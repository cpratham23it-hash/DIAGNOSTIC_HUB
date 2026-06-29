"""
Pydantic schemas for the symptom_questions and symptom_sessions collections
(Module 1 — manual symptom checker).

This is a guided, structured walk: appliance -> question -> answer ->
narrower question -> ... -> candidate fault(s). It's deliberately separate
from free-text NLP symptom parsing (that's part of Module 2/3) — this is
multiple-choice, not free text.

Tree shape: each symptom_questions document is one node. A node with
parent_question_id=None is a root question for that appliance_type (there
can be more than one root per appliance if useful, though the seed data
here uses exactly one). Each option on a question can lead to either:
  - another question (a child node whose parent_option_value matches that
    option's value), or
  - a final result, if the node itself has `resolves_to` set (a leaf).

Building out the FULL tree per appliance (every real branch a technician
would actually ask about) is content/knowledge-engineering work, not
something to fabricate wholesale. What's seeded here is a small number of
real, working branches per appliance — enough to prove the engine end to
end — meant to be extended with more real diagnostic content over time.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

ApplianceType = str  # kept loose here; routers validate against the same
# ALLOWED_APPLIANCE_TYPES set used elsewhere, rather than duplicating a
# Literal type in three different files that could drift out of sync.


class QuestionOption(BaseModel):
    value: str  # short machine key, e.g. "constant_running"
    label: str  # what's actually shown to the user


class FaultGuess(BaseModel):
    fault_name: str
    confidence: float  # 0-100


class QuestionCreate(BaseModel):
    appliance_type: str
    question_text: str
    parent_question_id: Optional[str] = None
    parent_option_value: Optional[str] = None  # which option on the parent leads here
    options: list[QuestionOption] = Field(default_factory=list)
    resolves_to: Optional[list[FaultGuess]] = None  # set only on leaf nodes


class QuestionPublic(BaseModel):
    id: str
    appliance_type: str
    question_text: str
    parent_question_id: Optional[str] = None
    parent_option_value: Optional[str] = None
    options: list[QuestionOption] = []
    resolves_to: Optional[list[FaultGuess]] = None
    created_at: datetime


def new_question_document(body: QuestionCreate) -> dict:
    return {
        "appliance_type": body.appliance_type,
        "question_text": body.question_text,
        "parent_question_id": body.parent_question_id,
        "parent_option_value": body.parent_option_value,
        "options": [o.model_dump() for o in body.options],
        "resolves_to": [f.model_dump() for f in body.resolves_to] if body.resolves_to else None,
        "created_at": datetime.now(timezone.utc),
    }


def question_doc_to_public(doc: dict) -> QuestionPublic:
    return QuestionPublic(
        id=str(doc["_id"]),
        appliance_type=doc["appliance_type"],
        question_text=doc["question_text"],
        parent_question_id=doc.get("parent_question_id"),
        parent_option_value=doc.get("parent_option_value"),
        options=[QuestionOption(**o) for o in doc.get("options", [])],
        resolves_to=[FaultGuess(**f) for f in doc["resolves_to"]] if doc.get("resolves_to") else None,
        created_at=doc["created_at"],
    )


# ─────────────────────────── SESSIONS ───────────────────────────

class SessionStatus(str, Enum):
    in_progress = "in_progress"
    completed = "completed"


class AnsweredStep(BaseModel):
    question_id: str
    question_text: str  # snapshotted at answer time, so history reads
    # correctly even if a question's wording is edited later
    selected_value: str
    selected_label: str


class SessionCreate(BaseModel):
    appliance_type: str


class AnswerSubmit(BaseModel):
    value: str  # the option value the user picked for the CURRENT question


class SessionPublic(BaseModel):
    id: str
    user_id: str
    appliance_type: str
    status: SessionStatus
    history: list[AnsweredStep] = []
    current_question: Optional[QuestionPublic] = None  # None once completed
    result: Optional[list[FaultGuess]] = None  # set once completed
    created_at: datetime
    updated_at: datetime


def new_session_document(user_id: str, appliance_type: str) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "user_id": user_id,
        "appliance_type": appliance_type,
        "status": SessionStatus.in_progress.value,
        "current_question_id": None,  # filled in right after insert, once we know the root question's real id
        "history": [],
        "result": None,
        "created_at": now,
        "updated_at": now,
    }