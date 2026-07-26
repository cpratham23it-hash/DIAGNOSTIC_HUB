"""
Technician listing and fault-matched ranking.
GET /technicians?fault_name=X returns technicians ranked by relevance to the fault.
"""

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, Query, status
from typing import Optional

from app.database import get_db
from app.models.technician import TechnicianPublic
from app.security.current_user import CurrentUser, get_current_user

router = APIRouter(prefix="/technicians", tags=["technicians"])


def _doc_to_public(doc: dict) -> TechnicianPublic:
    return TechnicianPublic(
        id=str(doc["_id"]),
        name=doc["name"],
        service_area=doc.get("service_area"),
        specialties=doc.get("specialties", []),
        price_per_visit=doc.get("price_per_visit"),
        rating=doc.get("rating"),
        jobs_completed=doc.get("jobs_completed", 0),
        created_at=doc["created_at"],
    )


@router.get("", response_model=list[TechnicianPublic])
async def list_technicians(
    fault_name: Optional[str] = Query(None, description="Rank by experience with this fault"),
    current_user: CurrentUser = Depends(get_current_user),
):
    db = get_db()
    docs = await db.technicians.find().to_list(length=100)
    techs = [_doc_to_public(d) for d in docs]

    if fault_name:
        # Sort: technicians with the fault in specialties first, then by rating
        def sort_key(t):
            has_match = 1 if fault_name in t.specialties else 0
            return (-has_match, -(t.rating or 0), -(t.jobs_completed or 0))
        techs.sort(key=sort_key)

    return techs


@router.get("/{technician_id}", response_model=TechnicianPublic)
async def get_technician(
    technician_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    db = get_db()
    try:
        doc = await db.technicians.find_one({"_id": ObjectId(technician_id)})
    except InvalidId:
        doc = None
    if doc is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Technician not found.")
    return _doc_to_public(doc)