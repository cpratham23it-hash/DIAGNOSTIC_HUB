"""
Pydantic schemas for the users collection and auth request/response shapes.

Note: these are API/validation schemas, not a MongoDB ORM layer — MongoDB
documents are plain dicts in app/database.py usage. These models define
what a valid request looks like and what we promise to return.
"""

from datetime import datetime, timezone

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)


class SigninRequest(BaseModel):
    email: EmailStr
    password: str


class GoogleSignInRequest(BaseModel):
    credential: str  # the ID token JWT string returned by Google Identity Services


class UserPublic(BaseModel):
    """User fields safe to return to the client — never includes password_hash."""

    id: str
    name: str
    email: EmailStr


class AuthResponse(BaseModel):
    token: str
    user: UserPublic


def new_user_document(name: str, email: str, password_hash: str) -> dict:
    """Shape of a user document as stored in MongoDB (email/password signup)."""
    return {
        "name": name,
        "email": email,
        "password_hash": password_hash,
        "google_sub": None,
        "created_at": datetime.now(timezone.utc),
    }


def new_google_user_document(name: str, email: str, google_sub: str) -> dict:
    """
    Shape of a user document created via Google sign-in. No password_hash —
    this account can only ever sign in through Google, never via
    POST /auth/signin with a password.
    """
    return {
        "name": name,
        "email": email,
        "password_hash": None,
        "google_sub": google_sub,
        "created_at": datetime.now(timezone.utc),
    }