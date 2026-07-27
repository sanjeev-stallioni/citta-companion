"""Shared helpers for the Streamlit UI layer."""

from __future__ import annotations

import streamlit as st

import config
from risk_detection import (
    RISK_CRISIS,
    RISK_LOW,
    RISK_MODERATE,
    RISK_NONE,
)


def get_query_params() -> dict[str, str]:
    """Read ``id``, ``sector`` and ``lang`` from the URL query string.

    Falls back to sensible defaults from :mod:`config`.
    """
    params = st.query_params

    def _first(key: str, default: str) -> str:
        value = params.get(key, default)
        if isinstance(value, list):
            value = value[0] if value else default
        return (value or default).strip()

    return {
        "employee_id": _first("id", config.DEFAULT_EMPLOYEE_ID),
        "sector": _first("sector", config.DEFAULT_SECTOR),
        "lang": _first("lang", config.DEFAULT_LANG),
    }


def language_label(lang_code: str) -> str:
    """Human-readable language name for a code (e.g. ``en`` -> ``English``)."""
    return config.SUPPORTED_LANGUAGES.get(lang_code, lang_code)


# Label + chip style per risk category (scope: Green/Yellow/Amber/Red/Crisis).
_RISK_META = {
    RISK_NONE: ("Green", "ok"),
    RISK_LOW: ("Yellow", "warn"),
    RISK_MODERATE: ("Amber", "warn"),
    RISK_CRISIS: ("Crisis", "crit"),
}


def risk_label(risk_category: str) -> str:
    """Human-readable label for a risk category."""
    return _RISK_META.get(risk_category, (risk_category.title(), "idle"))[0]


def risk_chip_kind(risk_category: str) -> str:
    """Chip style kind (ok/warn/crit/idle) for a risk category."""
    return _RISK_META.get(risk_category, ("", "idle"))[1]


def status_chip_kind() -> str:
    """Chip style kind for the current conversation status."""
    if st.session_state.get("conversation_finished"):
        return "ok"
    if st.session_state.get("crisis_triggered"):
        return "crit"
    if st.session_state.get("chat_started"):
        return "ok"
    return "idle"


def init_session_state() -> None:
    """Initialise all session_state keys used across the app exactly once."""
    defaults = {
        "consented": False,
        "chat_started": False,
        "messages": [],  # list of {"role": "user"|"assistant", "content": str}
        "model": None,
        "risk_category": RISK_NONE,
        "crisis_triggered": False,
        "conversation_finished": False,
        "summary": None,
        "params_loaded": False,
        "employee_id": config.DEFAULT_EMPLOYEE_ID,
        "sector": config.DEFAULT_SECTOR,
        "lang": config.DEFAULT_LANG,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def conversation_status() -> str:
    """Human-readable conversation status for the sidebar."""
    if st.session_state.get("conversation_finished"):
        return "Finished"
    if st.session_state.get("crisis_triggered"):
        return "Crisis — paused"
    if st.session_state.get("chat_started"):
        return "In progress"
    return "Not started"
