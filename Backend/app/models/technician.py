"""
Pydantic schemas for the technicians collection.

A technician profile, as shown on book-technician.html — currently three
hardcoded cards in that page. This is the real shape behind that UI, once
Module 5 actually builds technician sign-up/management and the matching
logic ("ranked by experience with this specific fault").

NOT populated yet. As flagged earlier, getting real technicians signed up
is partly an operations problem, not just an engineering one.
"""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel


class TechnicianCreate(BaseModel):
    name: str
    service_area: Optional[str] = None  # e.g. a city/region name, or lat/long later
    specialties: list[str] = []  # fault names this technician has experience with
    price_per_visit: Optional[float] = None


class TechnicianPublic(BaseModel):
    id: str
    name: str
    service_area: Optional[str] = None
    specialties: list[str] = []
    price_per_visit: Optional[float] = None
    rating: Optional[float] = None
    jobs_completed: int = 0
    created_at: datetime


def new_technician_document(body: TechnicianCreate) -> dict:
    return {
        "name": body.name,
        "service_area": body.service_area,
        "specialties": body.specialties,
        "price_per_visit": body.price_per_visit,
        "rating": None,
        "jobs_completed": 0,
        "created_at": datetime.now(timezone.utc),
    }