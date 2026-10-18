from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from services.word_lookup import WordLookup, lookup_word
from utils.db import get_db
from utils.provider_errors import raise_openai_unavailable_if_provider_error

router = APIRouter()


class WordLookupRequest(BaseModel):
    word: str = Field(min_length=1, max_length=60)


@router.post("/word/lookup", response_model=WordLookup)
async def word_lookup(req: WordLookupRequest, db: Session = Depends(get_db)):
    """
    A word from the book word lists, the vocabulary table and the Azure Translator dictionary;
    the LLM only fills the gaps.
    """
    try:
        return await lookup_word(db, req.word)
    except Exception as exc:
        raise_openai_unavailable_if_provider_error(exc)
