"""
Pydantic schemas for the bookings collection.

A booking ties together: a user, the diagnosis that prompted it, a chosen
technician, and a scheduled slot. This is the real shape behind
book-technician.html's "Confirm booking" button, which currently just
toggles a div with nothing persisted.

NOT populated yet — depends on Module 5 (technician records existing) and
Module 2b (diagnoses existing) both being real first.
"""

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel

BookingStatus = Literal["pending", "confirmed", "completed", "cancelled"]


class BookingCreate(BaseModel):
    diagnosis_id: str
    technician_id: str
    scheduled_slot: str  # kept as a plain string for now (e.g. "Today, 2:00 PM");
    # a real calendar/datetime representation can replace this once slot
    # availability logic in Module 5 needs to do real date math


class BookingPublic(BaseModel):
    id: str
    diagnosis_id: str
    technician_id: str
    scheduled_slot: str
    status: BookingStatus
    price: Optional[float] = None
    created_at: datetime


def new_booking_document(user_id: str, body: BookingCreate, price: Optional[float] = None) -> dict:
    return {
        "user_id": user_id,
        "diagnosis_id": body.diagnosis_id,
        "technician_id": body.technician_id,
        "scheduled_slot": body.scheduled_slot,
        "status": "pending",
        "price": price,
        "created_at": datetime.now(timezone.utc),
    }