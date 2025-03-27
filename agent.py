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

load_dotenv()

logfire.configure(token=os.getenv("LOGFIRE_TOKEN"))

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

@dataclass
class Deps:
    client: AsyncClient
    db: Any  # SQLAlchemy session

language_agent = Agent(
    "openai:gpt-4o",
    system_prompt=(
        "You are a Dutch language learning assistant."
        " Use the tools to retrieve lessons, translate text, and explain grammar topics clearly."
    ),
    deps_type=Deps,
    retries=2,
    instrument=True
)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def parse_embedding(text: str) -> list[float]:
    return [float(x) for x in text.split(",")]


@language_agent.tool
async def find_lesson(ctx: RunContext[Deps], text: str) -> str:
    """Find the most relevant lesson from the embedded Dutch books."""
    # Generate the embedding for the question
    embedded = openai.embeddings.create(
        model="text-embedding-ada-002",
        input=text,
    ).data[0].embedding

    vector_str = f"[{', '.join(map(str, embedded))}]"

    db = ctx.deps.db

    # Query the database using pgvector cosine similarity
    result = db.execute(
        sql_text("""
            SELECT title, content
            FROM sections
            ORDER BY embedding <-> CAST(:embedding AS vector)
            LIMIT 1
        """),
        {"embedding": vector_str}
    ).fetchone()

    if result:
        return f"## {result.title}\n\n{result.content}"
    return "No relevant lesson found."

@language_agent.tool
async def find_sentences(ctx: RunContext[Deps], text: str, limit: int = 1, book_id: int = None) -> str:
    """Find the most similar sentences from the embedded Dutch books, optionally filtered by book title. Get x number of similar sentences."""
    # Generate the embedding for the question
    embedded = openai.embeddings.create(
        model="text-embedding-ada-002",
        input=text,
    ).data[0].embedding

    vector_str = f"[{', '.join(map(str, embedded))}]"
    db = ctx.deps.db

    # Build SQL dynamically based on whether book_title is provided
    base_sql = """
        SELECT s.text AS sentence
        FROM sentences s
        WHERE (:book_id IS NULL OR s.book_id = :book_id)
        ORDER BY s.embedding <-> CAST(:embedding AS vector)
        LIMIT :limit
    """

    result = db.execute(
        sql_text(base_sql),
        {"embedding": vector_str, "book_id": book_id, "limit": limit}
    ).fetchall()

    if result:
        sentences = [row.sentence for row in result]
        return ", ".join(sentences)
    
    return "No similar sentence found."

@language_agent.tool
async def get_vocabularies(
    ctx: RunContext[Deps],
    text: str = None,
    limit: int = 1,
    cefr_level: str = None,
    pos: str = None
) -> str:
    """
    Retrieve vocabulary words from the embedded Dutch books.

    - If `text` is provided, returns the most semantically similar vocabulary entries based on vector similarity.
    - If `text` is not provided, returns random vocabulary entries.

    Optional filters:
    - `cefr_level`: Limit results to a specific CEFR level (e.g., A1, B2).
    - `pos`: Limit results by part of speech. Supported values: VERB, NOUN, INTJ, ADJ.

    Returns a formatted list of vocabulary entries including:
    - `lemma`: the word itself
    - `pos`: part of speech
    - `cefr_level`: estimated CEFR level
    - `encounter_count`: how many times the word appeared in the dataset
    """

    db = ctx.deps.db

    if text:
        # Generate embedding for semantic similarity
        embedded = openai.embeddings.create(
            model="text-embedding-ada-002",
            input=text,
        ).data[0].embedding
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
            "limit": limit
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

        params = {
            "cefr_level": cefr_level,
            "pos": pos,
            "limit": limit
        }

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
    """Find the most relevant book id from the Dutch books by book name."""

    # Query the database using pgvector cosine similarity
    result = ctx.deps.db.execute(
        sql_text("""
            SELECT title
            FROM books
            WHERE title = :bookName
            LIMIT 1
        """),
        {"bookName": bookName}
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
            "Content-Type": "application/json"
        },
        json={
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": prompt}]
        }
    )
    return response.json()['choices'][0]['message']['content'].strip()


async def main():
    async with AsyncClient() as client:
        db = SessionLocal()
        deps = Deps(client=client, db=db)
        result = await language_agent.run(
            "Explain me the 'geboren' giving the example sentences.",
            deps=deps
        )
        print("Response:\n", result.data)


if __name__ == '__main__':
    asyncio.run(main())
    
__all__ = ["language_agent", "Deps", "SessionLocal"]