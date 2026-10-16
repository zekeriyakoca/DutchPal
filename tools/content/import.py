"""Load validated chapter JSON (content/<book>/chXX.json) into the content tables.

Usage: python tools/content/import.py content/nl-in-gang/ch*.json [--allow-remote]

Idempotent: chapters are matched on (book_id, number) and their rows on the JSON ids
(or list/item position for vocabulary), so re-running updates rows in place and removes
rows that are no longer in the file. Row ids stay stable across re-imports.
Chapters with validation errors are refused. Only a local DATABASE_URL is used unless
--allow-remote is passed.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, delete, func, select, tuple_
from sqlalchemy.dialects.postgresql import insert

from models import Base, Chapter, Dialogue, Exercise, GrammarTopic, VocabEntry
from validate import validate

env_file = ".env.production" if os.getenv("ENV") == "production" else ".env"
load_dotenv(env_file)

LOCAL_HOSTS = {None, "", "localhost", "127.0.0.1", "::1"}
GRAMMAR_FIELDS = {"id", "title", "book_page"}
EXERCISE_FIELDS = {"id", "label", "book_page", "type", "instruction", "answers_source"}


def upsert(conn, model, rows, key):
    """Insert rows, updating the existing row on a conflict over the `key` columns."""
    if not rows:
        return
    stmt = insert(model).values(rows)
    update = {c: stmt.excluded[c] for c in rows[0] if c not in key}
    conn.execute(stmt.on_conflict_do_update(index_elements=key, set_=update))


def prune(conn, model, chapter_id, key, keep):
    """Delete the chapter's rows whose `key` is not in `keep` (removed from the JSON)."""
    columns = [getattr(model, c) for c in key]
    stmt = delete(model).where(model.chapter_id == chapter_id)
    if keep:
        target = columns[0] if len(columns) == 1 else tuple_(*columns)
        stmt = stmt.where(target.not_in(keep))
    conn.execute(stmt)


def import_chapter(conn, data: dict) -> int:
    book, ch = data["book"], data["chapter"]
    pdf_pages = ch.get("pdf_pages") or [None, None]
    book_pages = ch.get("book_pages") or [None, None]
    chapter_row = {
        "book_id": book["id"],
        "book_title": book["title"],
        "book_cefr": book.get("cefr"),
        "number": ch["number"],
        "title": ch["title"],
        "schema_version": data["schema_version"],
        "pdf_page_first": pdf_pages[0],
        "pdf_page_last": pdf_pages[1],
        "book_page_first": book_pages[0],
        "book_page_last": book_pages[1],
        "goals": ch.get("goals", []),
        "culture": data.get("culture", []),
        "reflection": data.get("reflection"),
    }
    stmt = insert(Chapter).values(chapter_row)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_chapters_book_number",
        set_={**{c: stmt.excluded[c] for c in chapter_row}, "imported_at": func.now()},
    ).returning(Chapter.id)
    chapter_id = conn.execute(stmt).scalar_one()

    dialogues = [
        {
            "chapter_id": chapter_id,
            "source_id": d["id"],
            "position": i,
            "title": d.get("title"),
            "book_page": d.get("book_page"),
            "audio_tracks": d.get("audio_tracks", []),
            "lines": d["lines"],
        }
        for i, d in enumerate(data.get("dialogues", []))
    ]

    vocab = [
        {
            "chapter_id": chapter_id,
            "list_position": li,
            "item_position": ii,
            "list_name": vlist.get("list"),
            "book_page": vlist.get("book_page"),
            "nl": item["nl"],
            "lemma": item["lemma"],
            "article": item.get("article"),
            "form": item.get("form"),
            "en": item["en"],
        }
        for li, vlist in enumerate(data.get("vocabulary", []))
        for ii, item in enumerate(vlist["items"])
    ]

    grammar = [
        {
            "chapter_id": chapter_id,
            "source_id": g["id"],
            "position": i,
            "title": g["title"],
            "book_page": g.get("book_page"),
            "content": {k: v for k, v in g.items() if k not in GRAMMAR_FIELDS},
        }
        for i, g in enumerate(data.get("grammar", []))
    ]

    exercises = [
        {
            "chapter_id": chapter_id,
            "source_id": e["id"],
            "position": i,
            "label": e.get("label"),
            "book_page": e.get("book_page"),
            "type": e["type"],
            "instruction": e.get("instruction"),
            "answers_source": e.get("answers_source"),
            "payload": {k: v for k, v in e.items() if k not in EXERCISE_FIELDS},
        }
        for i, e in enumerate(data.get("exercises", []))
    ]

    for model, rows, key in (
        (Dialogue, dialogues, ["chapter_id", "source_id"]),
        (VocabEntry, vocab, ["chapter_id", "list_position", "item_position"]),
        (GrammarTopic, grammar, ["chapter_id", "source_id"]),
        (Exercise, exercises, ["chapter_id", "source_id"]),
    ):
        upsert(conn, model, rows, key)
        own_key = key[1:]
        keep = [r[own_key[0]] if len(own_key) == 1 else tuple(r[c] for c in own_key) for r in rows]
        prune(conn, model, chapter_id, own_key, keep)
    return chapter_id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--allow-remote", action="store_true", help="allow a non-local DATABASE_URL")
    args = parser.parse_args()

    engine = create_engine(os.environ["DATABASE_URL"])
    if engine.url.host not in LOCAL_HOSTS and not args.allow_remote:
        print(f"Refusing to import into non-local database host '{engine.url.host}' (pass --allow-remote).")
        return 1

    chapters = []
    for path in args.files:
        errors, _, _ = validate(path)
        if errors:
            print(f"{path}: {len(errors)} validation errors, fix them first (tools/content/validate.py)")
            return 1
        chapters.append((path, json.loads(path.read_text(encoding="utf-8"))))

    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for path, data in chapters:
            chapter_id = import_chapter(conn, data)
            print(f"{path}: chapter {data['chapter']['number']} -> chapters.id {chapter_id}")

        print("\nRow counts:")
        for model in (Chapter, Dialogue, VocabEntry, GrammarTopic, Exercise):
            count = conn.execute(select(func.count()).select_from(model)).scalar_one()
            print(f"  {model.__tablename__}: {count}")
        review = conn.execute(
            select(func.count()).where(Exercise.answers_source == "generated_needs_review")
        ).scalar_one()
        print(f"  exercises with answers_source=generated_needs_review: {review}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
