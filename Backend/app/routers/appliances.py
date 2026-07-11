"""
Appliances endpoints (Module 4 — appliance performance analysis).

POST   /appliances                  — register a new appliance
GET    /appliances                  — list all the signed-in user's appliances
GET    /appliances/{id}             — fetch one appliance
PATCH  /appliances/{id}             — update brand/model/nickname/installed_date
DELETE /appliances/{id}             — remove an appliance
GET    /appliances/{id}/health      — health report (score, status, trend)
"""

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, status

from app.database import get_db
from app.models.appliance import (
    ApplianceCreate,
    AppliancePublic,
    ApplianceUpdate,
    HealthReport,
    appliance_doc_to_public,
    new_appliance_document,
)
from app.security.current_user import CurrentUser, get_current_user
from app.services.health import compute_health

router = APIRouter(prefix="/appliances", tags=["appliances"])


async def _get_owned_appliance(db, appliance_id: str, user_id: str) -> dict:
    if not ObjectId.is_valid(appliance_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appliance not found.")
    try:
        doc = await db.appliances.find_one({"_id": ObjectId(appliance_id)})
    except InvalidId:
        doc = None
    if doc is None or doc["user_id"] != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appliance not found.")
    return doc


@router.post("", response_model=AppliancePublic, status_code=status.HTTP_201_CREATED)
async def create_appliance(
    body: ApplianceCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    db = get_db()
    doc = new_appliance_document(user_id=current_user.id, body=body)
    result = await db.appliances.insert_one(doc)
    doc["_id"] = result.inserted_id
    return appliance_doc_to_public(doc)


@router.get("", response_model=list[AppliancePublic])
async def list_appliances(current_user: CurrentUser = Depends(get_current_user)):
    db = get_db()
    cursor = db.appliances.find({"user_id": current_user.id}).sort("created_at", -1)
    docs = await cursor.to_list(length=200)
    return [appliance_doc_to_public(d) for d in docs]


@router.get("/{appliance_id}", response_model=AppliancePublic)
async def get_appliance(
    appliance_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    db = get_db()
    doc = await _get_owned_appliance(db, appliance_id, current_user.id)
    return appliance_doc_to_public(doc)


@router.patch("/{appliance_id}", response_model=AppliancePublic)
async def update_appliance(
    appliance_id: str,
    body: ApplianceUpdate,
    current_user: CurrentUser = Depends(get_current_user),
):
    db = get_db()
    await _get_owned_appliance(db, appliance_id, current_user.id)

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update.",
        )

    await db.appliances.update_one(
        {"_id": ObjectId(appliance_id)},
        {"$set": updates},
    )
    updated = await db.appliances.find_one({"_id": ObjectId(appliance_id)})
    return appliance_doc_to_public(updated)


@router.delete("/{appliance_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_appliance(
    appliance_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    db = get_db()
    await _get_owned_appliance(db, appliance_id, current_user.id)
    await db.appliances.delete_one({"_id": ObjectId(appliance_id)})


@router.get("/{appliance_id}/health", response_model=HealthReport)
async def get_appliance_health(
    appliance_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Compute and return a health report for this appliance based on its
    diagnosis history. Score and status are derived from faults detected
    in the last 90 days — more recent faults = lower score.

    This is always computed fresh (never cached) so the score reflects
    the latest diagnosis state without any staleness.
    """
    db = get_db()
    await _get_owned_appliance(db, appliance_id, current_user.id)

    # Fetch all diagnoses for this appliance, newest first
    cursor = db.diagnoses.find(
        {"appliance_id": appliance_id, "user_id": current_user.id}
    ).sort("created_at", -1)
    diagnoses = await cursor.to_list(length=500)

    return compute_health(appliance_id=appliance_id, diagnoses=diagnoses)