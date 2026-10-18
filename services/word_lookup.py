"""Word lookup grounded in our own data.

Order: the textbook word lists (`vocab_entries`), then the old `vocabulary` table (CEFR level,
part of speech, verb forms), then the Azure Translator dictionary (English meanings, part of
speech, example sentences), then the LLM for whatever is still missing. Stored values always
win; the dictionary and the LLM only fill empty fields, and the LLM is skipped when nothing is.
"""

import json
import os
from typing import Any, Literal, Optional

import httpx
from pydantic import BaseModel, field_validator
from sqlalchemy import func, or_, text as sql_text
from tools.chat_with_ai import chat_fast
from tools.content.models import VocabEntry
from utils.llm_json import ask_llm_json

ARTICLES = ("de", "het")
TRANSLATOR_URL = "https://api.cognitive.microsofttranslator.com/dictionary"
# Translator part-of-speech tags mapped to the ones the LLM uses; the rest becomes OTHER.
DICTIONARY_POS = {"NOUN": "NOUN", "VERB": "VERB", "MODAL": "VERB", "ADJ": "ADJ", "ADV": "ADV"}


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
    source: Literal["book", "db", "dictionary", "llm"]  # where the entry was found


class LlmWord(BaseModel):
    """The JSON we ask the LLM for, also the dictionary's answer. Everything is optional; unknown keys are ignored."""

    lemma: Optional[str] = None
    article: Optional[str] = None
    translations: list[str] = []
    pos: Optional[str] = None
    forms: Forms = Forms()
    examples: list[str] = []

    @field_validator("forms", mode="before")
    @classmethod
    def no_forms(cls, value):
        # The LLM writes `"forms": null` for words that are not verbs.
        return {} if value is None else value

    @field_validator("translations", "examples", mode="before")
    @classmethod
    def no_items(cls, value):
        return [] if value is None else value


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


def merge(word: str, book: list, row: Any, dictionary: Optional[LlmWord], llm: Optional[LlmWord]) -> WordLookup:
    """Book first, then the vocabulary row, then the dictionary and the LLM, which only fill what is still empty."""
    lemma = (book[0].lemma if book else None) or (row and (row.infinitive or row.lemma))
    article = next((e.article for e in book if e.article), None)
    translations = _unique(e.en for e in book)
    pos = row.pos.upper() if row and row.pos else None
    forms = Forms(present=row.present_form, v2=row.v2_form, v3=row.v3_form) if row else Forms()
    examples = []

    for fill in (dictionary, llm):
        if not fill:
            continue
        lemma = lemma or fill.lemma
        # The book prints an article for every noun, so a book entry without one has none.
        if not book and fill.article and fill.article.lower() in ARTICLES:
            article = fill.article.lower()
        translations = translations or _unique(fill.translations)
        pos = pos or (fill.pos.upper() if fill.pos else None)
        if pos == "VERB":
            forms = Forms(**{k: getattr(forms, k) or getattr(fill.forms, k) for k in Forms.model_fields})
        examples = examples or _unique(fill.examples)

    return WordLookup(
        word=word,
        lemma=lemma or word,
        article=article,
        translations=translations,
        cefr_level=row.cefr_level if row else None,
        pos=pos,
        forms=forms,
        examples=examples,
        source="book" if book else "db" if row else "dictionary" if dictionary else "llm",
    )


async def dictionary_lookup(term: str) -> Optional[LlmWord]:
    """
    English meanings and part of speech from the Azure Translator
    dictionary (REST, no SDK). None without AZURE_TRANSLATOR_KEY, when the dictionary does not
    know the word, or on any error, incl. 429 when the F0 quota (2M characters a month) is used up.
    """
    key, region = os.getenv("AZURE_TRANSLATOR_KEY"), os.getenv("AZURE_TRANSLATOR_REGION")
    if not key:
        return None
    headers = {"Ocp-Apim-Subscription-Key": key}
    if region:
        headers["Ocp-Apim-Subscription-Region"] = region

    try:
        # A short timeout: the lookup must not get slower than the LLM alone.
        async with httpx.AsyncClient(
            timeout=3, headers=headers, params={"api-version": "3.0", "from": "nl", "to": "en"}
        ) as client:
            response = await client.post(f"{TRANSLATOR_URL}/lookup", json=[{"Text": term}])
            response.raise_for_status()
            entry = response.json()[0]
            # Sorted by confidence; the long tail is rare or odd meanings.
            meanings = [t for t in entry["translations"] if t["confidence"] >= 0.05][:4]
            if not meanings:
                return None
            # Only meanings: the nl→en examples endpoint returns English sentences on both sides,
            # so Dutch examples still come from the LLM.
            return LlmWord(
                translations=[t["displayTarget"] for t in meanings],
                pos=DICTIONARY_POS.get(meanings[0]["posTag"], "OTHER"),
            )
    except Exception as exc:
        print(f"Translator dictionary for {term!r} skipped: {exc!r}")
        return None


def needs_llm(stored: WordLookup, book: list) -> bool:
    """True when a field the LLM fills is still empty."""
    if stored.source in ("dictionary", "llm"):
        return True  # no stored lemma ("noemde" -> "noemen") nor article
    return (
        not stored.translations
        or not stored.examples
        or not stored.pos
        or (stored.pos == "NOUN" and not book and not stored.article)
        or (stored.pos == "VERB" and not all(stored.forms.model_dump().values()))
    )


def build_lookup_prompt(word: str, stored: WordLookup) -> str:
    known = {}
    if stored.source != "llm":
        dumped = stored.model_dump(exclude={"word", "source", "examples"}, exclude_none=True)
        known = {k: v for k, v in dumped.items() if v}
        if stored.source == "dictionary":
            known.pop("lemma", None)  # only the typed word; the dictionary gives no lemma
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
    # The stored lemma finds more ("noemde" -> "noemen"); otherwise the word without its article.
    lemma = merge(word, book, row, None, None).lemma if book or row else words[-1]
    dictionary = await dictionary_lookup(lemma)
    stored = merge(word, book, row, dictionary, None)
    if not needs_llm(stored, book):
        return stored

    try:
        llm = await ask_llm_json(chat_fast, build_lookup_prompt(word, stored), LlmWord)
    except Exception as exc:
        if stored.source == "llm":
            raise
        # Stored facts are still worth showing without generated examples.
        print(f"Word lookup for {word!r}: LLM fill failed, returning stored data only: {exc}")
        return stored

    return merge(word, book, row, dictionary, llm)
