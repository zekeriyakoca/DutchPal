import os

# The app reads these at import time; dummy values so no real DB, API key or Logfire is needed.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("LOGFIRE_SEND_TO_LOGFIRE", "false")

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import main
import utils.db
from routes import (
    ask,
    grammar,
    quiz,
    sentences,
    translate,
    translate_word,
    vocabulary,
)
from utils.db import get_db


async def _fake_agent_run(prompt, deps=None, output_type=None):
    if output_type is quiz.Quiz:
        return SimpleNamespace(output=quiz.Quiz(questions=[]))
    return SimpleNamespace(output="agent reply")


async def _fake_async(*args, **kwargs):
    return "llm reply"


async def _fake_list(*args, **kwargs):
    return []


@pytest.fixture
def client(monkeypatch):
    main.app.dependency_overrides[get_db] = lambda: MagicMock()

    # ask, chat and quiz share the same agent instance
    monkeypatch.setattr(ask.language_agent, "run", _fake_agent_run)
    monkeypatch.setattr(quiz, "get_paragraph_questions", lambda *a, **k: [])
    monkeypatch.setattr(sentences, "find_or_get_sentences", _fake_list)
    monkeypatch.setattr(vocabulary, "get_vocabularies", _fake_list)
    monkeypatch.setattr(grammar, "explain_grammar", _fake_async)
    monkeypatch.setattr(grammar, "explain", _fake_async)
    monkeypatch.setattr(translate, "translate", _fake_async)
    for name in ("chat_fast", "chat_smart", "chat_with_openai_5_nano"):
        monkeypatch.setattr(translate_word, name, lambda prompt: "| word |")
    monkeypatch.setattr(
        translate_word, "chat_with_openai_5_mini", lambda prompt: '{"word": "huis"}'
    )

    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize(
    "method, path, body",
    [
        ("get", "/bootstrap", None),
        ("post", "/chat", {"message": "hallo"}),
        ("post", "/ask", {"message": "hallo", "page": "grammar"}),
        ("post", "/sentences", {}),
        ("post", "/vocabulary", {}),
        ("post", "/quiz", {"quiz_type": "grammar"}),
        ("post", "/quiz", {"quiz_type": "PARAGRAPH"}),
        ("post", "/explain-grammar", {"message": "Ik woon hier."}),
        ("post", "/explain", {"message": "Ik woon hier."}),
        ("post", "/translate", {"message": "Ik woon hier."}),
        ("post", "/translate-word", {"message": "wonen"}),
        ("post", "/translate-word-as-json", {"message": "huis"}),
    ],
)
def test_routes_respond(client, method, path, body):
    response = client.request(method, path, json=body)
    assert response.status_code == 200, response.text
    assert response.json().keys() & {"response", "book_options", "items", "questions"}


def test_get_db_closes_session(monkeypatch):
    session = MagicMock()
    monkeypatch.setattr(utils.db, "SessionLocal", lambda: session)

    dependency = get_db()
    assert next(dependency) is session
    dependency.close()

    session.close.assert_called_once()
