"""
app/services/text_analysis.py — Gemini-powered appliance fault diagnosis.
"""

import json
import os
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FaultGuess:
    fault_name: str
    confidence: float


@dataclass
class TextPrediction:
    fault_name: Optional[str]
    confidence: float
    message: str
    is_valid_query: bool
    appliance_type: str
    other_faults: list[FaultGuess] = field(default_factory=list)


SYSTEM_INSTRUCTION = """You are an expert appliance fault diagnosis assistant for Diagnos, an AI-powered home appliance health platform.

Your ONLY job is to analyze appliance symptom descriptions and identify the most likely faults from a provided list.

You must respond with a valid JSON object with exactly these fields:
{
  "is_valid_query": true or false,
  "primary_fault": "exact fault name from the provided list, or null",
  "confidence": integer 0-100,
  "other_faults": [
    {"fault_name": "exact name from list", "confidence": integer},
    {"fault_name": "exact name from list", "confidence": integer}
  ],
  "message": "plain English explanation under 80 words"
}

Rules:
1. If the query is NOT about an appliance symptom (e.g. math questions, general chat, weather, jokes, gibberish), set is_valid_query=false, primary_fault=null, confidence=0, other_faults=[], message="Please describe a symptom, sound, smell, or behavior you have noticed with your appliance."
2. If it IS about an appliance but you cannot identify a specific fault from the provided list with reasonable confidence, set primary_fault=null, confidence=0, other_faults=[], message asking for more detail.
3. Use EXACT fault names from the provided list. Do not invent new fault names.
4. Primary confidence: 75-90 for strong match, 50-74 for moderate. Below 50 = set primary_fault to null.
5. other_faults: up to 3 alternative faults from the list with lower confidence. Only include if primary_fault is set.
6. Never mention other brands, products, or services.
7. Never use markdown in the message field. Plain text only.
8. Respond with JSON only — no preamble, no explanation outside the JSON."""


def analyze_symptom_text(
    symptom_text: str,
    appliance_type: str,
    fault_docs: list[dict],
) -> Optional[TextPrediction]:
    if not symptom_text or not symptom_text.strip():
        return None

    from app.config import settings
    api_key = settings.gemini_api_key.strip()
    if not api_key:
        return None

    fault_lines = []
    for doc in fault_docs:
        symptoms = doc.get("typical_symptoms", [])
        fault_lines.append(f"- {doc['name']}: {'; '.join(symptoms[:3])}")
    fault_list = "\n".join(fault_lines) if fault_lines else "No faults available."

    user_prompt = f"""Appliance type: {appliance_type}
User symptom description: "{symptom_text.strip()}"

Known faults for this appliance type:
{fault_list}

Analyze the symptom and respond with JSON only."""

    payload = json.dumps({
        "system_instruction": {
            "parts": [{"text": SYSTEM_INSTRUCTION}]
        },
        "contents": [
            {"role": "user", "parts": [{"text": user_prompt}]}
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 400,
        }
    }).encode()

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"

    try:
        import time
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        data = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read())
                break
            except urllib.error.HTTPError as he:
                if he.code == 429 and attempt < 2:
                    time.sleep(2 ** attempt)  # 1s, 2s
                    req = urllib.request.Request(
                        url,
                        data=payload,
                        headers={"Content-Type": "application/json"},
                        method="POST"
                    )
                    continue
                raise
        if data is None:
            return None

        raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()

        if raw_text.startswith("```"):
            parts = raw_text.split("```")
            raw_text = parts[1] if len(parts) > 1 else raw_text
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
        raw_text = raw_text.strip()

        result = json.loads(raw_text)

        known_names = {doc["name"] for doc in fault_docs}

        def resolve_fault_name(name):
            if not name:
                return None
            if name in known_names:
                return name
            return next((n for n in known_names if n.lower() == name.lower()), None)

        fault_name = resolve_fault_name(result.get("primary_fault"))
        confidence = float(result.get("confidence", 0))
        is_valid = bool(result.get("is_valid_query", True))
        message = result.get("message", "Analysis complete.")

        if confidence < 50:
            fault_name = None

        other_faults = []
        if fault_name:
            for item in result.get("other_faults", [])[:3]:
                name = resolve_fault_name(item.get("fault_name"))
                conf = float(item.get("confidence", 0))
                if name and name != fault_name and conf > 0:
                    other_faults.append(FaultGuess(fault_name=name, confidence=conf))

        return TextPrediction(
            fault_name=fault_name,
            confidence=confidence,
            message=message,
            is_valid_query=is_valid,
            appliance_type=appliance_type,
            other_faults=other_faults,
        )

    except Exception as e:
        import traceback
        print(f"[text_analysis] ERROR: {e}")
        traceback.print_exc()
        return None