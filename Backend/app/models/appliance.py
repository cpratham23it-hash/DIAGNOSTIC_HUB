"""
Pydantic schemas for the appliances collection.

An appliance is a single physical device a user owns and tracks — e.g. "my
kitchen fridge." Diagnoses (see models/diagnosis.py) are run against a
specific appliance, and Module 4's health/performance view is essentially
an aggregation over one appliance's diagnosis history.

Not populated by any endpoint yet — Module 2b/4 will add the routes that
create and read these.
"""

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field

ApplianceType = Literal["fridge", "ac", "washer", "purifier", "camera"]


class ApplianceCreate(BaseModel):
    type: ApplianceType
    brand: Optional[str] = None
    model: Optional[str] = None
    nickname: Optional[str] = Field(default=None, max_length=80)  # e.g. "Kitchen Fridge"
    installed_date: Optional[datetime] = None  # used for age-based health logic later


class AppliancePublic(BaseModel):
    id: str
    type: ApplianceType
    brand: Optional[str] = None
    model: Optional[str] = None
    nickname: Optional[str] = None
    installed_date: Optional[datetime] = None
    created_at: datetime


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