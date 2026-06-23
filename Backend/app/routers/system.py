"""
System-level routes: health checks, version info. Nothing user-facing lives here.
"""

from fastapi import APIRouter

from app.config import settings
from app.database import get_db

router = APIRouter(tags=["system"])


@router.get("/healthz")
async def healthz():
    db_status = "ok"
    try:
        await get_db().command("ping")
    except Exception as e:
        db_status = f"error: {e}"

    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.app_env,
        "mongo": db_status,
    }