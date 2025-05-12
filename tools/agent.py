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
from services.app_service import (
    find_lesson_by_name,
    get_vocabularies,
    find_book_id,
    find_or_get_sentences,
    find_sentence_containing_word,
)

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
    " Use your tools as much as you need to. Your first priority is to provide information from your dataset and tools and not to generate new content."
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


@language_agent.tool
async def find_lesson(ctx: RunContext[Deps], text: str) -> str:
    """
    Searches embedded Dutch books for the most relevant lesson using similarity.
    - `text`: Input text to match.
    Returns the lesson title and content.
    """
    return find_lesson_by_name(ctx.deps.db, text)


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
    return find_or_get_sentences(ctx.deps.db, text, limit, book_id, cefr_level)


@language_agent.tool
async def find_sentence(
    ctx: RunContext[Deps], word: str, limit: int = 1, book_id: int = None
) -> str:
    """
    Finds sentences from embedded Dutch books containing a word.
    - `word`: Word to search for.
    - `limit`: Max results.
    - `book_id`: (Optional) Filter by book.
    Returns a comma-separated list of sentences containing the word.
    """

    return find_sentence_containing_word(ctx.deps.db, word, limit, book_id)


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
        WHERE (:book_id IS NULL OR :book_id = 0 OR s.book_id = :book_id)
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
async def find_book_id_by_name(ctx: RunContext[Deps], bookName: str) -> str:
    return find_book_id(ctx.deps.db, bookName)


@language_agent.tool
async def get_book_names(ctx: RunContext[Deps]) -> list[str]:
    """
    Return array of name of books. Limit to 10 books.
    """

    # Query the database using pgvector cosine similarity
    result = ctx.deps.db.execute(
        sql_text(
            """
            SELECT title
            FROM books
            WHERE title = :bookName
            LIMIT 10
        """
        ),
        {},
    ).fetchone()

    if result:
        return [book.title for book in result]
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


def cosine_similarity(a: list[float], b: list[float]) -> float:
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def parse_embedding(text: str) -> list[float]:
    return [float(x) for x in text.split(",")]


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
