"""
Verifies a Google ID token (the 'credential' string returned by Google
Identity Services in the browser after a successful Google sign-in).

This checks three things, all handled internally by google.oauth2.id_token:
  1. The token's signature is valid (signed by Google's actual private keys)
  2. The token hasn't expired
  3. The token's "aud" (audience) claim matches OUR app's Client ID —
     without this check, a token issued for some other app would be accepted here too
"""

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from app.config import settings


class GoogleTokenError(Exception):
    pass


def verify_google_token(credential: str) -> dict:
    """
    Returns Google's decoded payload (contains email, name, picture, sub, etc.)
    if valid. Raises GoogleTokenError otherwise.
    """
    try:
        idinfo = google_id_token.verify_oauth2_token(
            credential, google_requests.Request(), settings.google_client_id
        )
    except ValueError as e:
        raise GoogleTokenError(str(e))

    if not idinfo.get("email_verified", False):
        raise GoogleTokenError("Google account email is not verified.")

    return idinfo