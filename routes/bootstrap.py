from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from tools.agent import SessionLocal
from tools.embed import Book

router = APIRouter()


# Dependency to get the database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/bootstrap")
def get_bootstrap_data(db: Session = Depends(get_db)):
    """
    Endpoint to retrieve all book names and IDs.
    """
    books = db.query(Book).all()
    return {"book_options": [{"id": book.id, "name": book.title} for book in books]}
