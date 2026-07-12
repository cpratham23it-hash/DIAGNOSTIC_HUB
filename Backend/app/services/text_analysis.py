"""
app/services/text_analysis.py — LLM-powered appliance fault diagnosis.
Priority: Groq → DeepSeek → Gemini (only Gemini supports image analysis).
Returns a dynamic number of faults based on confidence thresholds.
"""

import base64
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

Your ONLY job is to analyze appliance symptom descriptions and/or images and identify the most likely faults from a provided list.

You must respond with a valid JSON object with exactly these fields:
{
  "is_valid_query": true or false,
  "faults": [
    {"fault_name": "exact fault name from the provided list", "confidence": integer 0-100}
  ],
  "message": "plain English explanation under 80 words"
}

Rules:
1. If the query is NOT about an appliance symptom (e.g. math questions, general chat, weather, jokes, gibberish, random characters, unrelated images), set is_valid_query=false, faults=[], message="Please describe a symptom or upload a photo of the appliance issue."
2. If it IS about an appliance but you cannot identify a specific fault, set faults=[], message asking for more detail.
3. Use EXACT fault names from the provided list. Do not invent new fault names.
4. The "faults" array should contain ALL faults from the list that could plausibly match the symptoms/image, ranked by confidence (highest first). Include every fault with confidence >= 10.
5. Confidence guidelines: 75-95 for strong match, 50-74 for moderate, 25-49 for weak but possible, 10-24 for unlikely but not impossible.
6. When an image is provided, look for visible signs of damage: rust, corrosion, ice buildup, water leaks, burn marks, frayed wires, clogged filters, loose parts, unusual discoloration, mold, or physical damage.
7. When both image and text are provided, combine evidence from both to produce a more accurate diagnosis.
8. Never mention other brands, products, or services.
9. Never use markdown in the message field. Plain text only.
10. Respond with JSON only — no preamble, no explanation outside the JSON."""


def _build_user_prompt(symptom_text: str, appliance_type: str, fault_docs: list[dict], has_image: bool = False) -> str:
    fault_lines = []
    for doc in fault_docs:
        symptoms = doc.get("typical_symptoms", [])
        fault_lines.append(f"- {doc['name']}: {'; '.join(symptoms[:3])}")
    fault_list = "\n".join(fault_lines) if fault_lines else "No faults available."

    parts = [f"Appliance type: {appliance_type}"]
    if symptom_text and symptom_text.strip():
        parts.append(f'User symptom description: "{symptom_text.strip()}"')
    if has_image:
        parts.append("An image of the appliance has been attached. Examine it for visible signs of damage, wear, leaks, ice buildup, corrosion, burn marks, or other anomalies.")
    parts.append(f"\nKnown faults for this appliance type:\n{fault_list}")
    parts.append("\nAnalyze all provided inputs and respond with JSON only.")

    return "\n".join(parts)


# In-memory cache: avoid re-hitting API for identical inputs
_cache = {}
_CACHE_MAX = 50


def _cache_key(symptom_text: str, appliance_type: str, has_image: bool) -> str:
    # Don't cache image requests (each image is unique)
    if has_image:
        return ""
    return f"{appliance_type}::{symptom_text.strip().lower()}"


def analyze_symptom_text(
    symptom_text: str,
    appliance_type: str,
    fault_docs: list[dict],
    image_bytes: Optional[bytes] = None,
    image_content_type: Optional[str] = None,
) -> Optional[TextPrediction]:
    if not symptom_text and not image_bytes:
        return None
    if symptom_text and not symptom_text.strip() and not image_bytes:
        return None

    from app.config import settings

    has_image = image_bytes is not None
    symptom_text = symptom_text or ""

    # Check cache (text-only requests)
    ck = _cache_key(symptom_text, appliance_type, has_image)
    if ck and ck in _cache:
        print("[text_analysis] Cache hit — skipping API call.")
        return _cache[ck]

    user_prompt = _build_user_prompt(symptom_text, appliance_type, fault_docs, has_image)

    # If image is present, only Gemini supports vision — skip text-only providers
    if not has_image:
        # Priority chain for text-only: Groq → DeepSeek → Gemini
        groq_key = settings.groq_api_key.strip()
        if groq_key:
            result = _call_openai_compatible(
                api_key=groq_key,
                base_url="https://api.groq.com/openai/v1/chat/completions",
                model="llama-3.3-70b-versatile",
                user_prompt=user_prompt,
                label="Groq",
            )
            if result is not None:
                parsed = _parse_result(result, fault_docs, appliance_type)
                _cache_store(ck, parsed)
                return parsed

        deepseek_key = settings.deepseek_api_key.strip()
        if deepseek_key:
            result = _call_openai_compatible(
                api_key=deepseek_key,
                base_url="https://api.deepseek.com/v1/chat/completions",
                model="deepseek-chat",
                user_prompt=user_prompt,
                label="DeepSeek",
            )
            if result is not None:
                parsed = _parse_result(result, fault_docs, appliance_type)
                _cache_store(ck, parsed)
                return parsed

    # Gemini — supports both text and image
    gemini_key = settings.gemini_api_key.strip()
    if gemini_key:
        result = _call_gemini(
            gemini_key, user_prompt,
            image_bytes=image_bytes,
            image_content_type=image_content_type,
        )
        if result is not None:
            parsed = _parse_result(result, fault_docs, appliance_type)
            if ck:
                _cache_store(ck, parsed)
            return parsed

    print("[text_analysis] No API keys configured or all providers failed.")
    return None


def _cache_store(key: str, result):
    if key and result is not None:
        if len(_cache) >= _CACHE_MAX:
            _cache.pop(next(iter(_cache)))
        _cache[key] = result


def _call_openai_compatible(
    api_key: str,
    base_url: str,
    model: str,
    user_prompt: str,
    label: str,
) -> Optional[dict]:
    """Call any OpenAI-compatible API (Groq, DeepSeek, etc.)."""
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 600,
        "stream": False
    }).encode()

    try:
        req = urllib.request.Request(
            base_url,
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
        return _extract_json(raw_text)

    except Exception as e:
        print(f"[text_analysis] {label} ERROR: {e}")
        return None


def _call_gemini(
    api_key: str,
    user_prompt: str,
    image_bytes: Optional[bytes] = None,
    image_content_type: Optional[str] = None,
) -> Optional[dict]:
    """Call Gemini API with optional image (vision)."""

    # Build the user content parts
    user_parts = [{"text": user_prompt}]

    if image_bytes:
        mime = image_content_type or "image/jpeg"
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        user_parts.insert(0, {
            "inline_data": {
                "mime_type": mime,
                "data": b64,
            }
        })

    payload = json.dumps({
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": user_parts}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 600}
    }).encode()

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent?key={api_key}"

    try:
        import time
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        data = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
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
        return _extract_json(raw_text)

    except Exception as e:
        print(f"[text_analysis] Gemini ERROR: {e}")
        return None


def _extract_json(raw_text: str) -> Optional[dict]:
    """Strip markdown fences and parse JSON."""
    if raw_text.startswith("```"):
        parts = raw_text.split("```")
        raw_text = parts[1] if len(parts) > 1 else raw_text
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
    raw_text = raw_text.strip()
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        print(f"[text_analysis] JSON parse failed: {raw_text[:200]}")
        return None


def _parse_result(result: dict, fault_docs: list[dict], appliance_type: str) -> Optional[TextPrediction]:
    """Parse JSON result into TextPrediction."""
    known_names = {doc["name"] for doc in fault_docs}

    def resolve_fault_name(name):
        if not name:
            return None
        if name in known_names:
            return name
        return next((n for n in known_names if n.lower() == name.lower()), None)

    is_valid = bool(result.get("is_valid_query", True))
    message = result.get("message", "Analysis complete.")

    faults_list = result.get("faults", [])

    # Legacy format fallback
    if not faults_list and result.get("primary_fault"):
        faults_list = [{"fault_name": result["primary_fault"], "confidence": result.get("confidence", 0)}]
        faults_list.extend(result.get("other_faults", []))

    resolved = []
    for item in faults_list:
        name = resolve_fault_name(item.get("fault_name"))
        conf = float(item.get("confidence", 0))
        if name and conf >= 10:
            resolved.append(FaultGuess(fault_name=name, confidence=conf))

    resolved.sort(key=lambda f: f.confidence, reverse=True)

    primary_name = None
    primary_conf = 0.0
    other_faults = []

    if resolved and resolved[0].confidence >= 50:
        primary_name = resolved[0].fault_name
        primary_conf = resolved[0].confidence
        seen = {primary_name}
        for f in resolved[1:]:
            if f.fault_name not in seen:
                other_faults.append(f)
                seen.add(f.fault_name)
    elif resolved:
        other_faults = resolved

    return TextPrediction(
        fault_name=primary_name,
        confidence=primary_conf,
        message=message,
        is_valid_query=is_valid,
        appliance_type=appliance_type,
        other_faults=other_faults,
    )