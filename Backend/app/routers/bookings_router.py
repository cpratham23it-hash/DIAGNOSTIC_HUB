"""
Booking CRUD — create a booking, list user bookings, get single booking.
POST /bookings creates a real persisted booking tied to a diagnosis + technician.
"""

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, status

from app.database import get_db
from app.models.booking import BookingCreate, BookingPublic, new_booking_document
from app.security.current_user import CurrentUser, get_current_user

router = APIRouter(prefix="/bookings", tags=["bookings"])


def _doc_to_public(doc: dict) -> BookingPublic:
    return BookingPublic(
        id=str(doc["_id"]),
        diagnosis_id=doc["diagnosis_id"],
        technician_id=doc["technician_id"],
        scheduled_slot=doc["scheduled_slot"],
        status=doc["status"],
        price=doc.get("price"),
        created_at=doc["created_at"],
    )


@router.post("", response_model=BookingPublic, status_code=status.HTTP_201_CREATED)
async def create_booking(
    body: BookingCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    db = get_db()

    # Validate diagnosis exists and belongs to user
    try:
        diag = await db.diagnoses.find_one({"_id": ObjectId(body.diagnosis_id)})
    except InvalidId:
        diag = None
    if not diag or diag["user_id"] != current_user.id:
        raise HTTPException(status_code=404, detail="Diagnosis not found.")

    # Validate technician exists
    try:
        tech = await db.technicians.find_one({"_id": ObjectId(body.technician_id)})
    except InvalidId:
        tech = None
    if not tech:
        raise HTTPException(status_code=404, detail="Technician not found.")

    price = tech.get("price_per_visit")
    doc = new_booking_document(user_id=current_user.id, body=body, price=price)
    result = await db.bookings.insert_one(doc)
    doc["_id"] = result.inserted_id

    # Increment technician's jobs_completed
    await db.technicians.update_one(
        {"_id": ObjectId(body.technician_id)},
        {"$inc": {"jobs_completed": 1}},
    )

    return _doc_to_public(doc)


@router.get("", response_model=list[BookingPublic])
async def list_bookings(
    current_user: CurrentUser = Depends(get_current_user),
):
    db = get_db()
    docs = await db.bookings.find({"user_id": current_user.id}).sort("created_at", -1).to_list(length=100)
    return [_doc_to_public(d) for d in docs]


@router.get("/{booking_id}", response_model=BookingPublic)
async def get_booking(
    booking_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    db = get_db()
    try:
        doc = await db.bookings.find_one({"_id": ObjectId(booking_id)})
    except InvalidId:
        doc = None
    if doc is None or doc["user_id"] != current_user.id:
        raise HTTPException(status_code=404, detail="Booking not found.")
    return _doc_to_public(doc)