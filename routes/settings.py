"""Per-user settings: the user's own Notion workspace (optional).

The Notion secret is stored encrypted (SETTINGS_ENCRYPTION_KEY) and never sent back;
the UI only learns whether one is set.
"""

import asyncio
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from services.notion import database_title
from services.users import User, UserSettings, decrypt_secret, encrypt_secret
from utils.auth import current_user
from utils.db import get_db

router = APIRouter()


class NotionSettings(BaseModel):
    secret: str | None = None  # empty keeps the saved secret
    noun_db_id: str = ""
    verb_db_id: str = ""


def settings_json(settings: UserSettings | None) -> dict:
    return {
        "notion": {
            "secret_set": bool(settings and settings.notion_secret_encrypted),
            "noun_db_id": settings.notion_noun_db_id if settings else None,
            "verb_db_id": settings.notion_verb_db_id if settings else None,
        }
    }


@router.get("/settings", tags=["Settings"])
def get_settings(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return settings_json(db.get(UserSettings, user.id))


@router.put("/settings/notion", tags=["Settings"])
def save_notion_settings(
    body: NotionSettings, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    settings = db.get(UserSettings, user.id) or UserSettings(user_id=user.id)
    secret = (body.secret or "").strip()
    if secret:
        if not os.getenv("SETTINGS_ENCRYPTION_KEY"):
            raise HTTPException(status_code=503, detail="Saving your own Notion is not configured on this server")
        settings.notion_secret_encrypted = encrypt_secret(secret)
    if not settings.notion_secret_encrypted:
        raise HTTPException(status_code=400, detail="Enter your Notion integration secret")
    settings.notion_noun_db_id = body.noun_db_id.strip() or None
    settings.notion_verb_db_id = body.verb_db_id.strip() or None
    db.add(settings)
    db.commit()
    return settings_json(settings)


@router.delete("/settings/notion", tags=["Settings"])
def use_default_notion(user: User = Depends(current_user), db: Session = Depends(get_db)):
    settings = db.get(UserSettings, user.id)
    if settings:
        settings.notion_secret_encrypted = settings.notion_noun_db_id = settings.notion_verb_db_id = None
        db.commit()
    return settings_json(settings)


@router.post("/settings/notion/test", tags=["Settings"])
async def test_notion(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """
    Opens the saved noun and verb databases with the saved secret and returns their titles.
    """
    settings = db.get(UserSettings, user.id)
    if not settings or not settings.notion_secret_encrypted:
        raise HTTPException(status_code=400, detail="Save your Notion settings first")
    secret = decrypt_secret(settings.notion_secret_encrypted)
    kinds = [k for k in ("noun", "verb") if getattr(settings, f"notion_{k}_db_id")]
    if not kinds:
        raise HTTPException(status_code=400, detail="Add a noun or verb database id first")
    titles = await asyncio.gather(
        *(database_title(secret, getattr(settings, f"notion_{k}_db_id")) for k in kinds)
    )
    return dict(zip(kinds, titles))
