from __future__ import annotations as _annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any

import logfire
import openai
import numpy as np
from httpx import AsyncClient
from sqlalchemy import create_engine, text as sql_text
from sqlalchemy.orm import sessionmaker
from pydantic_ai import Agent, RunContext
from dotenv import load_dotenv

env_file = ".env.production" if os.getenv("ENV") == "production" else ".env"
load_dotenv(env_file)

logfire.configure(token=os.getenv("LOGFIRE_TOKEN"))

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


@dataclass
class Deps:
    client: AsyncClient
    db: Any  # SQLAlchemy session


system_prompt = (
    "You are a lively and friendly Dutch language learning assistant — like a smart, funny friend helping someone learn Dutch."
    " Use a warm, conversational tone, and explain things clearly and gently."
    " Sprinkle in light humor or fun examples when helpful — think of yourself as a patient teacher with a smile."
    " Respond only using Markdown formatting. Include headings, bullet points, tables, and **bold** text where appropriate."
    " Use your tools as much as you need to"
    "**Do not wrap the entire response in triple backticks or any code block.** Just return valid Markdown content directly."
)

agent_model = "grok:llama4-scout"

if agent_model == "gpt-4o":
    language_agent = Agent(
        "openai:gpt-4o",
        system_prompt=system_prompt,
        deps_type=Deps,
        retries=2,
        instrument=True,
    )

elif agent_model == "grok:llama4-scout":
    language_agent = Agent(
        model="groq:llama3-8b-8192",
        openai_base_url="https://api.groq.com/openai/v1",
        openai_api_key=os.getenv("GROQ_API_KEY"),
        system_prompt=system_prompt,
        deps_type=Deps,
        retries=2,
        instrument=True,
    )


def cosine_similarity(a: list[float], b: list[float]) -> float:
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def parse_embedding(text: str) -> list[float]:
    return [float(x) for x in text.split(",")]


@language_agent.tool
async def find_lesson_by_name(ctx: RunContext[Deps], text: str) -> str:
    """
    Searches embedded Dutch books for the most relevant lesson using similarity.
    - `text`: Input text to match.
    Returns the lesson title and content.
    """

    # Generate the embedding for the question
    embedded = (
        openai.embeddings.create(
            model="text-embedding-ada-002",
            input=text,
        )
        .data[0]
        .embedding
    )

    vector_str = f"[{', '.join(map(str, embedded))}]"

    db = ctx.deps.db

    # Query the database using pgvector cosine similarity
    result = db.execute(
        sql_text(
            """
            SELECT title, content
            FROM sections
            ORDER BY embedding <-> CAST(:embedding AS vector)
            LIMIT 1
        """
        ),
        {"embedding": vector_str},
    ).fetchone()

    if result:
        return f"## {result.title}\n\n{result.content}"
    return "No relevant lesson found."


@language_agent.tool
async def find_sentences(
    ctx: RunContext[Deps],
    text: str,
    limit: int = 1,
    book_id: int = None,
    cefr_level: str = "ALL LEVELS",
) -> str:
    """
    Finds similar sentences from embedded Dutch books.
    - `text`: The input text to find similar sentences for.
    - `limit`: The maximum number of sentences.
    - `book_id`: (Optional) Filter by book.
    - `cefr_level`: (Optional) Filter by CEFR level (e.g., A1, B2)).
    Returns a comma-separated list of similar sentence texts.
    """
    # Validate the CEFR level
    valid_cefr_levels = ["A1", "A2", "B1", "B2", "C1", "C2", "ALL LEVELS"]
    if cefr_level not in valid_cefr_levels:
        return f"Invalid CEFR level. Valid options are: {', '.join(valid_cefr_levels)}"
    if limit < 1:
        return "Limit must be at least 1."
    if limit > 10:
        return "Limit must be at most 10."

    # Generate the embedding for the question
    embedded = (
        openai.embeddings.create(
            model="text-embedding-ada-002",
            input=text,
        )
        .data[0]
        .embedding
    )

    vector_str = f"[{', '.join(map(str, embedded))}]"
    db = ctx.deps.db

    base_sql = """
        SELECT s.text AS sentence
        FROM sentences s
        WHERE (:book_id IS NULL OR s.book_id = :book_id)
          AND (:cefr_level = 'ALL LEVELS' OR s.cefr_level = :cefr_level)
        ORDER BY s.embedding <-> CAST(:embedding AS vector)
        LIMIT :limit
    """

    result = db.execute(
        sql_text(base_sql),
        {
            "embedding": vector_str,
            "book_id": book_id,
            "cefr_level": cefr_level,
            "limit": limit,
        },
    ).fetchall()

    if result:
        sentences = [row.sentence for row in result]
        return ", ".join(sentences)

    return "No similar sentence found."


@language_agent.tool
async def find_sentence_containing_word(
    ctx: RunContext[Deps], word: str, limit: int = 1, book_id: int = None
) -> str:
    """
    Finds sentences from embedded Dutch books containing a word.
    - `word`: Word to search for.
    - `limit`: Max results.
    - `book_id`: (Optional) Filter by book.
    Returns a comma-separated list of sentences containing the word.
    """

    if limit < 1:
        return "Limit must be at least 1."
    if limit > 10:
        return "Limit must be at most 10."
    if not word:
        return "Please provide a word to search for."
    if len(word) < 2:
        return "Word must be at least 2 characters long."
    if len(word) > 20:
        return "Word must be at most 20 characters long."

    db = ctx.deps.db

    base_sql = """
        SELECT s.text AS sentence
        FROM sentences s
        WHERE to_tsvector('dutch', s.text) @@ plainto_tsquery('dutch', :search)
        AND (:book_id IS NULL OR s.book_id = :book_id)
        ORDER BY RANDOM()
        LIMIT :limit
    """

    result = db.execute(
        sql_text(base_sql), {"search": word, "book_id": book_id, "limit": limit}
    ).fetchall()

    if result:
        sentences = [row.sentence for row in result]
        return ", ".join(sentences)

    return "No sentence found including the word."


@language_agent.tool
async def get_random_sentences(
    ctx: RunContext[Deps],
    limit: int = 1,
    book_id: int = None,
    cefr_level: str = "ALL LEVELS",
) -> str:
    """
    Retrieve random Dutch sentences from the dataset.
    - `limit`: Max results.
    - `book_id`: (Optional) Filter by book.
    - `cefr_level`: (Optional) Filter by CEFR level (e.g., A1, B2)).
    Returns a comma-separated list of random sentence texts.
    """

    db = ctx.deps.db

    sql = """
        SELECT s.text AS sentence
        FROM sentences s
        WHERE (:book_id IS NULL OR s.book_id = :book_id)
          AND (:cefr_level = 'ALL LEVELS' OR s.cefr_level = :cefr_level)
        ORDER BY RANDOM()
        LIMIT :limit
    """

    params = {"book_id": book_id, "cefr_level": cefr_level, "limit": limit}

    result = db.execute(sql_text(sql), params).fetchall()

    if result:
        sentences = [row.sentence for row in result]
        return ", ".join(sentences)

    return "No random sentences found."


@language_agent.tool
async def get_vocabularies(
    ctx: RunContext[Deps],
    word_to_search: str = None,
    limit: int = 1,
    cefr_level: str = None,
    pos: str = None,
) -> str:
    """
    Retrieves vocabulary from embedded Dutch books.

    - `word_to_search`: (Optional) If provided, returns semantically similar words. Otherwise, returns random entries..
    - `limit`: Max results.

    Optional filters:
    - `cefr_level`: (Optional) Filter by CEFR level (e.g., A1, B2).
    - `pos`: (Optional) Filter by part of speech (VERB, NOUN, INTJ, ADJ).

    Returns a formatted list of vocabulary entries including:
    - `lemma`: the word itself
    - `pos`: part of speech
    - `cefr_level`: estimated CEFR level
    - `encounter_count`: how many times the word appeared in the dataset
    """

    db = ctx.deps.db

    if word_to_search:
        # Generate embedding for semantic similarity
        embedded = (
            openai.embeddings.create(
                model="text-embedding-ada-002",
                input=word_to_search,
            )
            .data[0]
            .embedding
        )
        vector_str = f"[{', '.join(map(str, embedded))}]"

        sql = """
            SELECT lemma, pos, cefr_level, encounter_count
            FROM vocabulary
            WHERE (:cefr_level IS NULL OR cefr_level = :cefr_level)
              AND (:pos IS NULL OR pos = :pos)
            ORDER BY embedding <-> CAST(:embedding AS vector)
            LIMIT :limit
        """

        params = {
            "embedding": vector_str,
            "cefr_level": cefr_level,
            "pos": pos,
            "limit": limit,
        }
    else:
        # Random vocab retrieval
        sql = """
            SELECT lemma, pos, cefr_level, encounter_count
            FROM vocabulary
            WHERE (:cefr_level IS NULL OR cefr_level = :cefr_level)
              AND (:pos IS NULL OR pos = :pos)
            ORDER BY RANDOM()
            LIMIT :limit
        """

        params = {"cefr_level": cefr_level, "pos": pos, "limit": limit}

    result = db.execute(sql_text(sql), params).fetchall()

    if not result:
        return "No matching vocabulary found."

    # Format nicely
    return "\n".join(
        f"Lemma: {row.lemma}, POS: {row.pos}, CEFR: {row.cefr_level}, EncounterCount: {row.encounter_count}×"
        for row in result
    )


@language_agent.tool
async def find_book_id(ctx: RunContext[Deps], bookName: str) -> str:
    """
    Finds the most relevant book ID by name.
    - `bookName`: Book name to search.
    Returns the book ID or a message if not found.
    """

    # Query the database using pgvector cosine similarity
    result = ctx.deps.db.execute(
        sql_text(
            """
            SELECT title
            FROM books
            WHERE title = :bookName
            LIMIT 1
        """
        ),
        {"bookName": bookName},
    ).fetchone()

    if result:
        return result.id
    return "No relevant book found."


# no need to use this tool since agent can handle this task itself
# @language_agent.tool
# async def translate(ctx: RunContext[Deps], text: str, direction: str = "nl-en") -> str:
#     """Translate Dutch to English or vice versa."""
#     direction_map = {
#         "nl-en": "Translate this Dutch sentence into English:",
#         "en-nl": "Translate this English sentence into Dutch:",
#     }
#     prompt = f"{direction_map.get(direction, 'Translate:')}\n{text}"

#     response = await ctx.deps.client.post(
#         "https://api.openai.com/v1/chat/completions",
#         headers={
#             "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
#             "Content-Type": "application/json"
#         },
#         json={
#             "model": "gpt-3.5-turbo",
#             "messages": [{"role": "user", "content": prompt}]
#         }
#     )
#     return response.json()['choices'][0]['message']['content'].strip()


@language_agent.tool
async def explain_grammar(ctx: RunContext[Deps], sentence: str) -> str:
    """Explain the grammar rules in the given Dutch sentence."""
    prompt = f"Explain the Dutch grammar in this sentence:\n{sentence}"

    response = await ctx.deps.client.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
            "Content-Type": "application/json",
        },
        json={
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": prompt}],
        },
    )
    return response.json()["choices"][0]["message"]["content"].strip()


async def main():
    async with AsyncClient() as client:
        db = SessionLocal()
        deps = Deps(client=client, db=db)
        result = await language_agent.run(
            "Explain me the 'geboren' giving the example sentences.", deps=deps
        )
        print("Response:\n", result.data)


if __name__ == "__main__":
    asyncio.run(main())

__all__ = ["language_agent", "Deps", "SessionLocal"]
