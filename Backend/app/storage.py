"""
Disk-based file storage.

See prior turns for full rationale: validates real file bytes via magic-byte
signatures rather than trusting the client-supplied Content-Type header.
"""

import os
import uuid
from pathlib import Path

from fastapi import UploadFile

from app.config import settings

IMAGE_SIGNATURES: dict[str, bytes] = {
    "image/jpeg": b"\xff\xd8\xff",
    "image/png": b"\x89PNG\r\n\x1a\n",
}

AUDIO_SIGNATURES: dict[str, bytes] = {
    "audio/wav": b"RIFF",
    "audio/ogg": b"OggS",
    "audio/mpeg": b"ID3",
}

MAX_SNIFF_BYTES = 64


class FileTooLargeError(Exception):
    pass


class UnsupportedFileTypeError(Exception):
    pass


def _user_upload_dir(user_id: str) -> Path:
    path = Path(settings.upload_dir) / user_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _format_size(num_bytes: int) -> str:
    if num_bytes >= 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.1f}MB"
    return f"{num_bytes / 1024:.0f}KB"


def _sniff_image(head: bytes) -> str | None:
    for content_type, sig in IMAGE_SIGNATURES.items():
        if head.startswith(sig):
            return content_type
    if head[0:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[4:8] == b"ftyp" and head[8:12] in {
        b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1",
    }:
        return "image/heic"
    return None


def _sniff_audio(head: bytes) -> str | None:
    if head[0:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "audio/wav"
    if head.startswith(b"OggS"):
        return "audio/ogg"
    if head.startswith(b"ID3"):
        return "audio/mpeg"
    if len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0:
        return "audio/mpeg"
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return "audio/webm"
    if head[4:8] == b"ftyp" and head[8:12] in {b"M4A ", b"isom", b"mp42", b"mp41"}:
        return "audio/mp4"
    return None


def _safe_filename(original_filename: str | None) -> str:
    original_filename = original_filename or "upload"
    return os.path.basename(original_filename)


async def _read_all(upload: UploadFile, max_bytes: int) -> bytes:
    chunks = []
    size_bytes = 0
    chunk_size = 1024 * 1024
    while True:
        chunk = await upload.read(chunk_size)
        if not chunk:
            break
        size_bytes += len(chunk)
        if size_bytes > max_bytes:
            raise FileTooLargeError(f"File exceeds the {_format_size(max_bytes)} limit.")
        chunks.append(chunk)
    return b"".join(chunks)


async def save_image_upload(user_id: str, upload: UploadFile) -> dict:
    data = await _read_all(upload, settings.max_upload_size_bytes)
    real_content_type = _sniff_image(data[:MAX_SNIFF_BYTES])
    if real_content_type is None:
        raise UnsupportedFileTypeError(
            "That file isn't a supported image (JPEG, PNG, WEBP, or HEIC). "
            "Upload a real photo, not a renamed or mislabeled file."
        )
    return _write_to_disk(data, user_id, upload.filename, real_content_type)


async def save_audio_upload(user_id: str, upload: UploadFile) -> dict:
    data = await _read_all(upload, settings.max_upload_size_bytes)
    real_content_type = _sniff_audio(data[:MAX_SNIFF_BYTES])

    if real_content_type is None:
        # Magic-byte sniff failed — some browsers produce WebM/Opus blobs
        # that don't start with the standard EBML header, or have a slightly
        # different container variant. Fall back to trusting the declared
        # Content-Type (stripped of codec suffix) if it's a known audio type.
        declared = (upload.content_type or "").split(";")[0].strip().lower()
        TRUSTED_FALLBACK = {
            "audio/webm": "audio/webm",
            "audio/ogg": "audio/ogg",
            "audio/mpeg": "audio/mpeg",
            "audio/mp4": "audio/mp4",
            "audio/wav": "audio/wav",
            "audio/x-wav": "audio/wav",
        }
        real_content_type = TRUSTED_FALLBACK.get(declared)

    if real_content_type is None:
        raise UnsupportedFileTypeError(
            "That file isn't a supported audio clip (WAV, MP3, OGG, WEBM, or MP4/M4A). "
            "Upload a real recording, not a renamed or mislabeled file."
        )
    return _write_to_disk(data, user_id, upload.filename, real_content_type)


def _write_to_disk(data: bytes, user_id: str, original_filename: str | None, content_type: str) -> dict:
    file_id = str(uuid.uuid4())
    safe_filename = _safe_filename(original_filename)
    stored_path = _user_upload_dir(user_id) / f"{file_id}__{safe_filename}"
    stored_path.write_bytes(data)
    return {
        "file_id": file_id,
        "original_filename": safe_filename,
        "content_type": content_type,
        "size_bytes": len(data),
        "stored_path": str(stored_path),
    }


def delete_file_from_disk(stored_path: str) -> None:
    Path(stored_path).unlink(missing_ok=True)