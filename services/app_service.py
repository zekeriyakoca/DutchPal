from __future__ import annotations as _annotations

import asyncio

import os
import random
import re
from dataclasses import dataclass
from typing import Any, Optional

import logfire
import openai
import numpy as np
from httpx import AsyncClient
from sqlalchemy import String, cast, create_engine, or_, text as sql_text, true
from sqlalchemy.orm import sessionmaker
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from tools.chat_with_ai import chat_fast, chat_with_openai_5_mini
from tools.content.models import Chapter, Dialogue, Exercise
from utils.llm_json import ask_llm_json

SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
WORD = re.compile(r"[^\W\d_]+(?:[-'][^\W\d_]+)*")

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


def create_embedding(text: str) -> list[float]:
    return (
        openai.embeddings.create(
            model="text-embedding-ada-002",
            input=text,
        )
        .data[0]
        .embedding
    )


class SentenceTranslation(BaseModel):
    translation: str = Field(min_length=1)
    text: str


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

    prompt = f"""
        Translate the sentence '{sentence}' into English.
        If the sentence is not in good shape, intelligently correct it.
        return only a json with two fileds : translation and text like this:
        {{
            "translation": "Here is the translation",
            "text": "Here is the original text or corrected text"
        }} 
        No extra text or explanation needed buy only the json.
    """

    result = await ask_llm_json(chat_fast, prompt, SentenceTranslation)

    mdText = f"**Translation:** {result.translation}\n\n**Original Text:** {result.text}"
    return mdText


def find_sentence_containing_word(
    db: Any,
    word_forms: list[str],
    limit: int = 1,
    book_id: Optional[str] = None,
) -> list[str]:
    """
    Example sentences from the textbooks (dialogue lines and exercise items) that contain
    one of `word_forms` as a whole word, case-insensitively.
    - `book_id`: (Optional) Only from this book (slug).
    Returns up to `limit` random matches; empty for invalid input.
    """
    forms = sorted({w.strip().lower() for w in word_forms if len(w.strip()) > 1})
    if not forms or limit < 1:
        return []

    pattern = re.compile(rf"(?<!\w)({'|'.join(map(re.escape, forms))})(?!\w)", re.IGNORECASE)
    sentences = (s for t in example_texts(db, forms, book_id) for s in SENTENCE_END.split(t))
    matches = list(dict.fromkeys(s.strip() for s in sentences if pattern.search(s)))
    return random.sample(matches, min(limit, len(matches)))


def example_texts(db: Any, forms: Optional[list[str]], book_id: Optional[str]) -> list[str]:
    """Dialogue lines and finished exercise sentences; with `forms`, only rows whose JSON
    mentions one of them (a cheap SQL pre-filter)."""

    def mentions(column):
        return or_(*(cast(column, String).ilike(f"%{form}%") for form in forms)) if forms else true()

    dialogues = db.query(Dialogue.lines).filter(mentions(Dialogue.lines))
    exercises = db.query(Exercise.payload).filter(mentions(Exercise.payload))
    if book_id:
        dialogues = dialogues.join(Dialogue.chapter).filter(Chapter.book_id == book_id)
        exercises = exercises.join(Exercise.chapter).filter(Chapter.book_id == book_id)

    texts = [line.get("text") for (lines,) in dialogues for line in lines if not line.get("stage")]
    texts += [
        item.get("text")
        for (payload,) in exercises
        for item in payload.get("items", [])
        if isinstance(item, dict)
    ]
    # Gap ("___") and choice ("{a/b}") items are not finished sentences.
    return list(dict.fromkeys(t for t in texts if isinstance(t, str) and "___" not in t and "{" not in t))


def content_words(db: Any, book_id: Optional[str]) -> list[str]:
    """Every word that occurs in the textbook texts (optionally one book), lower-cased."""
    return sorted({w.lower() for t in example_texts(db, None, book_id) for w in WORD.findall(t)})


async def get_vocabularies(
    db: Any,
    word_to_search: str = None,
    limit: int = 1,
    cefr_level: str = "ALL LEVELS",
    pos: str = None,
    book_id: Optional[str] = None,
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
        embedded = await asyncio.to_thread(create_embedding, word_to_search)
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
        # Random words that occur in the textbooks, so each one has example sentences.
        sql = """
            SELECT lemma, pos, cefr_level, encounter_count, infinitive, present_form, v2_form, v3_form
            FROM vocabulary
            WHERE (:cefr_level = 'ALL LEVELS' OR cefr_level = :cefr_level)
              AND (:pos IS NULL OR pos = :pos)
              AND (lower(lemma) = ANY(:words)
                   OR string_to_array(lower(coalesce(present_form, '') || '/' || coalesce(v2_form, '')
                                            || '/' || coalesce(v3_form, '')), '/') && :words)
            ORDER BY RANDOM()
            LIMIT :limit
        """

        params = {
            "cefr_level": cefr_level,
            "pos": pos,
            "limit": limit,
            "words": content_words(db, book_id),
        }

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



async def explain_grammar(client: AsyncClient, sentence: str) -> str:
    """Explain the grammar rules in the given Dutch sentence."""
    prompt = f"Explain the Dutch grammar in this sentence:\n{sentence}"

    response = await client.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
            "Content-Type": "application/json",
        },
        json={
            "model": "gpt-5-mini",
            "reasoning_effort": "low",
            "messages": [{"role": "user", "content": prompt}],
        },
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


async def explain(sentence: str) -> str:
    """Explain the given Dutch sentence"""

    prompt = f"""
    Explain the Dutch grammar in this sentence:\n{sentence}
    Focus only on grammar rules, vocabulary, or phrases that stand out or may be tricky. 
    Skip anything too basic (A1 level or below).
    First translate and then explain it in quite concise and keep it simple. Mention Sentence Structure and Notable Points. Max 150 words, less is better, though. Don't tell every detail, just the most important ones.
    Return proper formatted, easy to read markdown text. Use headings, bullet points, and code blocks, bold texts where appropriate.
    """

    return await asyncio.to_thread(chat_with_openai_5_mini, prompt)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def parse_embedding(text: str) -> list[float]:
    return [float(x) for x in text.split(",")]


__all__ = [
    "Deps",
    "SessionLocal",
    "find_sentence_containing_word",
    "get_vocabularies",
]
