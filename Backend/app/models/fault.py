"""
Pydantic schemas for the faults collection.

This is the reference library — "what faults exist for this appliance type,
and what does each one typically cost to fix." Module 3's models classify
INTO this list; without it populated, there's nothing for a prediction to
point to. Module 1's symptom-checker tree also resolves to entries here.

NOT populated yet. Populating this with real fault data (from the datasets
discussed earlier, or manually authored entries) is content work that needs
to happen before Module 3 can produce anything meaningful.
"""

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel

ApplianceType = Literal["fridge", "ac", "washer", "purifier", "camera"]
Severity = Literal["low", "medium", "high"]


class FaultCreate(BaseModel):
    appliance_type: ApplianceType
    name: str  # e.g. "Compressor Strain"
    description: str
    severity: Severity
    typical_cost_min: Optional[float] = None
    typical_cost_max: Optional[float] = None


class FaultPublic(BaseModel):
    id: str
    appliance_type: ApplianceType
    name: str
    description: str
    severity: Severity
    typical_cost_min: Optional[float] = None
    typical_cost_max: Optional[float] = None
    created_at: datetime


def new_fault_document(body: FaultCreate) -> dict:
    return {
        "appliance_type": body.appliance_type,
        "name": body.name,
        "description": body.description,
        "severity": body.severity,
        "typical_cost_min": body.typical_cost_min,
        "typical_cost_max": body.typical_cost_max,
        "created_at": datetime.now(timezone.utc),
    }