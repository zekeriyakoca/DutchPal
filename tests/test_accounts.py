import os

# The app reads these at import time; dummy values so no real DB, API key or Logfire is needed.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("LOGFIRE_SEND_TO_LOGFIRE", "false")

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
from routes import auth
from services import notion, users
from services.users import UserSettings, decrypt_secret
from utils.auth import SESSION_COOKIE
from utils.db import get_db

CLAIMS = {"sub": "google-123", "email": "anna@example.com", "name": "Anna", "picture": "https://p/anna.png"}


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id.apps.googleusercontent.com")
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("SETTINGS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("NOTION_SECRET", "default-secret")
    monkeypatch.setenv("NOTION_NOUN_DB_ID", "default-noun-db")
    monkeypatch.setenv("NOTION_VERB_DB_ID", "default-verb-db")

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    users.Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    def get_test_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    main.app.dependency_overrides[get_db] = get_test_db
    yield Session
    main.app.dependency_overrides.clear()


@pytest.fixture
def verified(monkeypatch):
    calls = []

    def fake_verify(token, request, audience):
        calls.append((token, audience))
        if token != "good-token":
            raise ValueError("Token has wrong audience")
        return CLAIMS

    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", fake_verify)
    return calls


@pytest.fixture
def client(db, verified):
    # https so the Secure session cookie is sent back
    return TestClient(main.app, base_url="https://testserver")


def sign_in(client):
    response = client.post("/auth/google", json={"credential": "good-token"})
    assert response.status_code == 200, response.text
    return response


def test_sign_in_verifies_token_for_our_client_and_sets_session(client, verified, db):
    response = sign_in(client)

    assert verified == [("good-token", "client-id.apps.googleusercontent.com")]
    assert response.json()["email"] == "anna@example.com"
    cookie = response.headers["set-cookie"].lower()
    assert all(flag in cookie for flag in ("httponly", "secure", "samesite=lax"))
    assert client.get("/auth/me").json()["user"]["name"] == "Anna"

    sign_in(client)  # second login updates the same row
    assert db().query(users.User).count() == 1


def test_bad_token_is_rejected(client):
    response = client.post("/auth/google", json={"credential": "forged"})
    assert response.status_code == 401
    assert client.get("/auth/me").json()["is_authenticated"] is False


def test_logout_and_tampered_cookie_mean_signed_out(client):
    sign_in(client)
    user_id, expires, signature = client.cookies[SESSION_COOKIE].split(".")
    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE, f"{int(user_id) + 1}.{expires}.{signature}")
    assert client.get("/auth/me").json()["is_authenticated"] is False

    sign_in(client)
    client.post("/auth/logout")
    assert client.get("/auth/me").json()["is_authenticated"] is False


def test_settings_require_sign_in(client):
    assert client.get("/settings").status_code == 401
    assert client.put("/settings/notion", json={"secret": "x"}).status_code == 401


def test_notion_secret_is_encrypted_and_never_returned(client, db):
    sign_in(client)
    response = client.put(
        "/settings/notion", json={"secret": "secret_abc", "noun_db_id": "my-noun", "verb_db_id": ""}
    )

    assert response.status_code == 200, response.text
    assert "secret_abc" not in response.text
    assert response.json()["notion"] == {"secret_set": True, "noun_db_id": "my-noun", "verb_db_id": None}
    stored = db().query(UserSettings).one().notion_secret_encrypted
    assert stored != "secret_abc" and decrypt_secret(stored) == "secret_abc"

    # an empty secret keeps the saved one
    client.put("/settings/notion", json={"secret": "", "noun_db_id": "other-noun", "verb_db_id": ""})
    assert decrypt_secret(db().query(UserSettings).one().notion_secret_encrypted) == "secret_abc"

    response = client.delete("/settings/notion")
    assert response.json()["notion"]["secret_set"] is False


@pytest.fixture
def notion_calls(monkeypatch):
    calls = []

    async def fake_request(secret, method, path, json=None):
        calls.append((secret, method, path, json))
        return {"results": []}

    monkeypatch.setattr(notion, "notion_request", fake_request)
    return calls


def test_anonymous_saves_to_default_notion(client, notion_calls):
    response = client.post("/notion/noun", json={"name": " Huis ", "meaning": "house", "sentence": "Het **huis**."})

    assert response.json() == {"message": "Record inserted or already exists.", "count": 1}
    (query_secret, _, query_path, query), (secret, _, path, page) = notion_calls
    assert (query_secret, query_path) == ("default-secret", "databases/default-noun-db/query")
    assert query["filter"] == {"property": "Name", "rich_text": {"contains": "huis"}}
    assert (secret, path) == ("default-secret", "pages")
    assert page["parent"] == {"database_id": "default-noun-db"}
    assert page["properties"]["Name"] == {"title": [{"text": {"content": "huis"}}]}
    assert [s["annotations"]["bold"] for s in page["properties"]["Sentence"]["rich_text"]] == [False, True, False]


def test_signed_in_user_saves_to_own_notion(client, notion_calls):
    sign_in(client)
    client.put("/settings/notion", json={"secret": "user-secret", "noun_db_id": "", "verb_db_id": "user-verb-db"})

    response = client.post("/notion/verb", json={"name": "lopen", "meaning": "to walk", "pastTense": "liep"})

    assert response.json()["count"] == 1
    assert {(secret, path) for secret, _, path, _ in notion_calls} == {
        ("user-secret", "databases/user-verb-db/query"),
        ("user-secret", "pages"),
    }
    assert notion_calls[1][3]["properties"]["Past Tense"] == {"rich_text": [{"text": {"content": "liep"}}]}
    # their own Notion without a noun database: no silent fallback to the shared one
    assert client.post("/notion/noun", json={"name": "huis"}).status_code == 400


def test_existing_word_is_not_saved_again(client, monkeypatch):
    async def found(secret, method, path, json=None):
        assert path.endswith("/query")
        return {"results": [{"id": "page"}]}

    monkeypatch.setattr(notion, "notion_request", found)
    assert client.post("/notion/noun", json={"name": "huis"}).json()["count"] == 0
