"""
app/services/text_analysis.py — LLM-powered appliance fault diagnosis.
Priority: Groq (primary) → DeepSeek (fallback) → Gemini (last resort).
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


# In-memory cache: avoid re-hitting API for identical inputs
_cache = {}
_CACHE_MAX = 50


def _cache_key(symptom_text: str, appliance_type: str) -> str:
    return f"{appliance_type}::{symptom_text.strip().lower()}"


def _build_user_prompt(symptom_text: str, appliance_type: str, fault_docs: list[dict]) -> str:
    fault_lines = []
    for doc in fault_docs:
        symptoms = doc.get("typical_symptoms", [])
        fault_lines.append(f"- {doc['name']}: {'; '.join(symptoms[:3])}")
    fault_list = "\n".join(fault_lines) if fault_lines else "No faults available."

    return f"""Appliance type: {appliance_type}
User symptom description: "{symptom_text.strip()}"

Known faults for this appliance type:
{fault_list}

Analyze the symptom and respond with JSON only."""


def analyze_symptom_text(
    symptom_text: str,
    appliance_type: str,
    fault_docs: list[dict],
) -> Optional[TextPrediction]:
    if not symptom_text or not symptom_text.strip():
        return None

    from app.config import settings

    # Check cache first — avoids burning API quota on repeated inputs
    ck = _cache_key(symptom_text, appliance_type)
    if ck in _cache:
        print("[text_analysis] Cache hit — skipping API call.")
        return _cache[ck]

    user_prompt = _build_user_prompt(symptom_text, appliance_type, fault_docs)

    # Priority chain: Cerebras → Groq → DeepSeek → Gemini
    cerebras_key = settings.cerebras_api_key.strip()
    if cerebras_key:
        result = _call_openai_compatible(
            api_key=cerebras_key,
            base_url="https://api.cerebras.ai/v1/chat/completions",
            model="llama-3.3-70b",
            user_prompt=user_prompt,
            label="Cerebras",
        )
        if result is not None:
            parsed = _parse_result(result, fault_docs, appliance_type)
            _cache_store(ck, parsed)
            return parsed

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

    gemini_key = settings.gemini_api_key.strip()
    if gemini_key:
        result = _call_gemini(gemini_key, user_prompt)
        if result is not None:
            parsed = _parse_result(result, fault_docs, appliance_type)
            _cache_store(ck, parsed)
            return parsed

    print("[text_analysis] No API keys configured or all providers failed.")
    return None


def _cache_store(key: str, result):
    if result is not None:
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


def _call_gemini(api_key: str, user_prompt: str) -> Optional[dict]:
    """Call Gemini API (different format from OpenAI-compatible)."""
    payload = json.dumps({
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 600}
    }).encode()

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent?key={api_key}"

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

    # New dynamic format: "faults" array
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

