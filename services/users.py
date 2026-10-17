"""Signed-in users and their settings.

Own declarative Base (like tools/content/models.py), so `create_all` on startup only
creates these two tables when they are missing and never touches anything else.
Column types are kept generic so the tests can run them on SQLite.
"""

import os

from cryptography.fernet import Fernet
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    google_sub = Column(String, nullable=False, unique=True)  # Google's stable account id
    email = Column(String, nullable=False)
    name = Column(String, nullable=True)
    picture = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_login_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class UserSettings(Base):
    __tablename__ = "user_settings"
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    notion_secret_encrypted = Column(Text, nullable=True)  # Fernet token, see encrypt_secret
    notion_noun_db_id = Column(String, nullable=True)
    notion_verb_db_id = Column(String, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


def _fernet() -> Fernet:
    key = os.getenv("SETTINGS_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("SETTINGS_ENCRYPTION_KEY is not set")
    return Fernet(key)


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt_secret(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()
