"""Path safety of routes/media.py: only media files inside MEDIA_DIR are served.

    python -m pytest tests/test_media.py
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes import media


@pytest.fixture
def client(tmp_path, monkeypatch):
    root = tmp_path / "media"
    (root / "exam").mkdir(parents=True)
    (root / "exam" / "track 1.mp3").write_bytes(b"ID3audio")
    (root / "exam" / "notes.json").write_text("{}")
    (tmp_path / "secret.mp3").write_bytes(b"outside")
    (root / "exam" / "link.mp3").symlink_to(tmp_path / "secret.mp3")
    monkeypatch.setenv("MEDIA_DIR", str(root))
    app = FastAPI()
    app.include_router(media.router)
    return TestClient(app)


def test_serves_a_media_file_inside_the_root(client):
    r = client.get("/media/exam/track%201.mp3")
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/mpeg"
    assert r.content == b"ID3audio"


@pytest.mark.parametrize(
    "url",
    [
        "/media/%2e%2e/secret.mp3",  # ../secret.mp3
        "/media/exam/%2e%2e/%2e%2e/secret.mp3",
        "/media/..%2fsecret.mp3",
        "/media/%2fetc%2fpasswd",  # absolute path
        "/media/exam/link.mp3",  # symlink pointing outside the root
        "/media/exam/notes.json",  # not a media type
        "/media/exam/missing.mp3",
        "/media/exam",  # a directory
        "/media/exam/track%001.mp3",  # embedded null byte
    ],
)
def test_refuses_paths_outside_the_root_or_not_media(client, url):
    r = client.get(url)
    assert r.status_code == 404
    assert b"outside" not in r.content


@pytest.mark.parametrize("path", ["../secret.mp3", "exam/../../secret.mp3", "/etc/passwd", "exam/link.mp3", ""])
def test_resolve_media_stays_inside_the_root(client, path):
    assert media.resolve_media(path) is None
