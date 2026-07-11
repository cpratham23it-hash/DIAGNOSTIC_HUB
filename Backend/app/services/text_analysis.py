"""
app/services/text_analysis.py — DeepSeek-powered appliance fault diagnosis.
Returns a dynamic number of faults based on confidence thresholds.
"""

import json
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


SYSTEM_PROMPT = """You are an expert appliance fault diagnosis assistant for Diagnos, an AI-powered home appliance health platform.

Your ONLY job is to analyze appliance symptom descriptions and identify the most likely faults from a provided list.

You must respond with a valid JSON object with exactly these fields:
{
  "is_valid_query": true or false,
  "faults": [
    {"fault_name": "exact fault name from the provided list", "confidence": integer 0-100}
  ],
  "message": "plain English explanation under 80 words"
}

Rules:
1. If the query is NOT about an appliance symptom (e.g. math questions, general chat, weather, jokes, gibberish, random characters), set is_valid_query=false, faults=[], message="Please describe a symptom, sound, smell, or behavior you have noticed with your appliance."
2. If it IS about an appliance but you cannot identify a specific fault, set faults=[], message asking for more detail.
3. Use EXACT fault names from the provided list. Do not invent new fault names.
4. The "faults" array should contain ALL faults from the list that could plausibly match the symptoms, ranked by confidence (highest first). Do NOT cap at 3 — include every fault with confidence >= 10. Omit faults with confidence below 10.
5. Confidence guidelines: 75-95 for strong match, 50-74 for moderate, 25-49 for weak but possible, 10-24 for unlikely but not impossible.
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
    api_key = settings.deepseek_api_key.strip()
    if not api_key:
        # Fall back to Gemini key if DeepSeek not configured
        api_key = settings.gemini_api_key.strip()
        if not api_key:
            return None
        return _call_gemini(symptom_text, appliance_type, fault_docs, api_key)

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
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 600,
        "stream": False
    }).encode()

    url = "https://api.deepseek.com/v1/chat/completions"

    try:
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())

        raw_text = data["choices"][0]["message"]["content"].strip()

        # Strip markdown fences if present
        if raw_text.startswith("```"):
            parts = raw_text.split("```")
            raw_text = parts[1] if len(parts) > 1 else raw_text
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
        raw_text = raw_text.strip()

        result = json.loads(raw_text)
        return _parse_result(result, fault_docs, appliance_type)

    except Exception as e:
        import traceback
        print(f"[text_analysis] DeepSeek ERROR: {e}")
        traceback.print_exc()
        return None


def _call_gemini(symptom_text, appliance_type, fault_docs, api_key):
    """Fallback to Gemini if DeepSeek key is not configured."""
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
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 600}
    }).encode()

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"

    try:
        import time
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        data = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read())
                break
            except urllib.error.HTTPError as he:
                if he.code == 429 and attempt < 2:
                    time.sleep(2 ** attempt)
                    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
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
        return _parse_result(result, fault_docs, appliance_type)

    except Exception as e:
        import traceback
        print(f"[text_analysis] Gemini ERROR: {e}")
        traceback.print_exc()
        return None


def _parse_result(result: dict, fault_docs: list[dict], appliance_type: str) -> Optional[TextPrediction]:
    """Parse the JSON result from either DeepSeek or Gemini into a TextPrediction."""
    known_names = {doc["name"] for doc in fault_docs}

    def resolve_fault_name(name):
        if not name:
            return None
        if name in known_names:
            return name
        return next((n for n in known_names if n.lower() == name.lower()), None)

    is_valid = bool(result.get("is_valid_query", True))
    message = result.get("message", "Analysis complete.")

    # New dynamic format: "faults" array ranked by confidence
    faults_list = result.get("faults", [])

    # Legacy format fallback: "primary_fault" + "other_faults"
    if not faults_list and result.get("primary_fault"):
        faults_list = [{"fault_name": result["primary_fault"], "confidence": result.get("confidence", 0)}]
        faults_list.extend(result.get("other_faults", []))

    # Resolve and filter
    resolved = []
    for item in faults_list:
        name = resolve_fault_name(item.get("fault_name"))
        conf = float(item.get("confidence", 0))
        if name and conf >= 10:
            resolved.append(FaultGuess(fault_name=name, confidence=conf))

    # Sort by confidence descending
    resolved.sort(key=lambda f: f.confidence, reverse=True)

    # Primary = highest confidence, if >= 50
    primary_name = None
    primary_conf = 0.0
    other_faults = []

    if resolved and resolved[0].confidence >= 50:
        primary_name = resolved[0].fault_name
        primary_conf = resolved[0].confidence
        # Deduplicate: everything else is other_faults
        seen = {primary_name}
        for f in resolved[1:]:
            if f.fault_name not in seen:
                other_faults.append(f)
                seen.add(f.fault_name)
    elif resolved:
        # Nothing above 50 — no primary, but still return them all as other_faults
        other_faults = resolved

    return TextPrediction(
        fault_name=primary_name,
        confidence=primary_conf,
        message=message,
        is_valid_query=is_valid,
        appliance_type=appliance_type,
        other_faults=other_faults,
    )