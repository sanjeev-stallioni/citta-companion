"""Persistence layer backed by Google Sheets.

This module is deliberately independent of Streamlit so it can be reused,
tested, or swapped for another backend. All functions fail soft: they return a
boolean success flag and never raise into the UI layer.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import gspread
from google.oauth2.service_account import Credentials

import config

logger = logging.getLogger(__name__)

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Column headers for each worksheet.
# These MUST stay in the same order as the columns in the live spreadsheet —
# rows are appended positionally, so a reordered column silently corrupts data.
# Blank entries are columns the chatbot cannot know (personal details live in
# the Employee Registry, joinable on Employee ID) or that Citta's team fills in
# during review.
_HEADERS = {
    config.WORKSHEET_SUMMARIES: [
        "Employee ID",
        "Session Date",
        "Overall Wellbeing",
        "Stress Level",
        "Burnout",
        "Sleep Issues",
        "Workplace Pressure",
        "Manager/Team Stress",
        "Coping Strategies",
        "Emotional Regulation",
        "Human Support Requested",
        "AI Summary",
        "Risk Category",
        "Transcript Link",
    ],
    config.WORKSHEET_RISK_FLAGS: [
        "Employee ID",
        "Date",
        "Risk Category",
        "Detection Method",
        "Matched Keyword",
        "Human Support Requested",
        "Admin Email Sent",
        "Reviewed By",
        "Review Date",
        "Review Status",
    ],
    config.WORKSHEET_SUPPORT_LEADS: [
        "Employee ID",
        "Risk Category",
        "Human Support Requested",
        "Contact Opt-in",
        "Assigned To",
        "Contact Date",
        "Contact Outcome",
        "Follow-up Status",
        "Notes",
    ],
}


def _titled(value: str) -> str:
    """Match the spreadsheet's dropdown casing.

    Risk categories and yes/no answers are lowercase everywhere in the code —
    ``risk_detection`` compares against ``"crisis"``, the UI chips key off
    ``"amber"`` — but the sheet's data validation lists are Title Case. Writing
    the raw value makes every cell show "Input must be an item on the specified
    list", so the conversion happens here, at the boundary, rather than by
    changing the values the rest of the app reasons about.
    """
    text = str(value or "").strip()
    return text[:1].upper() + text[1:] if text else ""


class GoogleSheetsUnavailableError(RuntimeError):
    """Raised internally when Sheets cannot be reached."""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _get_client() -> gspread.Client:
    """Authorise and return a gspread client using the service account.

    Credentials come from ``GOOGLE_CREDENTIALS_JSON`` (raw JSON string — used
    on cloud hosts like Streamlit Cloud where secrets aren't files) or, if not
    set, from the ``GOOGLE_CREDENTIALS_FILE`` path.
    """
    if config.GOOGLE_CREDENTIALS_JSON:
        try:
            info = json.loads(config.GOOGLE_CREDENTIALS_JSON)
            credentials = Credentials.from_service_account_info(info, scopes=_SCOPES)
            return gspread.authorize(credentials)
        except Exception as exc:  # noqa: BLE001
            raise GoogleSheetsUnavailableError(
                f"Invalid GOOGLE_CREDENTIALS_JSON: {exc}"
            ) from exc

    creds_file = config.GOOGLE_CREDENTIALS_FILE
    if not creds_file or not os.path.exists(creds_file):
        raise GoogleSheetsUnavailableError(
            f"Service account credentials not found at '{creds_file}'."
        )
    try:
        credentials = Credentials.from_service_account_file(creds_file, scopes=_SCOPES)
        return gspread.authorize(credentials)
    except Exception as exc:  # noqa: BLE001
        raise GoogleSheetsUnavailableError(str(exc)) from exc


def _open_spreadsheet(client: gspread.Client) -> gspread.Spreadsheet:
    """Open the configured spreadsheet by key (preferred) or by name."""
    try:
        if config.GOOGLE_SHEET_KEY:
            return client.open_by_key(config.GOOGLE_SHEET_KEY)
        return client.open(config.GOOGLE_SHEET_NAME)
    except Exception as exc:  # noqa: BLE001
        raise GoogleSheetsUnavailableError(str(exc)) from exc


def _get_worksheet(spreadsheet: gspread.Spreadsheet, title: str) -> gspread.Worksheet:
    """Return the worksheet ``title``, creating it (with headers) if missing."""
    try:
        return spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=title, rows=1000, cols=26)
        headers = _HEADERS.get(title)
        if headers:
            worksheet.append_row(headers, value_input_option="RAW")
        return worksheet


def _append(worksheet_name: str, row: list) -> bool:
    """Append ``row`` to ``worksheet_name``. Returns success as a boolean."""
    try:
        client = _get_client()
        spreadsheet = _open_spreadsheet(client)
        worksheet = _get_worksheet(spreadsheet, worksheet_name)

        # Ensure headers exist on a brand-new (empty) sheet.
        if not worksheet.get_all_values():
            headers = _HEADERS.get(worksheet_name)
            if headers:
                worksheet.append_row(headers, value_input_option="RAW")

        worksheet.append_row(row, value_input_option="USER_ENTERED")
        return True
    except GoogleSheetsUnavailableError as exc:
        logger.warning("Google Sheets unavailable: %s", exc)
        return False
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected Google Sheets error: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def save_chat_summary(
    employee_id: str,
    sector: str,
    language: str,
    summary: dict,
    transcript_url: str = "",
) -> bool:
    """Persist a structured conversation summary. Returns success flag.

    ``sector`` and ``language`` are not written here — they already sit in the
    Employee Registry against the same Employee ID, so repeating them would
    duplicate data the executive report joins on anyway.

    ``transcript_url`` points at the archived PDF and is blank when archiving is
    switched off or Drive was unreachable.
    """
    row = [
        employee_id,
        _now(),
        summary.get("overall_wellbeing", ""),
        summary.get("stress_level", ""),
        summary.get("burnout", ""),
        summary.get("sleep", ""),
        summary.get("workplace_pressure", ""),
        summary.get("manager_relationship", ""),
        summary.get("coping_strategy", ""),
        summary.get("emotional_regulation", ""),
        _titled(summary.get("human_support_requested", "")),
        summary.get("summary", ""),
        _titled(summary.get("risk_category", "")),
        transcript_url,
    ]
    return _append(config.WORKSHEET_SUMMARIES, row)


def save_risk_flag(
    employee_id: str,
    sector: str,
    language: str,
    risk_category: str,
    matched_keywords: list[str],
    trigger_message: str,
    detection_method: str = "keyword",
    admin_email_sent: bool = False,
) -> bool:
    """Persist a risk/crisis flag. Returns success flag.

    ``trigger_message`` is deliberately not written to the sheet — the raw words
    someone typed in distress are sent to the admin alert email instead, so the
    shared spreadsheet keeps only the fact of the flag. The three review columns
    are left blank for Citta's intake team.
    """
    row = [
        employee_id,
        _now(),
        _titled(risk_category),
        detection_method,
        ", ".join(matched_keywords),
        "",  # Human Support Requested — set by the summary flow, not here
        "Yes" if admin_email_sent else "No",
        "",  # Reviewed By
        "",  # Review Date
        "",  # Review Status
    ]
    return _append(config.WORKSHEET_RISK_FLAGS, row)


def save_support_lead(
    employee_id: str,
    sector: str,
    language: str,
    human_support_requested: str,
    notes: str = "",
    risk_category: str = "",
) -> bool:
    """Persist a request for human support. Returns success flag.

    Name, email and phone are deliberately absent: the chat app never receives
    them (the link carries only ID, sector and language), and Citta's team joins
    on Employee ID against the Employee Registry. Keeping no column for them at
    all means nobody can paste personal contact details into the one sheet the
    design keeps free of them.
    """
    row = [
        employee_id,
        _titled(risk_category),
        _titled(human_support_requested),
        "",  # Contact Opt-in — from the Employee Registry
        "",  # Assigned To      \
        "",  # Contact Date      > filled by Citta's intake team
        "",  # Contact Outcome  /
        "",  # Follow-up Status
        notes,
    ]
    return _append(config.WORKSHEET_SUPPORT_LEADS, row)
