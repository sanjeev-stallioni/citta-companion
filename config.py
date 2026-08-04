"""Central configuration for Citta Companion.

All environment-driven settings are loaded here so the rest of the
application never touches ``os.environ`` directly. Secrets are read from a
local ``.env`` file (see ``.env.example``) and are never hardcoded.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
LOGO_PATH = ASSETS_DIR / "logo.png"

# Load environment variables from a local .env file if present.
load_dotenv(BASE_DIR / ".env")


def _get_env(key: str, default: str | None = None) -> str | None:
    """Read an environment variable, treating empty strings as unset."""
    value = os.getenv(key, default)
    if value is not None and value.strip() == "":
        return default
    return value


# ---------------------------------------------------------------------------
# Application metadata
# ---------------------------------------------------------------------------
APP_TITLE = "Citta Companion"
# Browser-tab icon: the Citta lotus mark (square-padded so it isn't stretched).
APP_ICON = str(BASE_DIR / "static" / "favicon.png")
APP_SUBTITLE = "Employee Wellbeing Discovery"
APP_LAYOUT = "centered"
SIDEBAR_STATE = "collapsed"

DISCLAIMER_TEXT = (
    "This tool is not therapy, diagnosis or an emergency service."
)

# ---------------------------------------------------------------------------
# Gemini configuration
# ---------------------------------------------------------------------------
GEMINI_API_KEY = _get_env("GEMINI_API_KEY")
# Pinned, not "-latest": a floating alias silently moves to newer and pricier
# models. The client asked for Gemini 1.5 Flash, but Google has retired the
# whole 1.x/2.x line for projects that hadn't already used it — every variant
# returns "no longer available", and paying doesn't change that. The 3.x Flash
# Lite tier is the cheapest still callable and honours the client's intent.
# Google AI Studio's "Rate limits by model" page lists retired models too, so
# treat an actual API call as the only proof a model is usable.
GEMINI_MODEL_NAME = _get_env("GEMINI_MODEL_NAME", "gemini-3.1-flash-lite")

# ---------------------------------------------------------------------------
# Google Sheets configuration
# ---------------------------------------------------------------------------
# Path to the service-account JSON credentials file.
GOOGLE_CREDENTIALS_FILE = _get_env(
    "GOOGLE_CREDENTIALS_FILE", str(BASE_DIR / "service_account.json")
)
# Alternative for cloud hosting (e.g. Streamlit Cloud secrets): the full
# service-account JSON as a string. Takes precedence over the file when set.
GOOGLE_CREDENTIALS_JSON = _get_env("GOOGLE_CREDENTIALS_JSON")
# Either the spreadsheet key (preferred) or its human-readable name.
GOOGLE_SHEET_KEY = _get_env("GOOGLE_SHEET_KEY")
GOOGLE_SHEET_NAME = _get_env("GOOGLE_SHEET_NAME", "Citta Companion")

# Worksheet (tab) names inside the spreadsheet.
WORKSHEET_SUMMARIES = _get_env("WORKSHEET_SUMMARIES", "Chat Summaries")
WORKSHEET_RISK_FLAGS = _get_env("WORKSHEET_RISK_FLAGS", "Risk Flags")
WORKSHEET_SUPPORT_LEADS = _get_env("WORKSHEET_SUPPORT_LEADS", "Support Leads")
WORKSHEET_REGISTRY = _get_env("WORKSHEET_REGISTRY", "Employee Registry")

# Require the Employee ID in a link to exist in the registry before a chat may
# start. Off by default so local development and tests keep working without
# Sheets credentials; set REQUIRE_REGISTERED_ID=true in the deployed app.
REQUIRE_REGISTERED_ID = _get_env("REQUIRE_REGISTERED_ID", "false").lower() in (
    "1", "true", "yes",
)

# ---------------------------------------------------------------------------
# Email configuration (placeholders — no real credentials committed)
# ---------------------------------------------------------------------------
SMTP_HOST = _get_env("SMTP_HOST", "smtp.example.com")
SMTP_PORT = int(_get_env("SMTP_PORT", "587"))
SMTP_USERNAME = _get_env("SMTP_USERNAME", "no-reply@example.com")
SMTP_PASSWORD = _get_env("SMTP_PASSWORD", "REPLACE_ME")
SMTP_USE_TLS = _get_env("SMTP_USE_TLS", "true").lower() == "true"

EMAIL_FROM = _get_env("EMAIL_FROM", "Citta Companion <no-reply@example.com>")
ADMIN_ALERT_EMAIL = _get_env("ADMIN_ALERT_EMAIL", "wellbeing-admin@example.com")

# ---------------------------------------------------------------------------
# Defaults for URL parameters
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Signed chat links
# ---------------------------------------------------------------------------
# Shared secret used to sign the employee link (see link_tokens.py). When set,
# the app ONLY accepts URLs carrying a valid ?t=<token>; hand-typed
# ?id=...&sector=... links are refused. Leave empty for local development.
LINK_SECRET = _get_env("LINK_SECRET")
# Days a link stays valid; 0 = never expires.
LINK_TTL_DAYS = int(_get_env("LINK_TTL_DAYS", "0") or "0")
# Public base URL, used when generating links.
APP_BASE_URL = _get_env("APP_BASE_URL", "http://localhost:8501")

# ---------------------------------------------------------------------------
# Transcript archiving
# ---------------------------------------------------------------------------
# Full conversations are archived as PDFs in Citta's Drive. The service account
# cannot create Drive files ("Service Accounts do not have storage quota"), so
# an Apps Script Web App running as the Citta account does it instead — see
# transcript-endpoint.gs. Leave either value empty to disable archiving; the
# rest of the app carries on unaffected.
TRANSCRIPT_WEBHOOK_URL = _get_env("TRANSCRIPT_WEBHOOK_URL")
TRANSCRIPT_SECRET = _get_env("TRANSCRIPT_SECRET")

DEFAULT_EMPLOYEE_ID = "UNKNOWN"
DEFAULT_SECTOR = "General"
DEFAULT_LANG = "en"

# Language codes from the project scope: en, hi, kn, ta, te, mr, bn.
SUPPORTED_LANGUAGES = {
    "en": "English",
    "hi": "Hindi",
    "kn": "Kannada",
    "ta": "Tamil",
    "te": "Telugu",
    "mr": "Marathi",
    "bn": "Bengali",
}
