"""
Pydantic schemas for the faults collection.

This is the reference library — "what faults exist for this appliance type,
and what does each one typically cost to fix." Module 3's models classify
INTO this list; without it populated, there's nothing for a prediction to
point to. Module 1's symptom-checker tree also resolves to entries here.

typical_symptoms is a short list of plain-language signatures (e.g. "loud
clicking near compressor", "burning smell", "ice buildup on back panel")
that Module 1's decision tree and, later, Module 3's text/NLP matching can
search against. This is intentionally free text, not a controlled
vocabulary — there's no taxonomy work done yet to justify anything stricter.
"""

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field

ApplianceType = Literal["fridge", "ac", "washer", "purifier", "camera"]
Severity = Literal["low", "medium", "high"]


class FaultCreate(BaseModel):
    appliance_type: ApplianceType
    name: str  # e.g. "Compressor Strain"
    description: str
    severity: Severity
    typical_symptoms: list[str] = Field(default_factory=list)
    typical_cost_min: Optional[float] = None
    typical_cost_max: Optional[float] = None


class FaultPublic(BaseModel):
    id: str
    appliance_type: ApplianceType
    name: str
    description: str
    severity: Severity
    typical_symptoms: list[str] = []
    typical_cost_min: Optional[float] = None
    typical_cost_max: Optional[float] = None
    created_at: datetime


def new_fault_document(body: FaultCreate) -> dict:
    return {
        "appliance_type": body.appliance_type,
        "name": body.name,
        "description": body.description,
        "severity": body.severity,
        "typical_symptoms": body.typical_symptoms,
        "typical_cost_min": body.typical_cost_min,
        "typical_cost_max": body.typical_cost_max,
        "created_at": datetime.now(timezone.utc),
    }


def fault_doc_to_public(doc: dict) -> FaultPublic:
    return FaultPublic(
        id=str(doc["_id"]),
        appliance_type=doc["appliance_type"],
        name=doc["name"],
        description=doc["description"],
        severity=doc["severity"],
        typical_symptoms=doc.get("typical_symptoms", []),
        typical_cost_min=doc.get("typical_cost_min"),
        typical_cost_max=doc.get("typical_cost_max"),
        created_at=doc["created_at"],
    )