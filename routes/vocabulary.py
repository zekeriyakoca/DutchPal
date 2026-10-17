from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from utils.db import get_db
from utils.provider_errors import raise_openai_unavailable_if_provider_error
from typing import Optional
from services.app_service import (
    find_sentence_containing_word,
    get_vocabularies,
)

router = APIRouter()


class VocabRequest(BaseModel):
    message: str = ""
    level: str = "ALL LEVELS"
    number_of_entries: int = 1
    book_id: Optional[str] = None  # content book slug; narrows the examples
    word_type: Optional[str] = None


@router.post("/vocabulary")
async def get_vocabulary(req: VocabRequest, db: Session = Depends(get_db)):
    try:
        vocabularies = await get_vocabularies(
            db=db,
            word_to_search=req.message,
            limit=req.number_of_entries,
            cefr_level=req.level,
            pos=None if req.word_type == "ALL TYPES" else req.word_type,
        )
    except Exception as exc:
        raise_openai_unavailable_if_provider_error(exc)

    # get_vocabularies returns a message string when nothing matches.
    if isinstance(vocabularies, str):
        return {"items": []}

    # Stored rows as they are: no LLM, so nothing is reformatted or invented.
    # The vocabulary table has no translations.
    return {
        "items": [
            {
                "word": vocab["infinitive"] or vocab["lemma"],
                "lemma": vocab["lemma"],
                "pos": vocab["pos"],
                "cefr_level": vocab["cefr_level"],
                "present_form": vocab["present_form"],
                "v2_form": vocab["v2_form"],
                "v3_form": vocab["v3_form"],
                "examples": find_sentence_containing_word(
                    db=db,
                    word_forms=get_all_forms_of_word(vocab),
                    limit=2,
                    book_id=req.book_id,
                ),
            }
            for vocab in vocabularies
        ]
    }


def get_all_forms_of_word(vocab: dict) -> list[str]:
    """
    Get all forms of a word from the vocabulary dictionary.
    """
    return (
        [
            vocab["lemma"],
            *vocab["present_form"].split("/"),
            *vocab["v2_form"].split("/"),
            *vocab["v3_form"].split("/"),
        ]
        if vocab["pos"] == "verb"
        else [vocab["lemma"]]
    )
