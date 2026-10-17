"""Tests for the example-sentence lookup on small synthetic chapters (never real book content)."""

import os

# services.app_service builds an engine at import; these tests use their own.
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("OPENAI_API_KEY", "unused")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from services.app_service import find_sentence_containing_word
from tools.content.models import Base, Chapter, Dialogue, Exercise


@compiles(JSONB, "sqlite")
def _jsonb_as_json(type_, compiler, **kw):
    return "JSON"


def chapter(book_id, lines, items):
    return Chapter(
        book_id=book_id,
        book_title=book_id,
        number=1,
        title="Les 1",
        schema_version=1,
        dialogues=[Dialogue(source_id="d1", position=0, lines=lines)],
        exercises=[Exercise(source_id="o1", position=0, type="rewrite", payload={"items": items})],
    )


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            [
                chapter(
                    "book-a",
                    [
                        {"speaker": "A", "text": "Ik loop naar huis."},
                        {"speaker": "B", "text": "Lopen is gezond."},
                        {"speaker": None, "text": "(loopt weg)", "stage": True},
                    ],
                    [
                        {"text": "Hij liep gisteren.", "a": "..."},
                        {"text": "Ik ___ naar school.", "a": "loop"},
                        {"text": "Ik {loop/loopt} hier.", "a": "loop"},
                    ],
                ),
                chapter("book-b", [{"speaker": "A", "text": "We lopen samen."}], [{"text": "Wandelaars lopen."}]),
            ]
        )
        session.commit()
        yield session


def test_matches_whole_word_forms_case_insensitively(db):
    found = find_sentence_containing_word(db, ["lopen", "loop", "LIEP"], limit=10, book_id="book-a")
    assert sorted(found) == ["Hij liep gisteren.", "Ik loop naar huis.", "Lopen is gezond."]


def test_skips_gaps_choices_stage_lines_and_partial_words(db):
    assert find_sentence_containing_word(db, ["loopt"], limit=10) == []
    assert find_sentence_containing_word(db, ["wandel"], limit=10) == []


def test_filters_by_book_and_limits(db):
    assert sorted(find_sentence_containing_word(db, ["lopen"], limit=10, book_id="book-b")) == [
        "Wandelaars lopen.",
        "We lopen samen.",
    ]
    assert len(find_sentence_containing_word(db, ["lopen"], limit=2)) == 2


def test_invalid_input_is_empty(db):
    assert find_sentence_containing_word(db, [" ", "a"], limit=5) == []
    assert find_sentence_containing_word(db, ["lopen"], limit=0) == []
