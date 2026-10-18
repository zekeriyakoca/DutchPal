"""Read-only endpoints for the extracted book chapters (see docs/06-content-extraction.md).

They serve the content tables as stored, so the UI can render a chapter without any LLM.
Exercise answers stay in `payload`; the UI checks them client-side.
"""

from itertools import groupby

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import exists, func
from sqlalchemy.orm import Session
from tools.content.models import Chapter, Exercise
from utils.db import get_db

router = APIRouter()


@router.get("/content/books", tags=["Content"])
def list_books(db: Session = Depends(get_db)):
    """
    Books that have imported chapters, with their chapter count.
    """
    # max() so a book whose chapters were imported before it had a category still lists once.
    rows = (
        db.query(
            Chapter.book_id, Chapter.book_title, Chapter.book_cefr, func.max(Chapter.book_category), func.count(Chapter.id)
        )
        .group_by(Chapter.book_id, Chapter.book_title, Chapter.book_cefr)
        .order_by(Chapter.book_id)
        .all()
    )
    return [
        {"book_id": book_id, "title": title, "cefr": cefr, "category": category, "chapter_count": count}
        for book_id, title, cefr, category, count in rows
    ]


@router.get("/content/books/{book_id}/chapters", tags=["Content"])
def list_chapters(book_id: str, db: Session = Depends(get_db)):
    """
    Chapters of a book, ordered by number.
    """
    has_exercises = exists().where(Exercise.chapter_id == Chapter.id)
    rows = (
        db.query(
            Chapter.id,
            Chapter.number,
            Chapter.title,
            Chapter.goals,
            Chapter.duration_minutes,
            has_exercises.label("has_exercises"),
        )
        .filter(Chapter.book_id == book_id)
        .order_by(Chapter.number)
        .all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"Book '{book_id}' not found")
    return [
        {
            "id": r.id,
            "number": r.number,
            "title": r.title,
            "goals": r.goals,
            "duration_minutes": r.duration_minutes,
            "has_exercises": bool(r.has_exercises),
        }
        for r in rows
    ]


@router.get("/content/chapters/{chapter_id}", tags=["Content"])
def get_chapter(chapter_id: int, db: Session = Depends(get_db)):
    """
    A full chapter: dialogues, vocabulary lists, grammar topics and exercises in book order.
    """
    ch = db.get(Chapter, chapter_id)
    if ch is None:
        raise HTTPException(status_code=404, detail=f"Chapter {chapter_id} not found")

    vocab = sorted(ch.vocab_entries, key=lambda v: (v.list_position, v.item_position))
    vocabulary = []
    for _, entries in groupby(vocab, key=lambda v: v.list_position):
        entries = list(entries)
        vocabulary.append(
            {
                "list": entries[0].list_name,
                "book_page": entries[0].book_page,
                "generated": bool(entries[0].generated),
                "items": [
                    {"nl": v.nl, "lemma": v.lemma, "article": v.article, "form": v.form, "en": v.en}
                    for v in entries
                ],
            }
        )

    return {
        "id": ch.id,
        "book_id": ch.book_id,
        "book_title": ch.book_title,
        "number": ch.number,
        "title": ch.title,
        "goals": ch.goals,
        "note": ch.note,
        "duration_minutes": ch.duration_minutes,
        "book_pages": (
            [ch.book_page_first, ch.book_page_last] if ch.book_page_first is not None else None
        ),
        "dialogues": [
            {
                "id": d.source_id,
                "title": d.title,
                "audio_tracks": d.audio_tracks,
                "lines": d.lines,
                "new_words": d.new_words,
            }
            for d in sorted(ch.dialogues, key=lambda d: d.position)
        ],
        "vocabulary": vocabulary,
        "grammar": [
            {"id": g.source_id, "title": g.title, "book_page": g.book_page, "content": g.content}
            for g in sorted(ch.grammar_topics, key=lambda g: g.position)
        ],
        "exercises": [
            {
                "id": e.id,
                "label": e.label,
                "type": e.type,
                "instruction": e.instruction,
                "book_page": e.book_page,
                "answers_source": e.answers_source,
                "payload": e.payload,
            }
            for e in sorted(ch.exercises, key=lambda e: e.position)
        ],
        "culture": ch.culture,
        "reflection": ch.reflection,
    }
