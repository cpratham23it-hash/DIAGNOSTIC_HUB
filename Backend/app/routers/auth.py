"""
Auth endpoints: signup and signin against the MongoDB users collection,
plus /auth/me to verify a session token and return the current user.

Google OAuth sign-in is added in Step 5 as a third endpoint here
(POST /auth/google) — not built yet.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.database import get_db
from app.models.user import (
    AuthResponse,
    GoogleSignInRequest,
    SigninRequest,
    SignupRequest,
    UserPublic,
    new_google_user_document,
    new_user_document,
)
from app.security.current_user import CurrentUser, get_current_user
from app.security.google_oauth import GoogleTokenError, verify_google_token
from app.security.passwords import hash_password, verify_password
from app.security.tokens import create_session_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def signup(body: SignupRequest):
    db = get_db()

    existing = await db.users.find_one({"email": body.email})
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    try:
        password_hash = hash_password(body.password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    doc = new_user_document(name=body.name, email=body.email, password_hash=password_hash)
    result = await db.users.insert_one(doc)
    user_id = str(result.inserted_id)

    token = create_session_token(user_id=user_id, email=body.email)
    return AuthResponse(
        token=token,
        user=UserPublic(id=user_id, name=body.name, email=body.email),
    )


@router.post("/signin", response_model=AuthResponse)
async def signin(body: SigninRequest):
    db = get_db()

    user = await db.users.find_one({"email": body.email})
    if user is None or user.get("password_hash") is None:
        # Same error for "no such user" and "wrong password" — avoids
        # leaking which emails are registered.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )

    if not verify_password(body.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )

    user_id = str(user["_id"])
    token = create_session_token(user_id=user_id, email=user["email"])
    return AuthResponse(
        token=token,
        user=UserPublic(id=user_id, name=user["name"], email=user["email"]),
    )


@router.get("/me", response_model=UserPublic)
async def get_me(current_user: CurrentUser = Depends(get_current_user)):
    """
    The first protected route. Requires a valid Authorization: Bearer token
    (issued by /auth/signup or /auth/signin). Returns whoever that token
    belongs to — useful for the frontend to confirm a stored token is still
    valid and to fetch fresh user info (e.g. on dashboard load).
    """
    return UserPublic(id=current_user.id, name=current_user.name, email=current_user.email)


@router.post("/google", response_model=AuthResponse)
async def google_signin(body: GoogleSignInRequest):
    """
    Sign in (or sign up, on first use) via Google.

    The frontend obtains a Google ID token via Google Identity Services and
    sends it here as 'credential'. We verify it really came from Google and
    really was issued for THIS app, then either:
      - find an existing user with that email and log them in (linking the
        Google identity onto that account if it didn't have one yet), or
      - create a brand new user, since this is their first time signing in.
    """
    try:
        idinfo = verify_google_token(body.credential)
    except GoogleTokenError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    email = idinfo.get("email")
    google_sub = idinfo.get("sub")
    name = idinfo.get("name") or (email.split("@")[0] if email else "User")

    if not email or not google_sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google token did not include the expected account info.",
        )

    db = get_db()
    user = await db.users.find_one({"email": email})

    if user is None:
        # First time this email has been seen — create a new account
        doc = new_google_user_document(name=name, email=email, google_sub=google_sub)
        result = await db.users.insert_one(doc)
        user_id = str(result.inserted_id)
    else:
        user_id = str(user["_id"])
        name = user["name"]  # keep the name already on file, don't overwrite silently
        if not user.get("google_sub"):
            # Existing email/password account signing in with Google for the
            # first time — link the two instead of creating a duplicate user.
            await db.users.update_one(
                {"_id": user["_id"]}, {"$set": {"google_sub": google_sub}}
            )

    token = create_session_token(user_id=user_id, email=email)
    return AuthResponse(token=token, user=UserPublic(id=user_id, name=name, email=email))