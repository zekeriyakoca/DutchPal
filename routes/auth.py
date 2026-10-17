"""Optional Google sign-in. Everything else in the API keeps working without it."""

import os

from fastapi import APIRouter, Depends, HTTPException, Response
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from services.users import User
from utils.auth import clear_session_cookie, optional_user, set_session_cookie
from utils.db import get_db

router = APIRouter()


class GoogleSignIn(BaseModel):
    credential: str = Field(min_length=1)  # the ID token from Google Identity Services


def user_json(user: User) -> dict:
    return {
        "email": user.email,
        "name": user.name,
        "picture": user.picture,
        "created_at": user.created_at,
    }


@router.post("/auth/google", tags=["Auth"])
def sign_in_with_google(body: GoogleSignIn, response: Response, db: Session = Depends(get_db)):
    """
    Verifies a Google ID token, creates or updates the user and sets the session cookie.
    """
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id or not os.getenv("SESSION_SECRET"):
        raise HTTPException(status_code=503, detail="Sign-in is not configured on this server")
    try:
        claims = id_token.verify_oauth2_token(body.credential, google_requests.Request(), client_id)
    except ValueError:
        raise HTTPException(status_code=401, detail="Google sign-in failed. Please try again.")

    user = db.query(User).filter(User.google_sub == claims["sub"]).one_or_none()
    if user is None:
        user = User(google_sub=claims["sub"])
        db.add(user)
    user.email = claims["email"]
    user.name = claims.get("name")
    user.picture = claims.get("picture")
    user.last_login_at = func.now()
    db.commit()
    db.refresh(user)

    set_session_cookie(response, user.id)
    return user_json(user)


@router.get("/auth/me", tags=["Auth"])
def me(user: User | None = Depends(optional_user)):
    """
    Whether someone is signed in, and who.
    """
    return {"is_authenticated": user is not None, "user": user_json(user) if user else None}


@router.post("/auth/logout", tags=["Auth"])
def logout(response: Response):
    clear_session_cookie(response)
    return {"status": "ok"}
