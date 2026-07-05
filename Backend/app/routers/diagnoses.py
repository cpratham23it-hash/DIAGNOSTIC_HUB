"""
Diagnoses endpoints (Module 2b + Module 3 inference).

POST /diagnoses/{id}/analyze  — run the trained audio model against this diagnosis
                                 if it has an audio_file_id. Updates status and
                                 primary_fault in place. Returns the updated diagnosis.
"""

import asyncio
from pathlib import Path

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
AUDIO_SUPPORTED_APPLIANCES = {"fridge", "ac", "purifier", "washer"}


async def _get_owned_file(db, file_id: str, current_user_id: str, *, field_name: str) -> dict:
    if not ObjectId.is_valid(file_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field_name} is not a valid file id.")
    try:
        doc = await db.files.find_one({"_id": ObjectId(file_id)})
    except InvalidId:
        doc = None
    if doc is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field_name} does not reference an uploaded file.")
    if doc["user_id"] != current_user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field_name} does not reference an uploaded file.")
    return doc


@router.post("", response_model=DiagnosisPublic, status_code=status.HTTP_201_CREATED)
async def create_diagnosis(
    body: DiagnosisCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    if body.appliance_type not in ALLOWED_APPLIANCE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown appliance_type '{body.appliance_type}'. Allowed: {sorted(ALLOWED_APPLIANCE_TYPES)}.",
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

    if body.appliance_id is not None:
        if not ObjectId.is_valid(body.appliance_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid appliance_id.")
        appliance_doc = await db.appliances.find_one({"_id": ObjectId(body.appliance_id)})
        if appliance_doc is None or appliance_doc["user_id"] != current_user.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid appliance_id.")

    if has_image:
        file_doc = await _get_owned_file(db, body.image_file_id, current_user.id, field_name="image_file_id")
        if not file_doc["content_type"].startswith("image/"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="image_file_id does not reference an image file.")

    if has_audio:
        file_doc = await _get_owned_file(db, body.audio_file_id, current_user.id, field_name="audio_file_id")
        if not file_doc["content_type"].startswith("audio/"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="audio_file_id does not reference an audio file.")

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


@router.post("/{diagnosis_id}/analyze", response_model=DiagnosisPublic)
async def analyze_diagnosis(
    diagnosis_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Run the trained audio model against a saved diagnosis that has an
    audio_file_id. Updates status → 'done' and fills in primary_fault.

    Only covers fridge, ac, purifier (fan-type model).
    Returns 503 gracefully if the model file hasn't been trained yet.
    """
    if not ObjectId.is_valid(diagnosis_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diagnosis not found.")

    db = get_db()
    try:
        doc = await db.diagnoses.find_one({"_id": ObjectId(diagnosis_id)})
    except InvalidId:
        doc = None

    if doc is None or doc["user_id"] != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diagnosis not found.")

    if not doc.get("audio_file_id"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This diagnosis has no audio file to analyze.",
        )

    appliance_type = doc["appliance_type"]
    if appliance_type not in AUDIO_SUPPORTED_APPLIANCES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Audio analysis not available for '{appliance_type}'. "
                   f"Supported: {sorted(AUDIO_SUPPORTED_APPLIANCES)}.",
        )

    from app.ml.inference import model_is_available
    if not model_is_available(appliance_type):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The audio model hasn't been trained yet. Run  python ml/train.py  first.",
        )

    audio_file_doc = await db.files.find_one({"_id": ObjectId(doc["audio_file_id"])})
    if audio_file_doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio file no longer exists.")

    stored_path = Path(audio_file_doc["stored_path"])
    if not stored_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio file not found on disk.")

    await db.diagnoses.update_one(
        {"_id": ObjectId(diagnosis_id)},
        {"$set": {"status": "processing"}},
    )

    try:
        from app.ml.inference import get_classifier
        audio_bytes = stored_path.read_bytes()

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: get_classifier(appliance_type).predict(audio_bytes, appliance_type=appliance_type),
        )

        primary_fault = None
        if result.is_anomalous and result.fault_name:
            primary_fault = {
                "fault_name": result.fault_name,
                "confidence": result.confidence,
            }

        await db.diagnoses.update_one(
            {"_id": ObjectId(diagnosis_id)},
            {"$set": {
                "status": "done",
                "primary_fault": primary_fault,
                "other_faults": [],
                "analysis_message": result.message,
                "frames_analyzed": result.frames_analyzed,
                "anomaly_probability": result.anomaly_probability,
            }},
        )

    except Exception as e:
        await db.diagnoses.update_one(
            {"_id": ObjectId(diagnosis_id)},
            {"$set": {"status": "failed"}},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {str(e)}",
        )

    updated_doc = await db.diagnoses.find_one({"_id": ObjectId(diagnosis_id)})
    return _doc_to_public(updated_doc)


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