"""Generate a structured wellbeing summary from a conversation.

The summary is produced by asking Gemini to return strict JSON, then parsed
defensively so a malformed response never crashes the app.
"""

from __future__ import annotations

import json
import logging
import re

from gemini_service import GeminiUnavailableError, generate_json
from prompts import SUMMARY_PROMPT
from risk_detection import RISK_NONE

logger = logging.getLogger(__name__)

# Canonical set of fields every summary must expose.
SUMMARY_FIELDS = [
    "overall_wellbeing",
    "stress_level",
    "sleep",
    "burnout",
    "workplace_pressure",
    "manager_relationship",
    "coping_strategy",
    "emotional_regulation",
    "human_support_requested",
    "risk_category",
    "summary",
    "recommendation",
]


def _empty_summary(risk_category: str = RISK_NONE) -> dict:
    """Return a fully-populated summary with placeholder values."""
    summary = {field: "unclear" for field in SUMMARY_FIELDS}
    # Scope categories are Green/Yellow/Amber/Red/Crisis — "none" maps to green.
    summary["risk_category"] = "green" if risk_category == RISK_NONE else risk_category
    summary["summary"] = "No summary could be generated."
    summary["recommendation"] = (
        "Consider reaching out to a trusted person or your workplace support "
        "resources if you would like to talk further."
    )
    return summary


def _extract_json(raw: str) -> dict | None:
    """Best-effort extraction of a JSON object from model output."""
    if not raw:
        return None

    # Strip markdown code fences if present.
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()

    # Try a direct parse first.
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Fall back to the first {...} block in the text.
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


def _normalize(data: dict, risk_category: str) -> dict:
    """Ensure every expected field exists and values are strings."""
    summary = _empty_summary(risk_category)
    for field in SUMMARY_FIELDS:
        if field in data and data[field] not in (None, ""):
            summary[field] = str(data[field]).strip()

    # A crisis detected locally always wins over the model's own assessment.
    if risk_category and risk_category != RISK_NONE:
        summary["risk_category"] = risk_category
    return summary


def generate_summary(model, history: list[dict], risk_category: str = RISK_NONE) -> dict:
    """Produce a structured summary dict from the conversation ``history``.

    Never raises: on any failure a placeholder summary is returned so the UI
    can still complete gracefully.
    """
    if not history:
        return _empty_summary(risk_category)

    try:
        raw = generate_json(model, history, SUMMARY_PROMPT)
    except GeminiUnavailableError:
        logger.warning("Summary generation failed: Gemini unavailable")
        return _empty_summary(risk_category)

    data = _extract_json(raw)
    if not isinstance(data, dict):
        logger.warning("Summary generation returned non-JSON output")
        return _empty_summary(risk_category)

    return _normalize(data, risk_category)
