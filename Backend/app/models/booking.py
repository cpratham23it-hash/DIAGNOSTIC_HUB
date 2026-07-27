"""
Pydantic schemas for the bookings collection.
Stores denormalized details (tech name, fault, appliance) for easy display.
"""

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel

BookingStatus = Literal["pending", "confirmed", "completed", "cancelled"]


class BookingCreate(BaseModel):
    diagnosis_id: str
    technician_id: str
    scheduled_slot: str


class BookingPublic(BaseModel):
    id: str
    diagnosis_id: str
    technician_id: str
    technician_name: Optional[str] = None
    appliance_type: Optional[str] = None
    appliance_name: Optional[str] = None
    fault_name: Optional[str] = None
    fault_confidence: Optional[float] = None
    scheduled_slot: str
    status: BookingStatus
    price: Optional[float] = None
    cost_min: Optional[float] = None
    cost_max: Optional[float] = None
    created_at: datetime


def new_booking_document(
    user_id: str,
    body: BookingCreate,
    price: Optional[float] = None,
    technician_name: Optional[str] = None,
    appliance_type: Optional[str] = None,
    appliance_name: Optional[str] = None,
    fault_name: Optional[str] = None,
    fault_confidence: Optional[float] = None,
    cost_min: Optional[float] = None,
    cost_max: Optional[float] = None,
) -> dict:
    return {
        "user_id": user_id,
        "diagnosis_id": body.diagnosis_id,
        "technician_id": body.technician_id,
        "technician_name": technician_name,
        "appliance_type": appliance_type,
        "appliance_name": appliance_name,
        "fault_name": fault_name,
        "fault_confidence": fault_confidence,
        "scheduled_slot": body.scheduled_slot,
        "status": "pending",
        "price": price,
        "cost_min": cost_min,
        "cost_max": cost_max,
        "created_at": datetime.now(timezone.utc),
    }