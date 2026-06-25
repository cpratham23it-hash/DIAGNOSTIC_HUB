"""
Faults endpoints (Module 2a — fault reference database).

This is the ground-truth library Module 3's models will eventually
classify against, and Module 1's symptom-checker tree will resolve into.
Right now it's plain CRUD with no real predictions touching it yet.

SECURITY NOTE: there is no admin/role tier in this app yet — every route
here only requires get_current_user (i.e. "signed in"), same as every
other protected route. That means any signed-in user can currently create
or edit fault entries. Fine for solo development; this needs a real
admin check before this app has multiple real users, or anyone could
pollute the fault library that every diagnosis eventually depends on.

GET  /faults                       — list all faults, optional ?appliance_type= filter
GET  /faults/{fault_id}            — fetch one
POST /faults                       — create one (see security note above)
"""

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.database import get_db
from app.models.fault import (
    FaultCreate,
    FaultPublic,
    fault_doc_to_public,
    new_fault_document,
)
from app.security.current_user import CurrentUser, get_current_user

router = APIRouter(prefix="/faults", tags=["faults"])

ALLOWED_APPLIANCE_TYPES = {"fridge", "ac", "washer", "purifier", "camera"}


@router.get("", response_model=list[FaultPublic])
async def list_faults(
    appliance_type: str | None = Query(default=None),
    current_user: CurrentUser = Depends(get_current_user),
):
    if appliance_type is not None and appliance_type not in ALLOWED_APPLIANCE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown appliance_type '{appliance_type}'. Allowed: {sorted(ALLOWED_APPLIANCE_TYPES)}.",
        )

    db = get_db()
    query = {"appliance_type": appliance_type} if appliance_type else {}
    cursor = db.faults.find(query).sort("name", 1)
    docs = await cursor.to_list(length=500)
    return [fault_doc_to_public(d) for d in docs]


@router.get("/{fault_id}", response_model=FaultPublic)
async def get_fault(fault_id: str, current_user: CurrentUser = Depends(get_current_user)):
    if not ObjectId.is_valid(fault_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fault not found.")

    db = get_db()
    try:
        doc = await db.faults.find_one({"_id": ObjectId(fault_id)})
    except InvalidId:
        doc = None

    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fault not found.")

    return fault_doc_to_public(doc)


@router.post("", response_model=FaultPublic, status_code=status.HTTP_201_CREATED)
async def create_fault(body: FaultCreate, current_user: CurrentUser = Depends(get_current_user)):
    db = get_db()

    # Avoid exact duplicate (same appliance_type + name) entries from
    # accidental double-seeding or double submission.
    existing = await db.faults.find_one({"appliance_type": body.appliance_type, "name": body.name})
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A fault named '{body.name}' already exists for appliance_type '{body.appliance_type}'.",
        )

    doc = new_fault_document(body)
    result = await db.faults.insert_one(doc)
    doc["_id"] = result.inserted_id
    return fault_doc_to_public(doc)