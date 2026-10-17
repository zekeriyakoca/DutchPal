"""Lookup merge and LLM JSON handling, on tiny synthetic rows (never book content)."""

import os

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("LOGFIRE_SEND_TO_LOGFIRE", "false")

import asyncio
from types import SimpleNamespace

import pytest

from services import word_lookup
from services.word_lookup import LlmWord, candidates_for, merge
from utils.llm_json import LlmJsonError, ask_llm_json, parse_llm_json


def book_entry(lemma, en, article=None):
    return SimpleNamespace(lemma=lemma, en=en, article=article)


def vocab_row(lemma, pos=None, cefr_level=None, present=None, v2=None, v3=None):
    return SimpleNamespace(
        lemma=lemma, infinitive=None, pos=pos, cefr_level=cefr_level, present_form=present, v2_form=v2, v3_form=v3
    )


LLM = LlmWord(
    lemma="llm-lemma",
    article="de",
    translations=["llm meaning"],
    pos="noun",
    forms={"present": "llm-p", "v2": "llm-v2", "v3": "llm-v3"},
    examples=["Zin een.", "Zin een.", "Zin twee."],
)


def test_candidates_strip_article_and_punctuation():
    assert candidates_for("  Het  Huis. ") == ["het huis", "huis"]
    assert candidates_for("lopen") == ["lopen"]
    assert candidates_for("de") == ["de"]


def test_book_values_win_over_llm():
    book = [book_entry("kat", "cat", "de"), book_entry("kat", "Cat"), book_entry("kat", "puss")]
    result = merge("katten", book, None, LLM.model_copy(update={"article": "het"}))
    assert result.source == "book"
    assert result.lemma == "kat"
    assert result.article == "de"
    assert result.translations == ["cat", "puss"]  # deduplicated, LLM meaning not added
    assert result.pos == "NOUN"  # missing from the book, filled by the LLM
    assert result.examples == ["Zin een.", "Zin twee."]


def test_book_entry_without_article_gets_none_from_llm():
    result = merge("lopen", [book_entry("lopen", "to walk")], None, LLM)
    assert result.article is None


def test_db_values_win_and_llm_fills_only_missing_forms():
    row = vocab_row("wonen", pos="verb", cefr_level="A1", present="woon/woont/wonen", v3="gewoond")
    result = merge("woont", [], row, LLM)
    assert result.source == "db"
    assert (result.lemma, result.pos, result.cefr_level) == ("wonen", "VERB", "A1")
    assert result.forms.model_dump() == {"present": "woon/woont/wonen", "v2": "llm-v2", "v3": "gewoond"}
    assert result.translations == ["llm meaning"]  # the vocabulary table has no translations


def test_llm_forms_dropped_for_non_verbs():
    assert merge("x", [], vocab_row("x", pos="NOUN"), LLM).forms.model_dump() == {"present": None, "v2": None, "v3": None}


def test_llm_only():
    result = merge("fiets", [], None, LLM.model_copy(update={"article": "Een", "lemma": None}))
    assert result.source == "llm"
    assert result.lemma == "fiets"
    assert result.article is None  # not de/het


def test_lookup_returns_stored_data_when_llm_fails(monkeypatch):
    async def failing(*args):
        raise LlmJsonError()

    monkeypatch.setattr(word_lookup, "find_vocabulary_row", lambda db, words: None)
    monkeypatch.setattr(word_lookup, "find_book_entries", lambda db, words: [book_entry("kat", "cat", "de")])
    monkeypatch.setattr(word_lookup, "ask_llm_json", failing)
    result = asyncio.run(word_lookup.lookup_word(None, "kat"))
    assert (result.translations, result.examples, result.source) == (["cat"], [], "book")

    monkeypatch.setattr(word_lookup, "find_book_entries", lambda db, words: [])
    with pytest.raises(LlmJsonError):
        asyncio.run(word_lookup.lookup_word(None, "kat"))


@pytest.mark.parametrize(
    "reply",
    [
        '{"translations": ["cat"]}',
        '```json\n{"translations": ["cat"]}\n```',
        'Here you go: {"translations": ["cat"]} Hope it helps!',
    ],
)
def test_parse_llm_json_accepts_wrapped_json(reply):
    assert parse_llm_json(reply, LlmWord).translations == ["cat"]


@pytest.mark.parametrize("reply", ["not json", '{"translations": "cat"}', '{"translations": ["cat"'])
def test_parse_llm_json_rejects_bad_replies(reply):
    with pytest.raises(LlmJsonError):
        parse_llm_json(reply, LlmWord)


def test_ask_llm_json_retries_once():
    replies = iter(["oops", '{"pos": "VERB"}'])
    assert asyncio.run(ask_llm_json(lambda prompt: next(replies), "p", LlmWord)).pos == "VERB"

    calls = []
    with pytest.raises(LlmJsonError):
        asyncio.run(ask_llm_json(lambda prompt: calls.append(prompt) or "oops", "p", LlmWord))
    assert len(calls) == 2
