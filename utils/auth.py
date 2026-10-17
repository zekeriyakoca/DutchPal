"""Session cookie and the `optional_user` / `current_user` dependencies.

The cookie holds `<user id>.<expiry>.<HMAC-SHA256>` signed with SESSION_SECRET; it is
httpOnly, Secure and SameSite=Lax, so the UI never sees or stores a token.
Without SESSION_SECRET nobody is signed in and the app works as it does anonymously.
"""

import hashlib
import hmac
import os
import time

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from services.users import User
from utils.db import get_db

SESSION_COOKIE = "dutchpal_session"
SESSION_MAX_AGE = 30 * 24 * 3600  # seconds


def _sign(value: str) -> str | None:
    secret = os.getenv("SESSION_SECRET")
    if not secret:
        return None
    signature = hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()
    return f"{value}.{signature}"


def set_session_cookie(response: Response, user_id: int) -> None:
    cookie = _sign(f"{user_id}.{int(time.time()) + SESSION_MAX_AGE}")
    if cookie is None:
        raise HTTPException(status_code=503, detail="Sign-in is not configured on this server")
    response.set_cookie(
        SESSION_COOKIE,
        cookie,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=True,
        samesite="lax",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, httponly=True, secure=True, samesite="lax")


def session_user_id(cookie: str | None) -> int | None:
    """The user id from a valid, unexpired session cookie, else None."""
    if not cookie or cookie.count(".") != 2:
        return None
    user_id, expires, _ = cookie.split(".")
    expected = _sign(f"{user_id}.{expires}")
    if expected is None or not hmac.compare_digest(expected, cookie):
        return None
    if not expires.isdigit() or int(expires) < time.time():
        return None
    return int(user_id)


def optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    user_id = session_user_id(request.cookies.get(SESSION_COOKIE))
    return db.get(User, user_id) if user_id is not None else None


def current_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Please sign in first")
    return user
