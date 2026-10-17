"""Word lookup grounded in our own data.

Order: the textbook word lists (`vocab_entries`), then the old `vocabulary` table (CEFR level,
part of speech, verb forms), then the LLM for whatever both are missing. Stored values always
win; the LLM only fills empty fields.
"""

import json
from typing import Any, Literal, Optional

from pydantic import BaseModel
from sqlalchemy import func, or_, text as sql_text
from tools.chat_with_ai import chat_fast
from tools.content.models import VocabEntry
from utils.llm_json import ask_llm_json

ARTICLES = ("de", "het")


class Forms(BaseModel):
    present: Optional[str] = None
    v2: Optional[str] = None
    v3: Optional[str] = None


class WordLookup(BaseModel):
    word: str
    lemma: str
    article: Optional[str] = None
    translations: list[str] = []
    cefr_level: Optional[str] = None
    pos: Optional[str] = None
    forms: Forms = Forms()
    examples: list[str] = []
    source: Literal["book", "db", "llm"]  # where the entry was found; examples are always generated


class LlmWord(BaseModel):
    """The JSON we ask the LLM for. Everything is optional; unknown keys are ignored."""

    lemma: Optional[str] = None
    article: Optional[str] = None
    translations: list[str] = []
    pos: Optional[str] = None
    forms: Forms = Forms()
    examples: list[str] = []


def candidates_for(word: str) -> list[str]:
    """Lower-cased spellings to match: as typed, and without a leading article ("het huis" -> "huis")."""
    cleaned = " ".join(word.lower().split()).strip(".,;:!?\"'()")
    first, _, rest = cleaned.partition(" ")
    return [cleaned, rest] if first in ARTICLES and rest else [cleaned]


def find_vocabulary_row(db: Any, words: list[str]):
    # Matches the lemma or any verb form. Rows with a CEFR level come first: the rest of the
    # table is mostly noise (inflected forms, names), e.g. a bare "woont" row next to "wonen".
    return db.execute(
        sql_text(
            """
            SELECT lemma, pos, cefr_level, infinitive, present_form, v2_form, v3_form
            FROM vocabulary
            WHERE lower(lemma) = ANY(:words)
               OR lower(infinitive) = ANY(:words)
               OR string_to_array(lower(present_form), '/') && CAST(:words AS text[])
               OR string_to_array(lower(v2_form), '/') && CAST(:words AS text[])
               OR string_to_array(lower(v3_form), '/') && CAST(:words AS text[])
            ORDER BY cefr_level IS NULL, lower(lemma) = ANY(:words) DESC, encounter_count DESC NULLS LAST
            LIMIT 1
            """
        ),
        {"words": words},
    ).fetchone()


def find_book_entries(db: Any, words: list[str]) -> list[VocabEntry]:
    return (
        db.query(VocabEntry)
        .filter(
            or_(
                func.lower(VocabEntry.lemma).in_(words),
                func.lower(VocabEntry.nl).in_(words),
                func.lower(VocabEntry.form).in_(words),
            )
        )
        .order_by(VocabEntry.chapter_id, VocabEntry.list_position, VocabEntry.item_position)
        .all()
    )


def _unique(values) -> list[str]:
    seen, result = set(), []
    for value in values:
        value = (value or "").strip()
        if value and value.lower() not in seen:
            seen.add(value.lower())
            result.append(value)
    return result


def merge(word: str, book: list, row: Any, llm: Optional[LlmWord]) -> WordLookup:
    """Book first, then the vocabulary row, then the LLM, which only fills what is still empty."""
    lemma = (book[0].lemma if book else None) or (row and (row.infinitive or row.lemma))
    article = next((e.article for e in book if e.article), None)
    translations = _unique(e.en for e in book)
    pos = row.pos.upper() if row and row.pos else None
    forms = Forms(present=row.present_form, v2=row.v2_form, v3=row.v3_form) if row else Forms()
    examples = []

    if llm:
        lemma = lemma or llm.lemma
        # The book prints an article for every noun, so a book entry without one has none.
        if not book and llm.article and llm.article.lower() in ARTICLES:
            article = llm.article.lower()
        translations = translations or _unique(llm.translations)
        pos = pos or (llm.pos.upper() if llm.pos else None)
        if pos == "VERB":
            forms = Forms(**{k: getattr(forms, k) or getattr(llm.forms, k) for k in Forms.model_fields})
        examples = _unique(llm.examples)

    return WordLookup(
        word=word,
        lemma=lemma or word,
        article=article,
        translations=translations,
        cefr_level=row.cefr_level if row else None,
        pos=pos,
        forms=forms,
        examples=examples,
        source="book" if book else "db" if row else "llm",
    )


def build_lookup_prompt(word: str, stored: WordLookup) -> str:
    known = {}
    if stored.source != "llm":
        dumped = stored.model_dump(exclude={"word", "source", "examples"}, exclude_none=True)
        known = {k: v for k, v in dumped.items() if v}
    return f"""
    You are a Dutch dictionary. Describe the Dutch word: "{word}".
    {f"Known facts (keep to them): {json.dumps(known, ensure_ascii=False)}" if known else ""}

    Return only this JSON object, no other text:
    {{
      "lemma": "<dictionary form, e.g. wonen>",
      "article": "de | het | null (nouns only)",
      "translations": ["<short English meaning>"],
      "pos": "NOUN | VERB | ADJ | ADV | OTHER",
      "forms": {{"present": "<e.g. woon/woont/wonen>", "v2": "<e.g. woonde/woonden>", "v3": "<e.g. gewoond>"}},
      "examples": ["<short Dutch sentence using the word>", "<another one>"]
    }}
    Use null for "forms" values unless the word is a verb. Plain text only, no Markdown.
    """


async def lookup_word(db: Any, word: str) -> WordLookup:
    word = word.strip()
    words = candidates_for(word)
    row = find_vocabulary_row(db, words)
    if row:
        words += _unique([(row.lemma or "").lower(), (row.infinitive or "").lower()])
    book = find_book_entries(db, words)
    stored = merge(word, book, row, None)

    try:
        llm = await ask_llm_json(chat_fast, build_lookup_prompt(word, stored), LlmWord)
    except Exception as exc:
        if stored.source == "llm":
            raise
        # Stored facts are still worth showing without generated examples.
        print(f"Word lookup for {word!r}: LLM fill failed, returning stored data only: {exc}")
        return stored

    return merge(word, book, row, llm)
