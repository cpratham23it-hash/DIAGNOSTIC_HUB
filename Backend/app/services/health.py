"""
app/services/health.py — Appliance health scoring engine (Module 4).

This is intentionally a rules engine, not an ML model. There isn't enough
longitudinal data yet to train a degradation model, and the rules are
transparent and defensible: more recent faults = worse health. When real
booking transaction data accumulates (Module 5/6), these thresholds can be
calibrated against actual repair outcomes.

Health status rules:
  needs_attention — 2+ fault diagnoses in last 90 days, OR any fault in
                    last 30 days (recent = urgent)
  watch           — exactly 1 fault diagnosis in last 90 days
  healthy         — no fault diagnoses in last 90 days

Score (0-100):
  Starts at 100, deducted per fault weighted by recency:
    fault in last 30 days  → -30 points
    fault in last 31-60d   → -20 points
    fault in last 61-90d   → -10 points
  Clamped to [0, 100].
"""

from datetime import datetime, timezone, timedelta
from typing import Optional

from app.models.appliance import HealthReport, HealthStatus


_30D  = timedelta(days=30)
_60D  = timedelta(days=60)
_90D  = timedelta(days=90)


def compute_health(
    appliance_id: str,
    diagnoses: list[dict],
) -> HealthReport:
    """
    Compute a health report for one appliance given its diagnosis documents.

    diagnoses — list of raw diagnosis dicts from MongoDB, for this appliance
                only, sorted newest-first (the router handles the query).
    """
    now = datetime.now(timezone.utc)
    total = len(diagnoses)

    # Collect fault diagnoses (status=done, primary_fault set) within 90 days
    fault_diags_90d = []
    for d in diagnoses:
        if not d.get("primary_fault"):
            continue
        created_at = d.get("created_at")
        if created_at is None:
            continue
        if not created_at.tzinfo:
            created_at = created_at.replace(tzinfo=timezone.utc)
        age = now - created_at
        if age <= _90D:
            fault_diags_90d.append((d, age))

    # Compute score
    score = 100
    for d, age in fault_diags_90d:
        if age <= _30D:
            score -= 30
        elif age <= _60D:
            score -= 20
        else:
            score -= 10
    score = max(0, min(100, score))

    # Determine status
    n_faults_90d = len(fault_diags_90d)
    has_fault_30d = any(age <= _30D for _, age in fault_diags_90d)

    if n_faults_90d >= 2 or has_fault_30d:
        status: HealthStatus = "needs_attention"
        status_label = "Needs Attention"
    elif n_faults_90d == 1:
        status = "watch"
        status_label = "Watch"
    else:
        status = "healthy"
        status_label = "Healthy"

    # Last fault info (most recent fault diagnosis overall, not just 90d)
    last_fault_name: Optional[str] = None
    last_fault_date: Optional[datetime] = None
    for d in diagnoses:
        if d.get("primary_fault"):
            last_fault_name = d["primary_fault"].get("fault_name")
            last_fault_date = d.get("created_at")
            if last_fault_date and not last_fault_date.tzinfo:
                last_fault_date = last_fault_date.replace(tzinfo=timezone.utc)
            break  # diagnoses are sorted newest-first

    # Recommendation
    if status == "needs_attention":
        recommendation = (
            f"{'Multiple recent faults detected' if n_faults_90d >= 2 else 'Fault detected recently'}. "
            "Consider booking a technician to inspect this appliance soon."
        )
    elif status == "watch":
        recommendation = (
            "One fault detected in the last 3 months. "
            "Monitor for recurrence — run another diagnosis if symptoms return."
        )
    else:
        if total == 0:
            recommendation = "No diagnoses run yet. Run a diagnosis to start tracking this appliance's health."
        else:
            recommendation = "No faults detected in the last 3 months. Appliance appears to be running normally."

    return HealthReport(
        appliance_id=appliance_id,
        status=status,
        status_label=status_label,
        score=score,
        total_diagnoses=total,
        fault_diagnoses_90d=n_faults_90d,
        last_fault_name=last_fault_name,
        last_fault_date=last_fault_date,
        recommendation=recommendation,
    )