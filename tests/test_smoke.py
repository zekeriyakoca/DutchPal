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
    chat,
    grammar,
    quiz,
    sentences,
    translate,
    translate_word,
    vocabulary,
    word,
)
from services import app_service
from services.word_lookup import WordLookup
from utils.db import get_db


async def _fake_agent_run(prompt, deps=None, **kwargs):
    return SimpleNamespace(output="agent reply")


async def _fake_async(*args, **kwargs):
    return "llm reply"


async def _fake_list(*args, **kwargs):
    return []


async def _fake_lookup(db, text):
    return WordLookup(word=text, lemma=text, translations=["to live"], source="book")


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
    monkeypatch.setattr(translate_word, "lookup_word", _fake_lookup)
    monkeypatch.setattr(word, "lookup_word", _fake_lookup)
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
    assert "response" in response.json() or "book_options" in response.json()


def test_word_lookup(client):
    response = client.post("/word/lookup", json={"word": "wonen"})
    assert response.status_code == 200, response.text
    assert response.json()["translations"] == ["to live"]
    assert client.post("/word/lookup", json={"word": ""}).status_code == 422


def test_translate_word_renders_lookup_as_table(client):
    response = client.post("/translate-word", json={"message": "wonen"})
    assert response.json()["response"] == "| Word | Translation |\n| --- | --- |\n| wonen | to live |"


def test_translate_unreadable_llm_reply_is_502(monkeypatch):
    calls = []
    monkeypatch.setattr(app_service, "chat_fast", lambda prompt: calls.append(prompt) or "Sorry, no JSON.")
    response = TestClient(main.app).post("/translate", json={"message": "Ik woon hier."})
    assert response.status_code == 502
    assert response.json() == {"detail": "The AI returned an answer we could not read. Please try again."}
    assert len(calls) == 2


def test_chat_sends_history_after_system_prompt(client, monkeypatch):
    seen = {}

    async def fake_run(prompt, deps=None, message_history=None):
        seen["history"] = message_history
        return SimpleNamespace(output="agent reply")

    monkeypatch.setattr(ask.language_agent, "run", fake_run)
    history = [{"role": "user", "content": "Hoi"}, {"role": "assistant", "content": "Hallo!"}]
    assert client.post("/chat", json={"message": "En nu?", "history": history}).status_code == 200
    kinds = [(type(part).__name__, part.content) for message in seen["history"] for part in message.parts]
    assert kinds == [
        ("SystemPromptPart", chat.system_prompt),
        ("UserPromptPart", "Hoi"),
        ("TextPart", "Hallo!"),
    ]


def test_get_db_closes_session(monkeypatch):
    session = MagicMock()
    monkeypatch.setattr(utils.db, "SessionLocal", lambda: session)

    dependency = get_db()
    assert next(dependency) is session
    dependency.close()

    session.close.assert_called_once()
