"""Tests for routes/content.py on small synthetic chapters (never real book content).

Runs on in-memory SQLite by default; set TEST_DATABASE_URL to a throwaway Postgres database
to run against Postgres instead (its content tables are created and dropped by the tests).

    pip install pytest
    python -m pytest tests/test_content_api.py
"""

import os

# tools.agent builds an engine and an OpenAI agent at import; these tests use neither.
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("OPENAI_API_KEY", "unused")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from routes import content
from tools.content.models import Base, Chapter, Dialogue, Exercise, GrammarTopic, VocabEntry


@compiles(JSONB, "sqlite")
def _jsonb_as_json(type_, compiler, **kw):
    return "JSON"


def seed(db):
    """Two synthetic books; rows are added out of order to check the API sorts them."""
    full = Chapter(
        book_id="test-book",
        book_title="Test Book",
        book_cefr="A1",
        number=1,
        title="Hallo",
        schema_version=1,
        book_page_first=10,
        book_page_last=12,
        goals=["groeten"],
        culture=[{"title": "Cultuur", "text": "Tekst"}],
        reflection={"book_page": 12, "can_do": ["Ik kan groeten."]},
        dialogues=[
            Dialogue(source_id="ch01-d2", position=1, title="Twee", lines=[{"speaker": "B", "text": "Dag."}]),
            Dialogue(
                source_id="ch01-d1",
                position=0,
                title="Een",
                audio_tracks=["1-1"],
                lines=[
                    {"speaker": "A", "text": "Hallo."},
                    {"speaker": None, "text": "(later)", "stage": True},
                ],
                new_words=["hallo"],
            ),
        ],
        vocab_entries=[
            VocabEntry(list_position=1, item_position=0, list_name="Lijst 2", book_page=11, nl="lopen", lemma="lopen", en="to walk"),
            VocabEntry(list_position=0, item_position=1, list_name="Lijst 1", book_page=10, nl="het huis", lemma="huis", article="het", en="house"),
            VocabEntry(list_position=0, item_position=0, list_name="Lijst 1", book_page=10, nl="de kat", lemma="kat", article="de", en="cat"),
        ],
        grammar_topics=[
            GrammarTopic(source_id="ch01-g1", position=0, title="Zijn", book_page=11, content={"examples": ["Ik ben."]}),
        ],
        exercises=[
            Exercise(
                source_id="ch01-o2",
                position=1,
                label="Opdracht 2",
                type="choose_option",
                payload={"items": [{"text": "Ik {ben/bent} hier.", "options": ["ben", "bent"], "answer": "ben"}]},
            ),
            Exercise(
                source_id="ch01-o1",
                position=0,
                label="Opdracht 1",
                book_page=12,
                type="fill_gap",
                instruction="Vul in.",
                answers_source="generated_needs_review",
                payload={"items": [{"text": "Ik ___ Anna.", "answers": ["ben"]}]},
            ),
        ],
    )
    empty = Chapter(book_id="test-book", book_title="Test Book", book_cefr="A1", number=2, title="Dag", schema_version=1)
    screenshots = Chapter(
        book_id="other-book",
        book_title="Other Book",
        number=1,
        title="Les 1",
        schema_version=1,
        source_images=["les1.png"],
        note="Cut off at the bottom.",
    )
    db.add_all([empty, full, screenshots])
    db.commit()
    return full.id


@pytest.fixture(scope="module")
def client():
    url = os.getenv("TEST_DATABASE_URL")
    if url:
        engine = create_engine(url)
    else:
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    def get_test_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    with Session() as db:
        chapter_id = seed(db)

    app = FastAPI()
    app.include_router(content.router)
    app.dependency_overrides[content.get_db] = get_test_db
    with TestClient(app) as c:
        c.chapter_id = chapter_id
        yield c
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_books(client):
    r = client.get("/content/books")
    assert r.status_code == 200
    assert r.json() == [
        {"book_id": "other-book", "title": "Other Book", "cefr": None, "chapter_count": 1},
        {"book_id": "test-book", "title": "Test Book", "cefr": "A1", "chapter_count": 2},
    ]


def test_chapters_ordered_by_number(client):
    r = client.get("/content/books/test-book/chapters")
    assert r.status_code == 200
    assert r.json() == [
        {"id": client.chapter_id, "number": 1, "title": "Hallo", "goals": ["groeten"], "has_exercises": True},
        {"id": r.json()[1]["id"], "number": 2, "title": "Dag", "goals": [], "has_exercises": False},
    ]


def test_unknown_book_is_404(client):
    r = client.get("/content/books/no-such-book/chapters")
    assert r.status_code == 404
    assert r.json() == {"detail": "Book 'no-such-book' not found"}


def test_chapter(client):
    r = client.get(f"/content/chapters/{client.chapter_id}")
    assert r.status_code == 200
    ch = r.json()
    assert {k: ch[k] for k in ("id", "book_id", "book_title", "number", "title", "goals", "note", "book_pages")} == {
        "id": client.chapter_id,
        "book_id": "test-book",
        "book_title": "Test Book",
        "number": 1,
        "title": "Hallo",
        "goals": ["groeten"],
        "note": None,
        "book_pages": [10, 12],
    }
    assert ch["dialogues"] == [
        {
            "id": "ch01-d1",
            "title": "Een",
            "audio_tracks": ["1-1"],
            "lines": [
                {"speaker": "A", "text": "Hallo."},
                {"speaker": None, "text": "(later)", "stage": True},
            ],
            "new_words": ["hallo"],
        },
        {"id": "ch01-d2", "title": "Twee", "audio_tracks": [], "lines": [{"speaker": "B", "text": "Dag."}], "new_words": []},
    ]
    assert ch["vocabulary"] == [
        {
            "list": "Lijst 1",
            "book_page": 10,
            "items": [
                {"nl": "de kat", "lemma": "kat", "article": "de", "form": None, "en": "cat"},
                {"nl": "het huis", "lemma": "huis", "article": "het", "form": None, "en": "house"},
            ],
        },
        {
            "list": "Lijst 2",
            "book_page": 11,
            "items": [{"nl": "lopen", "lemma": "lopen", "article": None, "form": None, "en": "to walk"}],
        },
    ]
    assert ch["grammar"] == [{"id": "ch01-g1", "title": "Zijn", "book_page": 11, "content": {"examples": ["Ik ben."]}}]
    assert [e["label"] for e in ch["exercises"]] == ["Opdracht 1", "Opdracht 2"]
    first = ch["exercises"][0]
    assert isinstance(first["id"], int)
    assert {k: v for k, v in first.items() if k != "id"} == {
        "label": "Opdracht 1",
        "type": "fill_gap",
        "instruction": "Vul in.",
        "book_page": 12,
        "answers_source": "generated_needs_review",
        "payload": {"items": [{"text": "Ik ___ Anna.", "answers": ["ben"]}]},
    }
    assert ch["culture"] == [{"title": "Cultuur", "text": "Tekst"}]
    assert ch["reflection"] == {"book_page": 12, "can_do": ["Ik kan groeten."]}


def test_chapter_without_page_numbers(client):
    other = client.get("/content/books/other-book/chapters").json()[0]
    ch = client.get(f"/content/chapters/{other['id']}").json()
    assert ch["book_pages"] is None
    assert ch["note"] == "Cut off at the bottom."
    assert ch["dialogues"] == ch["vocabulary"] == ch["grammar"] == ch["exercises"] == []
    assert ch["reflection"] is None


def test_unknown_chapter_is_404(client):
    r = client.get("/content/chapters/999999")
    assert r.status_code == 404
    assert r.json() == {"detail": "Chapter 999999 not found"}
