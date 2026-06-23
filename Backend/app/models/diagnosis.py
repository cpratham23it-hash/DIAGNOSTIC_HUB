"""
Pydantic schemas for the diagnoses collection.

This is the central record of the whole app. Module 2b creates one when a
user submits image/audio/text input. Module 3 fills in the result fields
once a real model (or, for now, a stub) produces a prediction. Module 4
aggregates over a user's diagnoses for appliance health. Module 5/6 reference
a diagnosis_id when a booking or cost estimate is tied back to "the thing
that prompted this."

NOT populated by any endpoint yet — this file only defines the shape.
Module 2b's first real endpoint (POST /diagnoses) will use these.
"""

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel

DiagnosisStatus = Literal["pending", "processing", "done", "failed"]


class FaultGuess(BaseModel):
    """One entry in the ranked list of possible causes."""

    fault_name: str
    confidence: float  # 0-100


class DiagnosisCreate(BaseModel):
    appliance_id: Optional[str] = None  # nullable: a one-off diagnosis not tied to a saved appliance
    appliance_type: Literal["fridge", "ac", "washer", "purifier", "camera"]
    image_file_id: Optional[str] = None
    audio_file_id: Optional[str] = None
    symptom_text: Optional[str] = None


class DiagnosisPublic(BaseModel):
    id: str
    appliance_id: Optional[str] = None
    appliance_type: str
    image_file_id: Optional[str] = None
    audio_file_id: Optional[str] = None
    symptom_text: Optional[str] = None
    status: DiagnosisStatus
    primary_fault: Optional[FaultGuess] = None
    other_faults: list[FaultGuess] = []
    created_at: datetime


def new_diagnosis_document(user_id: str, body: DiagnosisCreate) -> dict:
    return {
        "user_id": user_id,
        "appliance_id": body.appliance_id,
        "appliance_type": body.appliance_type,
        "image_file_id": body.image_file_id,
        "audio_file_id": body.audio_file_id,
        "symptom_text": body.symptom_text,
        "status": "pending",
        # Filled in once Module 3 (or its stub) produces a result:
        "primary_fault": None,
        "other_faults": [],
        "created_at": datetime.now(timezone.utc),
    }