"""
Generic file upload/retrieval endpoints.

POST /files   — upload a diagnosis image or audio clip, get back a file_id
GET  /files/{file_id} — download a file you previously uploaded

Module 2b calls POST /files when someone submits a diagnosis, then stores
the returned file_id(s) on the diagnoses document — this router doesn't know
or care about diagnoses at all, intentionally, so it stays reusable.

The caller declares which kind of file it's sending via the `kind` field
("image" or "audio"). That's not just bookkeeping — it picks which real
validation runs in storage.py (save_image_upload vs save_audio_upload),
each of which checks the file's actual bytes against known image/audio
signatures. A Word doc, PDF, or any other file type is rejected regardless
of what Content-Type header the request claims, and an audio file sent as
kind="image" (or vice versa) is rejected too — image input only ever
accepts images, audio input only ever accepts audio.
"""

from typing import Literal

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from app.database import get_db
from app.models.file import FilePublic, new_file_document
from app.security.current_user import CurrentUser, get_current_user
from app.storage import (
    FileTooLargeError,
    UnsupportedFileTypeError,
    save_audio_upload,
    save_image_upload,
)

router = APIRouter(prefix="/files", tags=["files"])


@router.post("", response_model=FilePublic, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile,
    kind: Literal["image", "audio"] = Form(...),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        if kind == "image":
            saved = await save_image_upload(user_id=current_user.id, upload=file)
        else:
            saved = await save_audio_upload(user_id=current_user.id, upload=file)
    except UnsupportedFileTypeError as e:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(e))
    except FileTooLargeError as e:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=str(e))

    db = get_db()
    doc = new_file_document(
        user_id=current_user.id,
        original_filename=saved["original_filename"],
        content_type=saved["content_type"],
        size_bytes=saved["size_bytes"],
        stored_path=saved["stored_path"],
    )
    result = await db.files.insert_one(doc)

    return FilePublic(
        id=str(result.inserted_id),
        original_filename=doc["original_filename"],
        content_type=doc["content_type"],
        size_bytes=doc["size_bytes"],
    )


@router.get("/{file_id}")
async def get_file(
    file_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    if not ObjectId.is_valid(file_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")

    db = get_db()
    try:
        doc = await db.files.find_one({"_id": ObjectId(file_id)})
    except InvalidId:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")

    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")

    if doc["user_id"] != current_user.id:
        # Same 404 as "doesn't exist" — don't reveal that a file exists but
        # belongs to someone else.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")

    return FileResponse(
        path=doc["stored_path"],
        media_type=doc["content_type"],
        filename=doc["original_filename"],
    )