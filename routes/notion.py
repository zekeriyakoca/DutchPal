"""Save a selected word to Notion. Replaces the .NET API's /vocabulary/{noun,verb}/upsert-to-notion."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from services.notion import insert_if_not_exists, notion_target, rich_text, rich_text_with_bold
from services.users import User, UserSettings
from utils.auth import optional_user
from utils.db import get_db

router = APIRouter()


class NounRecord(BaseModel):
    name: str = Field(min_length=1)
    meaning: str = ""
    pronunciation: str | None = None
    sentence: str = ""


class VerbRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(min_length=1)
    meaning: str = ""
    conjugations: str | None = None
    sentence: str | None = None
    past_tense: str | None = Field(default=None, alias="pastTense")


def user_settings(db: Session, user: User | None) -> UserSettings | None:
    return db.get(UserSettings, user.id) if user else None


def saved(count: int) -> dict:
    return {"message": "Record inserted or already exists.", "count": count}


@router.post("/notion/noun", tags=["Notion"])
async def save_noun(
    record: NounRecord, db: Session = Depends(get_db), user: User | None = Depends(optional_user)
):
    target = notion_target(user_settings(db, user), "noun")
    count = await insert_if_not_exists(
        target,
        record.name,
        {
            "Meaning": rich_text(record.meaning),
            "Pronunciation": rich_text(record.pronunciation or ""),
            "Sentence": rich_text_with_bold(record.sentence),
        },
    )
    return saved(count)


@router.post("/notion/verb", tags=["Notion"])
async def save_verb(
    record: VerbRecord, db: Session = Depends(get_db), user: User | None = Depends(optional_user)
):
    target = notion_target(user_settings(db, user), "verb")
    count = await insert_if_not_exists(
        target,
        record.name,
        {
            "Meaning": rich_text(record.meaning),
            "Conjugations": rich_text(record.conjugations or ""),
            "Sentence": rich_text_with_bold(record.sentence or ""),
            "Past Tense": rich_text(record.past_tense or ""),
        },
    )
    return saved(count)
