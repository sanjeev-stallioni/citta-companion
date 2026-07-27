"""Keyword-based crisis/risk detection.

This module is intentionally simple and deterministic. It provides an early,
transparent safety net: if any high-risk phrase appears in a message, the
conversation is immediately escalated to a crisis state.
"""

from __future__ import annotations

import re

# Risk categories in increasing order of severity.
RISK_NONE = "none"
RISK_LOW = "low"
RISK_MODERATE = "moderate"
RISK_CRISIS = "crisis"

# High-risk keywords/phrases. Matching is case-insensitive and whole-word where
# it makes sense. Keep phrases lowercase.
RISK_KEYWORDS: list[str] = [
    "suicide",
    "suicidal",
    "kill myself",
    "killing myself",
    "harm myself",
    "harm others",
    "hurt myself",
    "cannot go on",
    "can't go on",
    "self harm",
    "self-harm",
    "end my life",
    "end it all",
    "want to die",
    "wanna die",
    "no reason to live",
    "better off dead",
    "abuse",
    "abused",
    "unsafe",
    "domestic violence",
    "being hit",
    "beaten",
    "assault",
]

# Pre-compile a single regex for efficiency. Word boundaries are added so that
# short tokens (e.g. "abuse") do not match inside unrelated words.
_PATTERN = re.compile(
    r"|".join(rf"\b{re.escape(word)}\b" for word in RISK_KEYWORDS),
    flags=re.IGNORECASE,
)


def detect_risk(text: str) -> str:
    """Return the risk category detected in ``text``.

    Currently returns :data:`RISK_CRISIS` when any crisis keyword is present,
    otherwise :data:`RISK_NONE`.
    """
    if not text:
        return RISK_NONE
    if _PATTERN.search(text):
        return RISK_CRISIS
    return RISK_NONE


def matched_keywords(text: str) -> list[str]:
    """Return the list of distinct risk keywords found in ``text``.

    Useful for logging/alerting so responders have context.
    """
    if not text:
        return []
    found = {match.group(0).lower() for match in _PATTERN.finditer(text)}
    return sorted(found)


def is_crisis(text: str) -> bool:
    """Convenience helper: ``True`` if ``text`` triggers a crisis state."""
    return detect_risk(text) == RISK_CRISIS
