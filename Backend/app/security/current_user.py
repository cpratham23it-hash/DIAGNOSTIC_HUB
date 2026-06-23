"""
Auth dependency — the thing every protected route will declare to require
sign-in.

Usage in a route:

    from app.security.current_user import get_current_user, CurrentUser

    @router.get("/diagnoses")
    async def list_diagnoses(user: CurrentUser = Depends(get_current_user)):
        ...  # user.id, user.email are available here

How it works:
  1. FastAPI's HTTPBearer extracts the token from the "Authorization: Bearer <token>" header.
  2. We decode/verify the JWT (signature + expiry) using the same secret it was signed with.
  3. We look the user up in MongoDB by the id embedded in the token (the "sub" claim) —
     this catches tokens for users who were deleted after the token was issued.
  4. If any step fails, we raise 401 — never 500 — since an invalid/expired token
     is a normal, expected client error, not a server fault.
"""

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from pydantic import BaseModel

from app.database import get_db
from app.security.tokens import decode_session_token

_bearer_scheme = HTTPBearer(auto_error=False)


class CurrentUser(BaseModel):
    id: str
    name: str
    email: str


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> CurrentUser:
    if credentials is None:
        raise _unauthorized("Not authenticated. Include an Authorization: Bearer token.")

    try:
        payload = decode_session_token(credentials.credentials)
    except JWTError:
        raise _unauthorized("Invalid or expired session token.")

    user_id = payload.get("sub")
    if not user_id or not ObjectId.is_valid(user_id):
        raise _unauthorized("Invalid session token.")

    db = get_db()
    try:
        user = await db.users.find_one({"_id": ObjectId(user_id)})
    except InvalidId:
        raise _unauthorized("Invalid session token.")

    if user is None:
        # Token is well-formed and unexpired, but the user no longer exists
        # (e.g. account deleted) — must still be rejected.
        raise _unauthorized("User account no longer exists.")

    return CurrentUser(id=str(user["_id"]), name=user["name"], email=user["email"])