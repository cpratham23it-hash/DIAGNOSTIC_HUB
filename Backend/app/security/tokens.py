"""
Session tokens (JWT), issued after a successful signup/signin and required
on every protected endpoint going forward.

Pulled forward from what was planned as "Step 4" because signup/signin are
not actually useful without returning something the frontend can use to
stay signed in. Step 4 will mainly add the FastAPI dependency that *reads*
this token on protected routes — the issuing/verifying logic itself lives
here, already complete.
"""

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.config import settings

ALGORITHM = "HS256"


def create_session_token(user_id: str, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.session_expire_minutes
    )
    payload = {"sub": user_id, "email": email, "exp": expire}
    return jwt.encode(payload, settings.session_secret, algorithm=ALGORITHM)


def decode_session_token(token: str) -> dict:
    """
    Raises jose.JWTError (expired, bad signature, malformed) if the token
    is invalid. Callers (e.g. the auth dependency in Step 4) catch this.
    """
    return jwt.decode(token, settings.session_secret, algorithms=[ALGORITHM])