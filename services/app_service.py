from __future__ import annotations as _annotations

import json
import os
from dataclasses import dataclass
from typing import Any, List

import logfire
import openai
import numpy as np
from httpx import AsyncClient
from sqlalchemy import create_engine, text as sql_text
from sqlalchemy.orm import sessionmaker
from pydantic_ai import RunContext
from dotenv import load_dotenv
from tools.chat_with_ai import chat_with_grok
from utils.cerf_helper import map_to_joint_levels

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


async def translate(sentence: str) -> str:
    """
    Translates a Dutch sentence into English using the GROK model.

    Args:
        sentence: Dutch sentence to translate.

    Returns:
        A English translation corresponding to the input sentence.
    """
    if not sentence:
        return "Nothing to translate."

    prompt = f"""Translate the sentence '{sentence}' into English. Highlight the important words in the sentence. Do not return any extra info buy only md formatted translation."""

    response = chat_with_grok(prompt=prompt)
    return response.strip()


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


async def find_or_get_sentences(
    db: Any,
    text: str = None,
    limit: int = 1,
    book_id: int = None,
    cefr_level: str = "ALL LEVELS",
) -> list[dict]:
    """
    Finds similar sentences or retrieves random sentences from embedded Dutch books.
    - `text`: The input text to find similar sentences for (optional).
    - `limit`: The maximum number of sentences.
    - `book_id`: (Optional) Filter by book.
    - `cefr_level`: (Optional) Filter by CEFR level (e.g., A1, B2).
    Returns a list of objects like [{"sentence": "...", "translation": "..."}].
    """

    # Validate input
    if limit < 1:
        return [{"error": "Limit must be at least 1."}]
    if limit > 10:
        return [{"error": "Limit must be at most 10."}]
    if cefr_level not in ["A1", "A2", "B1", "B2", "C1", "C2", "ALL LEVELS"]:
        return [
            {
                "error": "Invalid CEFR level. Valid options are: A1, A2, B1, B2, C1, C2, ALL LEVELS."
            }
        ]

    # SQL query for random sentences
    if not text:
        sql = """
            SELECT s.id AS id, s.text AS sentence, s.translation AS translation
            FROM sentences s
            WHERE (:book_id IS NULL OR :book_id = 0 OR s.book_id = :book_id)
              AND (:cefr_level = 'ALL LEVELS' OR s.cefr_level = :cefr_level)
            ORDER BY RANDOM()
            LIMIT :limit
        """
        params = {"book_id": book_id, "cefr_level": cefr_level, "limit": limit}

    # SQL query for embedding-based search
    else:
        # Generate the embedding for the input text
        embedded = (
            openai.embeddings.create(
                model="text-embedding-ada-002",
                input=text,
            )
            .data[0]
            .embedding
        )

        vector_str = f"[{', '.join(map(str, embedded))}]"

        sql = """
            SELECT s.id AS id, s.text AS sentence, s.translation AS translation
            FROM sentences s
            WHERE (:book_id IS NULL OR :book_id = 0 OR s.book_id = :book_id)
              AND (:cefr_level = 'ALL LEVELS' OR s.cefr_level = :cefr_level)
            ORDER BY s.embedding <-> CAST(:embedding AS vector)
            LIMIT :limit
        """
        params = {
            "embedding": vector_str,
            "book_id": book_id,
            "cefr_level": cefr_level,
            "limit": limit,
        }

    # Execute the query
    result = db.execute(sql_text(sql), params).fetchall()

    if not result:
        return [{"error": "No sentences found."}]

    # Convert result to a list of dictionaries
    sentences = [
        {"id": row.id, "text": row.sentence, "translation": row.translation}
        for row in result
    ]

    print(f"{len(sentences)} sentences found.")
    # Ensure translations for sentences without them
    sentences = await ensure_translation(db, sentences)

    # Return the list of sentences with translations
    return [{"sentence": s["text"], "translation": s["translation"]} for s in sentences]


async def ensure_translation(db: Any, sentences: list[dict]) -> list[dict]:
    """
    Ensures translations exist for the given list of sentences.
    If a sentence does not have a translation, it uses the GROK model to translate all missing sentences
    in a single batch and updates the database with the translations.

    Args:
        db: Database session.
        sentences: List of dictionaries with sentence details (e.g., [{"id": 1, "text": "Ik wil leren"}]).

    Returns:
        List of dictionaries with sentence and translation (e.g., [{"sentence": "...", "translation": "..."}]).
    """
    # Filter sentences that do not have translations
    untranslated_sentences = [s for s in sentences if not s.get("translation")]

    if not untranslated_sentences:
        return sentences

    print(f"{len(untranslated_sentences)} sentences to be translated.")

    # Prepare the prompt for the GROK model
    sentences_to_translate = [s["text"] for s in untranslated_sentences]
    prompt = (
        "Translate the following Dutch sentences to English. "
        'Return ONLY AND ONLY array of the translations like this: ["Here you go", "I want to learn", ...]\n\n'
        "Don't include any extra text or explanations."
        + "\n".join(sentences_to_translate)
    )
    # Call the GROK model to translate all sentences in one batch
    response = chat_with_grok(prompt=prompt)

    translations = json.loads(response)

    # Update the database with the translations
    for sentence, translation in zip(untranslated_sentences, translations):
        sentence["translation"] = translation.strip()
        print(
            f"Updating translation for sentence ID {sentence['id']}: {translation.strip()}"
        )
        db.execute(
            sql_text("UPDATE sentences SET translation = :translation WHERE id = :id"),
            {"translation": translation.strip(), "id": sentence["id"]},
        )

    db.commit()

    # Return the updated list of sentences with translations
    return sentences


async def find_sentence_containing_word(
    db: Any,
    word_forms: List[str],
    limit: int = 1,
    book_id: int = None,
    cefr_level: str = "ALL LEVELS",
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

    word_forms = [w.strip() for w in word_forms if len(w.strip()) > 1]

    if not word_forms:
        return "Please provide a word to search for."
    if len(word_forms[0]) < 2:
        return "Word must be at least 2 characters long."
    if len(word_forms[0]) > 20:
        return "Word must be at most 20 characters long."

    result = retrieve_sentences(db, word_forms, limit, book_id, cefr_level)
    if not result:
        result = retrieve_sentences(db, word_forms, limit, book_id, "ALL LEVELS")

    print(f"{len(result)} sentences found.")
    if result:
        sentences = [row.sentence for row in result]
        return ", ".join(sentences)

    return "No sentence found including the word."


def retrieve_sentences(db, word_forms, limit, book_id, cefr_level):
    cefr_level_set = map_to_joint_levels(cefr_level)
    base_sql = """
        SELECT s.text AS sentence
        FROM sentences s
        WHERE to_tsvector('dutch', s.text) @@ to_tsquery('dutch', :tsquery)
        AND (:book_id IS NULL OR :book_id = 0 OR s.book_id = :book_id)
        AND (:cefr_level = 'ALL LEVELS' OR s.cefr_level = ANY(:cefr_level_set))
        ORDER BY RANDOM()
        LIMIT :limit
    """

    result = db.execute(
        sql_text(base_sql),
        {
            "tsquery": " | ".join(word_forms),
            "book_id": book_id,
            "limit": limit,
            "cefr_level": cefr_level,
            "cefr_level_set": cefr_level_set,
        },
    ).fetchall()

    return result


async def get_vocabularies(
    db: Any,
    word_to_search: str = None,
    limit: int = 1,
    cefr_level: str = "ALL LEVELS",
    pos: str = None,
) -> str:
    """
    Retrieves vocabulary from embedded Dutch books.

    - `word_to_search`: (Optional) If provided, returns semantically similar words. Otherwise, returns random entries..
    - `limit`: Max results.

    Optional filters:
    - `cefr_level`: (Optional) Filter by CEFR level (e.g., A1, B2).
    - `pos`: (Optional) Filter by part of speech (VERB, NOUN, INTJ, ADJ).

    Returns a formatted list of vocabulary entries
    """

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
            SELECT lemma, pos, cefr_level, encounter_count, infinitive, present_form, v2_form, v3_form
            FROM vocabulary
            WHERE (:cefr_level = 'ALL LEVELS' OR cefr_level = :cefr_level)
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
            SELECT lemma, pos, cefr_level, encounter_count, infinitive, present_form, v2_form, v3_form
            FROM vocabulary
            WHERE (:cefr_level = 'ALL LEVELS' OR cefr_level = :cefr_level)
              AND (:pos IS NULL OR pos = :pos)
            ORDER BY RANDOM()
            LIMIT :limit
        """

        params = {"cefr_level": cefr_level, "pos": pos, "limit": limit}

    result = db.execute(sql_text(sql), params).fetchall()

    if not result:
        return "No matching vocabulary found."

    # return an proper object
    return [
        {
            "lemma": row.lemma,
            "pos": row.pos,
            "cefr_level": row.cefr_level,
            "encounter_count": row.encounter_count,
            "infinitive": row.infinitive,
            "present_form": row.present_form,
            "v2_form": row.v2_form,
            "v3_form": row.v3_form,
        }
        for row in result
    ]

    # return "\n".join(
    #     f"Lemma: {row.lemma}, POS: {row.pos}, CEFR: {row.cefr_level}, EncounterCount: {row.encounter_count}×"
    #     for row in result
    # )


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


def cosine_similarity(a: list[float], b: list[float]) -> float:
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def parse_embedding(text: str) -> list[float]:
    return [float(x) for x in text.split(",")]


__all__ = [
    "Deps",
    "SessionLocal",
    "find_lesson_by_name",
    "find_sentence_containing_word",
    "find_or_get_sentences",
    "get_vocabularies",
    "find_book_id",
]
