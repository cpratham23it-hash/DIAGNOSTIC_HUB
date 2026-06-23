"""
Disk-based file storage.

Files are saved to {UPLOAD_DIR}/{user_id}/{file_id}__{original_filename}.
Scoping by user_id from day one means access control later ("does this file
belong to the requesting user") is a simple path/metadata check, not a
restructure.

This is intentionally the ONLY place that knows files live on local disk.
Swapping to S3-style object storage later means rewriting save_upload_file()
and read_file_bytes() here — nothing in routers/files.py or any other module
should need to change, since they only deal with file_id and metadata.

--- Why this validates file CONTENT, not just the Content-Type header ---
upload.content_type is whatever the client's browser/HTTP request claims it
is. It is not verified by anything — a request can label a Word document
(.docx) as "image/jpeg" and the header alone would happily believe it. That
let non-image/audio files (e.g. .docx, .pdf) slip through what was meant to
be an images-and-audio-only upload system.

To actually enforce "this is really an image" / "this is really an audio
file," we sniff the first few bytes of the file content against known
magic-number signatures for each real format. The Content-Type header is
still recorded for display/download purposes (browsers need it to render
correctly), but it is NEVER trusted for the accept/reject decision — only
the sniffed bytes are.
"""

import os
import uuid
from pathlib import Path

from fastapi import UploadFile

from app.config import settings

# ── Real magic-byte signatures, keyed by the canonical content_type we'll
# report once a file matches. Checked against the start of the file's
# actual bytes — never against the client-supplied header.
IMAGE_SIGNATURES: dict[str, bytes] = {
    "image/jpeg": b"\xff\xd8\xff",
    "image/png": b"\x89PNG\r\n\x1a\n",
}
# WEBP and HEIC use a container format where the magic bytes aren't a
# simple fixed prefix — they need a small offset check, handled in
# _sniff_image() below rather than the simple dict above.

AUDIO_SIGNATURES: dict[str, bytes] = {
    "audio/wav": b"RIFF",  # followed by size, then "WAVE" at offset 8 — checked below
    "audio/ogg": b"OggS",
    "audio/mpeg": b"ID3",  # MP3 with an ID3 tag
}
# MP3 without an ID3 tag starts with a frame-sync byte pattern instead
# (0xFF Ex/Fx) and WEBM/MP4 audio use container formats — both handled
# with extra logic in _sniff_audio() below.

MAX_SNIFF_BYTES = 64  # more than enough to read every signature we check


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
    """Returns the real content_type if head matches a known image
    signature, else None."""
    for content_type, sig in IMAGE_SIGNATURES.items():
        if head.startswith(sig):
            return content_type

    # WEBP: "RIFF" + 4-byte size + "WEBP"
    if head[0:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"

    # HEIC/HEIF: ISO base media file format. Bytes 4-7 are "ftyp", then a
    # 4-char brand (heic, heix, hevc, mif1, msf1, etc).
    if head[4:8] == b"ftyp" and head[8:12] in {
        b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1",
    }:
        return "image/heic"

    return None


def _sniff_audio(head: bytes) -> str | None:
    """Returns the real content_type if head matches a known audio
    signature, else None."""
    if head[0:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "audio/wav"
    if head.startswith(b"OggS"):
        return "audio/ogg"
    if head.startswith(b"ID3"):
        return "audio/mpeg"
    # MP3 without ID3 tag: frame sync 0xFFEx/Fx where the low nibble of the
    # second byte is one of E,F (MPEG version + layer bits set).
    if len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0:
        return "audio/mpeg"
    # WEBM audio (Matroska/EBML container) — browsers recording via
    # MediaRecorder commonly produce this.
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return "audio/webm"
    # MP4/M4A container: "ftyp" box starting at byte 4, brand like M4A.
    if head[4:8] == b"ftyp" and head[8:12] in {b"M4A ", b"isom", b"mp42", b"mp41"}:
        return "audio/mp4"

    return None


def _safe_filename(original_filename: str | None) -> str:
    original_filename = original_filename or "upload"
    # Strip any path components a malicious filename might smuggle in
    return os.path.basename(original_filename)


async def _read_all(upload: UploadFile, max_bytes: int) -> bytes:
    """Reads the full upload into memory in chunks, enforcing the size cap
    as it goes so an oversized file is rejected before we hold all of it."""
    chunks = []
    size_bytes = 0
    chunk_size = 1024 * 1024  # 1 MB at a time

    while True:
        chunk = await upload.read(chunk_size)
        if not chunk:
            break
        size_bytes += len(chunk)
        if size_bytes > max_bytes:
            raise FileTooLargeError(
                f"File exceeds the {_format_size(max_bytes)} limit."
            )
        chunks.append(chunk)

    return b"".join(chunks)


async def save_image_upload(user_id: str, upload: UploadFile) -> dict:
    """
    Validates that the upload is really an image (by content, not by the
    claimed Content-Type header) and saves it to disk.

    Returns {file_id, original_filename, content_type, size_bytes, stored_path}.
    Raises UnsupportedFileTypeError if the bytes don't match a known image
    format, or FileTooLargeError if it exceeds the size cap.
    """
    data = await _read_all(upload, settings.max_upload_size_bytes)

    real_content_type = _sniff_image(data[:MAX_SNIFF_BYTES])
    if real_content_type is None:
        raise UnsupportedFileTypeError(
            "That file isn't a supported image (JPEG, PNG, WEBP, or HEIC). "
            "Upload a real photo, not a renamed or mislabeled file."
        )

    return _write_to_disk(data, user_id, upload.filename, real_content_type)


async def save_audio_upload(user_id: str, upload: UploadFile) -> dict:
    """
    Validates that the upload is really an audio file (by content, not by
    the claimed Content-Type header) and saves it to disk.

    Returns {file_id, original_filename, content_type, size_bytes, stored_path}.
    Raises UnsupportedFileTypeError if the bytes don't match a known audio
    format, or FileTooLargeError if it exceeds the size cap.
    """
    data = await _read_all(upload, settings.max_upload_size_bytes)

    real_content_type = _sniff_audio(data[:MAX_SNIFF_BYTES])
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