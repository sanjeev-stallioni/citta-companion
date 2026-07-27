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
from oauth2client.service_account import ServiceAccountCredentials

import config

logger = logging.getLogger(__name__)

_SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Column headers for each worksheet.
_HEADERS = {
    config.WORKSHEET_SUMMARIES: [
        "timestamp",
        "employee_id",
        "sector",
        "language",
        "overall_wellbeing",
        "stress_level",
        "sleep",
        "burnout",
        "workplace_pressure",
        "manager_relationship",
        "coping_strategy",
        "human_support_requested",
        "risk_category",
        "summary",
        "recommendation",
    ],
    config.WORKSHEET_RISK_FLAGS: [
        "timestamp",
        "employee_id",
        "sector",
        "language",
        "risk_category",
        "matched_keywords",
        "trigger_message",
    ],
    config.WORKSHEET_SUPPORT_LEADS: [
        "timestamp",
        "employee_id",
        "sector",
        "language",
        "human_support_requested",
        "notes",
    ],
}


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
            credentials = ServiceAccountCredentials.from_json_keyfile_dict(
                info, _SCOPES
            )
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
        credentials = ServiceAccountCredentials.from_json_keyfile_name(
            creds_file, _SCOPES
        )
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
def save_chat_summary(employee_id: str, sector: str, language: str, summary: dict) -> bool:
    """Persist a structured conversation summary. Returns success flag."""
    row = [
        _now(),
        employee_id,
        sector,
        language,
        summary.get("overall_wellbeing", ""),
        summary.get("stress_level", ""),
        summary.get("sleep", ""),
        summary.get("burnout", ""),
        summary.get("workplace_pressure", ""),
        summary.get("manager_relationship", ""),
        summary.get("coping_strategy", ""),
        summary.get("human_support_requested", ""),
        summary.get("risk_category", ""),
        summary.get("summary", ""),
        summary.get("recommendation", ""),
    ]
    return _append(config.WORKSHEET_SUMMARIES, row)


def save_risk_flag(
    employee_id: str,
    sector: str,
    language: str,
    risk_category: str,
    matched_keywords: list[str],
    trigger_message: str,
) -> bool:
    """Persist a risk/crisis flag. Returns success flag."""
    row = [
        _now(),
        employee_id,
        sector,
        language,
        risk_category,
        ", ".join(matched_keywords),
        trigger_message,
    ]
    return _append(config.WORKSHEET_RISK_FLAGS, row)


def save_support_lead(
    employee_id: str,
    sector: str,
    language: str,
    human_support_requested: str,
    notes: str = "",
) -> bool:
    """Persist a request for human support. Returns success flag."""
    row = [
        _now(),
        employee_id,
        sector,
        language,
        human_support_requested,
        notes,
    ]
    return _append(config.WORKSHEET_SUPPORT_LEADS, row)
