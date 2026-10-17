from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from tools.embed import Book
from utils.db import get_db

router = APIRouter()


@router.get("/bootstrap")
def get_bootstrap_data(db: Session = Depends(get_db)):
    """
    Endpoint to retrieve all book names and IDs.
    """
    books = db.query(Book).all()
    return {"book_options": [{"id": book.id, "name": book.title} for book in books]}
