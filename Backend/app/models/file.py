"""
Pydantic schemas for the files collection.

A "file" here means anything uploaded through POST /files — currently just
diagnosis images/audio, but kept generic since other modules may need
uploads later (e.g. technician verification documents).
"""

from datetime import datetime, timezone

from pydantic import BaseModel


class FilePublic(BaseModel):
    """Fields safe to return to the client — never includes the disk path."""

    id: str
    original_filename: str
    content_type: str
    size_bytes: int


def new_file_document(
    user_id: str,
    original_filename: str,
    content_type: str,
    size_bytes: int,
    stored_path: str,
) -> dict:
    """Shape of a file document as stored in MongoDB."""
    return {
        "user_id": user_id,
        "original_filename": original_filename,
        "content_type": content_type,
        "size_bytes": size_bytes,
        "stored_path": stored_path,
        "created_at": datetime.now(timezone.utc),
    }