"""
Symptom checker endpoints (Module 1 — guided question engine).

Flow:
  POST /symptom-sessions                 -> start a session, get the first question
  GET  /symptom-sessions/{id}            -> resume: current question + history, or final result
  POST /symptom-sessions/{id}/answer     -> submit an answer, get the next question or the result
  GET  /symptom-sessions                 -> list the signed-in user's own sessions

This is a small, real state machine over the symptom_questions tree, not a
model. "Intelligence" here is entirely the seeded tree content (see
app/scripts/seed_symptom_questions.py) — the engine itself just walks it.
"""

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, status

from app.database import get_db
from app.models.symptom import (
    AnswerSubmit,
    AnsweredStep,
    QuestionPublic,
    SessionCreate,
    SessionPublic,
    SessionStatus,
    new_session_document,
    question_doc_to_public,
)
from app.security.current_user import CurrentUser, get_current_user

router = APIRouter(prefix="/symptom-sessions", tags=["symptom-checker"])

ALLOWED_APPLIANCE_TYPES = {"fridge", "ac", "washer", "purifier", "camera"}


async def _get_question_or_404(db, question_id: str) -> dict:
    if not ObjectId.is_valid(question_id):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Corrupt session state.")
    doc = await db.symptom_questions.find_one({"_id": ObjectId(question_id)})
    if doc is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Corrupt session state.")
    return doc


def _session_doc_to_public(doc: dict, current_question: dict | None) -> SessionPublic:
    return SessionPublic(
        id=str(doc["_id"]),
        user_id=doc["user_id"],
        appliance_type=doc["appliance_type"],
        status=doc["status"],
        history=[AnsweredStep(**h) for h in doc.get("history", [])],
        current_question=question_doc_to_public(current_question) if current_question else None,
        result=doc.get("result"),
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )


@router.post("", response_model=SessionPublic, status_code=status.HTTP_201_CREATED)
async def start_session(body: SessionCreate, current_user: CurrentUser = Depends(get_current_user)):
    if body.appliance_type not in ALLOWED_APPLIANCE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown appliance_type '{body.appliance_type}'. Allowed: {sorted(ALLOWED_APPLIANCE_TYPES)}.",
        )

    db = get_db()

    root_question = await db.symptom_questions.find_one({
        "appliance_type": body.appliance_type,
        "parent_question_id": None,
    })
    if root_question is None:
        # The tree hasn't been seeded for this appliance yet — a real,
        # honest gap, not something to paper over with a fake question.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No symptom-checker questions exist yet for appliance_type '{body.appliance_type}'.",
        )

    doc = new_session_document(user_id=current_user.id, appliance_type=body.appliance_type)
    doc["current_question_id"] = str(root_question["_id"])
    result = await db.symptom_sessions.insert_one(doc)
    doc["_id"] = result.inserted_id

    return _session_doc_to_public(doc, root_question)


@router.get("", response_model=list[SessionPublic])
async def list_sessions(current_user: CurrentUser = Depends(get_current_user)):
    db = get_db()
    cursor = db.symptom_sessions.find({"user_id": current_user.id}).sort("updated_at", -1)
    docs = await cursor.to_list(length=200)

    results = []
    for doc in docs:
        current_question = None
        if doc["status"] == SessionStatus.in_progress.value and doc.get("current_question_id"):
            current_question = await db.symptom_questions.find_one(
                {"_id": ObjectId(doc["current_question_id"])}
            )
        results.append(_session_doc_to_public(doc, current_question))
    return results


@router.get("/{session_id}", response_model=SessionPublic)
async def get_session(session_id: str, current_user: CurrentUser = Depends(get_current_user)):
    if not ObjectId.is_valid(session_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    db = get_db()
    try:
        doc = await db.symptom_sessions.find_one({"_id": ObjectId(session_id)})
    except InvalidId:
        doc = None

    if doc is None or doc["user_id"] != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    current_question = None
    if doc["status"] == SessionStatus.in_progress.value and doc.get("current_question_id"):
        current_question = await _get_question_or_404(db, doc["current_question_id"])

    return _session_doc_to_public(doc, current_question)


@router.post("/{session_id}/answer", response_model=SessionPublic)
async def submit_answer(
    session_id: str,
    body: AnswerSubmit,
    current_user: CurrentUser = Depends(get_current_user),
):
    if not ObjectId.is_valid(session_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    db = get_db()
    try:
        session_doc = await db.symptom_sessions.find_one({"_id": ObjectId(session_id)})
    except InvalidId:
        session_doc = None

    if session_doc is None or session_doc["user_id"] != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    if session_doc["status"] != SessionStatus.in_progress.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This session has already finished. Start a new one to continue.",
        )

    current_question = await _get_question_or_404(db, session_doc["current_question_id"])

    valid_values = {opt["value"] for opt in current_question.get("options", [])}
    if body.value not in valid_values:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{body.value}' is not a valid option for this question. Valid options: {sorted(valid_values)}.",
        )

    selected_label = next(
        (opt["label"] for opt in current_question["options"] if opt["value"] == body.value),
        body.value,
    )

    new_history_entry = {
        "question_id": str(current_question["_id"]),
        "question_text": current_question["question_text"],
        "selected_value": body.value,
        "selected_label": selected_label,
    }
    updated_history = session_doc.get("history", []) + [new_history_entry]

    # Find the next node: a question whose parent is the current one AND
    # whose parent_option_value matches what was just picked.
    next_question = await db.symptom_questions.find_one({
        "parent_question_id": str(current_question["_id"]),
        "parent_option_value": body.value,
    })

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    if next_question is None:
        # Dead end in the tree — no further question and no resolves_to
        # means the seed content doesn't cover this path yet. Treat this
        # as a real, visible gap rather than inventing a fake result.
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                "This answer path isn't covered by the symptom checker yet. "
                "More diagnostic branches need to be added for this combination of answers."
            ),
        )

    if next_question.get("resolves_to"):
        # Reached a leaf — finish the session with a real result.
        await db.symptom_sessions.update_one(
            {"_id": session_doc["_id"]},
            {"$set": {
                "status": SessionStatus.completed.value,
                "history": updated_history,
                "current_question_id": None,
                "result": next_question["resolves_to"],
                "updated_at": now,
            }},
        )
        updated_doc = await db.symptom_sessions.find_one({"_id": session_doc["_id"]})
        return _session_doc_to_public(updated_doc, None)

    # Otherwise, advance to the next question.
    await db.symptom_sessions.update_one(
        {"_id": session_doc["_id"]},
        {"$set": {
            "history": updated_history,
            "current_question_id": str(next_question["_id"]),
            "updated_at": now,
        }},
    )
    updated_doc = await db.symptom_sessions.find_one({"_id": session_doc["_id"]})
    return _session_doc_to_public(updated_doc, next_question)