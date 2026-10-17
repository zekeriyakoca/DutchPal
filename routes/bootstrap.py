from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from tools.content.models import Chapter
from utils.db import get_db

router = APIRouter()


@router.get("/bootstrap")
def get_bootstrap_data(db: Session = Depends(get_db)):
    """
    Endpoint to retrieve the textbooks (slug and title) for the book selects.
    """
    books = (
        db.query(Chapter.book_id, Chapter.book_title)
        .distinct()
        .order_by(Chapter.book_id)
        .all()
    )
    return {"book_options": [{"id": book_id, "name": title} for book_id, title in books]}
