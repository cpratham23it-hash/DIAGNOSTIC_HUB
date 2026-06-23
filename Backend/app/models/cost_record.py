"""
Pydantic schemas for the cost_records collection.

Regional repair cost data, keyed by fault and region. As discussed earlier,
no public dataset exists for Indian appliance repair costs — the durable
path is your own booking transaction data feeding this table over time,
which means this collection is necessarily the last one to fill with real
data, since it depends on Module 5 producing real bookings first.

NOT populated yet. This file only defines the shape so Module 6 has
somewhere to write to once there's real data to write.
"""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel


class CostRecordCreate(BaseModel):
    fault_name: str
    region: str  # e.g. "Mumbai, Maharashtra"
    cost_low: float
    cost_high: float
    source: Optional[str] = None  # e.g. "booking" once Module 5 feeds this automatically


class CostRecordPublic(BaseModel):
    id: str
    fault_name: str
    region: str
    cost_low: float
    cost_high: float
    source: Optional[str] = None
    recorded_at: datetime


def new_cost_record_document(body: CostRecordCreate) -> dict:
    return {
        "fault_name": body.fault_name,
        "region": body.region,
        "cost_low": body.cost_low,
        "cost_high": body.cost_high,
        "source": body.source,
        "recorded_at": datetime.now(timezone.utc),
    }