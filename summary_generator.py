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
    # Graded counterparts to the free-text fields above. The prose is what
    # Citta's intake team reads; these are what the employer's report counts.
    # Kept separate rather than replacing the prose: "waking at 3am from work
    # anxiety" is worth far more to a clinician than "poor".
    "sleep_quality",
    "pressure_level",
    "manager_support",
    "coping_level",
    "conflict_level",
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
    # Deliberately vague about *where* support comes from: Citta has given the
    # app no programme names, helplines or portals, so naming one would be an
    # invention. Follow-up comes from Citta's own team via the alert email.
    summary["recommendation"] = (
        "Consider reaching out to someone you trust if you would like to talk "
        "further. Citta's wellbeing team can also follow up with you."
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


# Ordered from least to most severe, so two categories can be compared.
_RISK_ORDER = ["green", "yellow", "amber", "red", "crisis"]


def _at_least(current: str, floor: str) -> str:
    """Return whichever of ``current`` and ``floor`` is the more severe."""
    try:
        return floor if _RISK_ORDER.index(floor) > _RISK_ORDER.index(current) else current
    except ValueError:  # an unrecognised value from the model
        return floor


def _apply_risk_floor(summary: dict) -> dict:
    """Raise the model's risk category when the summary contradicts it.

    The prompt defines the bands, but a language model still classifies
    inconsistently — a Tamil conversation describing four hours' sleep, two
    roles and shouting at family came back "green", while a near-identical
    English one came back "amber". Risk that varies by the language someone
    happens to speak is not a risk assessment.

    So two facts we can check deterministically set a floor, and the model may
    only ever revise upward from it.
    """
    if str(summary.get("human_support_requested", "")).strip().lower() == "yes":
        # Asking to speak to a human is itself the signal. Whatever the model
        # concluded, this person wants contact and must not sit in a green
        # bucket nobody reviews.
        summary["risk_category"] = _at_least(
            str(summary.get("risk_category", "")).strip().lower(), "amber"
        )
    return summary


# The graded fields, and the only values each may hold.
#
# These are COUNTED by formula on the employer's report, so an off-vocabulary
# value is worse than a missing one: "quite poor" matches no COUNTIF, the theme
# silently reads low, and nothing errors. The model is told the lists in the
# prompt; this enforces them, because a prompt is a request and this is a
# guarantee. Anything unrecognised becomes "unclear", which the report ignores.
GRADED_FIELDS = {
    "sleep_quality": {"good", "fair", "poor", "unclear"},
    "pressure_level": {"low", "moderate", "high", "unclear"},
    "manager_support": {"supportive", "mixed", "unsupportive", "unclear"},
    "coping_level": {"healthy", "limited", "none", "unclear"},
    "conflict_level": {"none", "some", "significant", "unclear"},
}


def _normalize(data: dict, risk_category: str) -> dict:
    """Ensure every expected field exists and values are strings."""
    summary = _empty_summary(risk_category)
    for field in SUMMARY_FIELDS:
        if field in data and data[field] not in (None, ""):
            summary[field] = str(data[field]).strip()

    # Graded fields are lowercased and checked against their vocabulary.
    for field, allowed in GRADED_FIELDS.items():
        value = str(summary.get(field, "")).strip().lower()
        if value not in allowed:
            if value not in ("", "unclear"):
                logger.warning(
                    "Summary field %s returned %r, which is not one of %s — "
                    "recorded as unclear", field, value, sorted(allowed),
                )
            value = "unclear"
        summary[field] = value

    summary["risk_category"] = str(summary.get("risk_category", "")).strip().lower()
    summary = _apply_risk_floor(summary)

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
