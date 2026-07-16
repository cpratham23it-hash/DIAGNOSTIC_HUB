"""
Diagnoses endpoints (Module 2b + Module 3 inference + text analysis).

POST /diagnoses/{id}/analyze  — runs available analysis:
  - Audio: silence detection + ML model if available
  - Text: TF-IDF matching against fault library
  - Fusion: audio wins if confident, text fills in if audio inconclusive
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
        analysis_message=doc.get("analysis_message"),
        cost_min=doc.get("cost_min"),
        cost_max=doc.get("cost_max"),
        created_at=doc["created_at"],
    )


@router.post("/{diagnosis_id}/analyze", response_model=DiagnosisPublic)
async def analyze_diagnosis(
    diagnosis_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Multi-signal analysis:
    - Audio (if present + supported appliance): silence detection + ML model
    - Text (if present): TF-IDF matching against fault library
    - Fusion: audio wins if confident, text fills in if audio inconclusive/absent
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

    appliance_type = doc["appliance_type"]
    symptom_text = doc.get("symptom_text", "")
    has_audio = bool(doc.get("audio_file_id"))
    has_text = bool(symptom_text and symptom_text.strip())

    await db.diagnoses.update_one(
        {"_id": ObjectId(diagnosis_id)},
        {"$set": {"status": "processing"}},
    )

    primary_fault = None
    text_other_faults = []
    analysis_message = "No inputs available for analysis."
    anomaly_probability = None
    frames_analyzed = 0

    try:
        # ── AUDIO ─────────────────────────────────────────────────────────────
        audio_result = None
        if has_audio and appliance_type in AUDIO_SUPPORTED_APPLIANCES:
            from app.ml.inference import model_is_available, get_classifier
            if model_is_available(appliance_type):
                audio_file_doc = await db.files.find_one({"_id": ObjectId(doc["audio_file_id"])})
                if audio_file_doc:
                    stored_path = Path(audio_file_doc["stored_path"])
                    if stored_path.exists():
                        audio_bytes = stored_path.read_bytes()
                        loop = asyncio.get_event_loop()
                        audio_result = await loop.run_in_executor(
                            None,
                            lambda: get_classifier(appliance_type).predict(
                                audio_bytes, appliance_type=appliance_type
                            ),
                        )
                        frames_analyzed = audio_result.frames_analyzed
                        anomaly_probability = audio_result.anomaly_probability
                        analysis_message = audio_result.message

                        if audio_result.is_anomalous and audio_result.fault_name:
                            primary_fault = {
                                "fault_name": audio_result.fault_name,
                                "confidence": audio_result.confidence,
                            }

        # ── TEXT + IMAGE ──────────────────────────────────────────────────────
        # Run LLM analysis when text or image is present — enriches audio results
        has_image = bool(doc.get("image_file_id"))
        if has_text or has_image:
            from app.services.text_analysis import analyze_symptom_text

            fault_cursor = db.faults.find({"appliance_type": appliance_type})
            fault_docs = await fault_cursor.to_list(length=100)

            # Read image bytes if uploaded
            image_bytes = None
            image_content_type = None
            if has_image:
                image_file_doc = await db.files.find_one({"_id": ObjectId(doc["image_file_id"])})
                if image_file_doc:
                    img_path = Path(image_file_doc["stored_path"])
                    if img_path.exists():
                        image_bytes = img_path.read_bytes()
                        image_content_type = image_file_doc.get("content_type", "image/jpeg")

            if fault_docs:
                loop = asyncio.get_event_loop()
                try:
                    text_result = await loop.run_in_executor(
                        None,
                        lambda: analyze_symptom_text(
                            symptom_text=symptom_text or "",
                            appliance_type=appliance_type,
                            fault_docs=fault_docs,
                            image_bytes=image_bytes,
                            image_content_type=image_content_type,
                        ),
                    )
                except Exception as text_err:
                    print(f"[analyze] text/image analysis failed (non-fatal): {text_err}")
                    text_result = None

                if text_result and text_result.is_valid_query is False:
                    # Text was gibberish/unrelated — keep audio result as-is
                    if primary_fault is None:
                        analysis_message = text_result.message

                elif text_result and text_result.fault_name:
                    # Text analysis found faults
                    text_other_faults = [
                        {"fault_name": f.fault_name, "confidence": f.confidence}
                        for f in text_result.other_faults
                    ]

                    if primary_fault is not None:
                        # Audio already set primary — use text for description + other_faults
                        analysis_message = text_result.message
                        # Add text primary as an other_fault if different from audio primary
                        if text_result.fault_name != primary_fault["fault_name"]:
                            text_other_faults.insert(0, {
                                "fault_name": text_result.fault_name,
                                "confidence": text_result.confidence,
                            })
                    else:
                        # No audio fault — text is the primary source
                        primary_fault = {
                            "fault_name": text_result.fault_name,
                            "confidence": text_result.confidence,
                        }
                        if audio_result and not audio_result.is_anomalous:
                            analysis_message = (
                                f"Audio analysis was inconclusive. "
                                f"Based on your description: {text_result.message}"
                            )
                        else:
                            analysis_message = text_result.message

                elif text_result:
                    # Text ran but found nothing confident
                    if primary_fault is None:
                        analysis_message = (
                            text_result.message or
                            "Your description did not closely match any known fault patterns. "
                            "Try describing the sound, smell, or behavior in more detail."
                        )

        # ── COST ESTIMATION ───────────────────────────────────────────────────
        # Look up the matched fault's cost range from the faults collection
        cost_min = None
        cost_max = None
        if primary_fault:
            fault_doc = await db.faults.find_one({
                "appliance_type": appliance_type,
                "name": primary_fault["fault_name"],
            })
            if fault_doc:
                cost_min = fault_doc.get("typical_cost_min")
                cost_max = fault_doc.get("typical_cost_max")

        update = {
            "status": "done",
            "primary_fault": primary_fault,
            "other_faults": text_other_faults,
            "analysis_message": analysis_message,
            "cost_min": cost_min,
            "cost_max": cost_max,
        }
        if anomaly_probability is not None:
            update["anomaly_probability"] = anomaly_probability
        if frames_analyzed:
            update["frames_analyzed"] = frames_analyzed

        await db.diagnoses.update_one(
            {"_id": ObjectId(diagnosis_id)},
            {"$set": update},
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