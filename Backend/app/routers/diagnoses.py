"""
Diagnoses endpoints (Module 2b — input collection).

Flow from the frontend:
  1. If there's an image and/or audio file, upload each to POST /files first
     (already built — Module 0) and get back a file_id for each.
  2. Call POST /diagnoses with appliance_type, optional image_file_id,
     optional audio_file_id, optional symptom_text.

This router does NOT handle raw file uploads itself — that's intentionally
owned by files.py so it stays reusable. This router's only job is: validate
that any referenced file_id actually exists, belongs to the caller, and is
the right kind of file (image_file_id must point at an image, etc.), then
persist a diagnoses document.

No ML runs here — there are no trained models yet (Module 3). A diagnosis
is created with status="pending" and just sits there until that module
exists to process it.

GET /diagnoses        — list the signed-in user's own diagnoses, newest first
GET /diagnoses/{id}   — fetch one diagnosis the signed-in user owns
"""

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, status

from app.database import get_db
from app.models.diagnosis import (
    DiagnosisCreate,
    DiagnosisPublic,
    FaultGuess,
    new_diagnosis_document,
)
from app.security.current_user import CurrentUser, get_current_user

router = APIRouter(prefix="/diagnoses", tags=["diagnoses"])

ALLOWED_APPLIANCE_TYPES = {"fridge", "ac", "washer", "purifier", "camera"}


async def _get_owned_file(db, file_id: str, current_user_id: str, *, field_name: str) -> dict:
    """Looks up a files-collection document by id and confirms it belongs to
    the caller. Raises 400 (not 404) on any problem — from this router's
    point of view, a bad file_id is a bad request body, not a missing
    resource lookup."""
    if not ObjectId.is_valid(file_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} is not a valid file id.",
        )
    try:
        doc = await db.files.find_one({"_id": ObjectId(file_id)})
    except InvalidId:
        doc = None

    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} does not reference an uploaded file.",
        )
    if doc["user_id"] != current_user_id:
        # Don't confirm the file exists at all if it belongs to someone else.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} does not reference an uploaded file.",
        )
    return doc


@router.post("", response_model=DiagnosisPublic, status_code=status.HTTP_201_CREATED)
async def create_diagnosis(
    body: DiagnosisCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    if body.appliance_type not in ALLOWED_APPLIANCE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown appliance_type '{body.appliance_type}'. "
            f"Allowed: {sorted(ALLOWED_APPLIANCE_TYPES)}.",
        )

    cleaned_text = body.symptom_text.strip() if body.symptom_text else None
    has_image = bool(body.image_file_id)
    has_audio = bool(body.audio_file_id)
    has_text = bool(cleaned_text)

    if not (has_image or has_audio or has_text):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide at least one of: image_file_id, audio_file_id, or symptom_text.",
        )

    db = get_db()

    # appliance_id, if given, must belong to the caller too — same pattern.
    if body.appliance_id is not None:
        if not ObjectId.is_valid(body.appliance_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid appliance_id.")
        appliance_doc = await db.appliances.find_one({"_id": ObjectId(body.appliance_id)})
        if appliance_doc is None or appliance_doc["user_id"] != current_user.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid appliance_id.")

    if has_image:
        file_doc = await _get_owned_file(db, body.image_file_id, current_user.id, field_name="image_file_id")
        if not file_doc["content_type"].startswith("image/"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="image_file_id does not reference an image file.",
            )

    if has_audio:
        file_doc = await _get_owned_file(db, body.audio_file_id, current_user.id, field_name="audio_file_id")
        if not file_doc["content_type"].startswith("audio/"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="audio_file_id does not reference an audio file.",
            )

    body.symptom_text = cleaned_text
    doc = new_diagnosis_document(user_id=current_user.id, body=body)
    result = await db.diagnoses.insert_one(doc)

    return DiagnosisPublic(
        id=str(result.inserted_id),
        appliance_id=doc["appliance_id"],
        appliance_type=doc["appliance_type"],
        image_file_id=doc["image_file_id"],
        audio_file_id=doc["audio_file_id"],
        symptom_text=doc["symptom_text"],
        status=doc["status"],
        primary_fault=None,
        other_faults=[],
        created_at=doc["created_at"],
    )


def _doc_to_public(doc: dict) -> DiagnosisPublic:
    return DiagnosisPublic(
        id=str(doc["_id"]),
        appliance_id=doc.get("appliance_id"),
        appliance_type=doc["appliance_type"],
        image_file_id=doc.get("image_file_id"),
        audio_file_id=doc.get("audio_file_id"),
        symptom_text=doc.get("symptom_text"),
        status=doc["status"],
        primary_fault=FaultGuess(**doc["primary_fault"]) if doc.get("primary_fault") else None,
        other_faults=[FaultGuess(**f) for f in doc.get("other_faults", [])],
        created_at=doc["created_at"],
    )


@router.get("", response_model=list[DiagnosisPublic])
async def list_diagnoses(current_user: CurrentUser = Depends(get_current_user)):
    db = get_db()
    cursor = db.diagnoses.find({"user_id": current_user.id}).sort("created_at", -1)
    docs = await cursor.to_list(length=200)
    return [_doc_to_public(d) for d in docs]


@router.get("/{diagnosis_id}", response_model=DiagnosisPublic)
async def get_diagnosis(diagnosis_id: str, current_user: CurrentUser = Depends(get_current_user)):
    if not ObjectId.is_valid(diagnosis_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diagnosis not found.")

    db = get_db()
    try:
        doc = await db.diagnoses.find_one({"_id": ObjectId(diagnosis_id)})
    except InvalidId:
        doc = None

    if doc is None or doc["user_id"] != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diagnosis not found.")

    return _doc_to_public(doc)