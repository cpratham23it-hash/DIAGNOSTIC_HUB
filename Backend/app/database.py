"""
MongoDB connection, set up once at app startup and reused everywhere.

We use Motor (the async MongoDB driver) instead of plain PyMongo because
FastAPI is async — a sync driver would block the event loop on every
database call, which defeats the point of using FastAPI at all.

Usage in other files:
    from app.database import get_db
    db = get_db()
    await db.users.find_one({"email": email})
"""

from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings

_client: AsyncIOMotorClient | None = None


def connect_to_mongo() -> None:
    """Called once on app startup (see main.py)."""
    global _client
    _client = AsyncIOMotorClient(settings.mongo_uri)


def close_mongo_connection() -> None:
    """Called once on app shutdown (see main.py)."""
    global _client
    if _client is not None:
        _client.close()
        _client = None


def get_db():
    """
    Returns the database handle. Collections are accessed as attributes,
    e.g. get_db().users, get_db().diagnoses — MongoDB creates them
    automatically on first write, no migration step needed.
    """
    if _client is None:
        raise RuntimeError(
            "MongoDB client not initialized. connect_to_mongo() must run at app startup."
        )
    return _client[settings.mongo_db_name]