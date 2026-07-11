"""
Pydantic schemas for the appliances collection (Module 4).

An appliance is a physical device a user owns and tracks — e.g. "my kitchen
fridge." Diagnoses are run against a specific appliance, and the health score
is an aggregation over that appliance's diagnosis history.
"""

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field

ApplianceType = Literal["fridge", "ac", "washer", "purifier", "camera"]
HealthStatus = Literal["healthy", "watch", "needs_attention"]


class ApplianceCreate(BaseModel):
    type: ApplianceType
    brand: Optional[str] = None
    model: Optional[str] = None
    nickname: Optional[str] = Field(default=None, max_length=80)
    installed_date: Optional[datetime] = None


class ApplianceUpdate(BaseModel):
    brand: Optional[str] = None
    model: Optional[str] = None
    nickname: Optional[str] = Field(default=None, max_length=80)
    installed_date: Optional[datetime] = None


class AppliancePublic(BaseModel):
    id: str
    user_id: str
    type: ApplianceType
    brand: Optional[str] = None
    model: Optional[str] = None
    nickname: Optional[str] = None
    installed_date: Optional[datetime] = None
    created_at: datetime


class HealthReport(BaseModel):
    """
    Health score for a single appliance, computed on-the-fly from its
    diagnosis history. Not stored — always freshly computed at request time.
    """
    appliance_id: str
    status: HealthStatus
    status_label: str           # human-readable: "Healthy", "Watch", "Needs Attention"
    score: int                  # 0-100, higher = healthier
    total_diagnoses: int
    fault_diagnoses_90d: int    # diagnoses with a detected fault in last 90 days
    last_fault_name: Optional[str] = None
    last_fault_date: Optional[datetime] = None
    recommendation: str         # plain-language action item


def new_appliance_document(user_id: str, body: ApplianceCreate) -> dict:
    return {
        "user_id": user_id,
        "type": body.type,
        "brand": body.brand,
        "model": body.model,
        "nickname": body.nickname,
        "installed_date": body.installed_date,
        "created_at": datetime.now(timezone.utc),
    }


def appliance_doc_to_public(doc: dict) -> AppliancePublic:
    return AppliancePublic(
        id=str(doc["_id"]),
        user_id=doc["user_id"],
        type=doc["type"],
        brand=doc.get("brand"),
        model=doc.get("model"),
        nickname=doc.get("nickname"),
        installed_date=doc.get("installed_date"),
        created_at=doc["created_at"],
    )