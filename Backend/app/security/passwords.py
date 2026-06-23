"""
Password hashing helpers.

Uses the bcrypt library directly rather than passlib — passlib's bcrypt
backend has a known compatibility break with current bcrypt versions
(it inspects bcrypt's internals in a way that no longer matches bcrypt's
current API), so we skip that layer entirely.

bcrypt has a hard 72-byte input limit per algorithm design. We enforce a
sane max password length up front so a very long password fails with a
clear error instead of being silently truncated.
"""

import bcrypt

MAX_PASSWORD_BYTES = 72


def hash_password(plain_password: str) -> str:
    if len(plain_password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes.")
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )
    except ValueError:
        # Malformed hash stored — treat as a failed verification, not a crash
        return False