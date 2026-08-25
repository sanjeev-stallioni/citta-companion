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
        "Transcript Link",
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


def employee_exists(employee_id: str) -> bool | None:
    """Is ``employee_id`` present in the Employee Registry?

    Returns ``True``/``False``, or ``None`` when the answer is unknown because
    Sheets could not be reached. The caller must distinguish those: turning a
    real employee away during a Sheets outage is a worse failure than letting an
    unregistered ID through, so ``None`` should be treated as "allow".

    A valid signature alone does not prove an employee exists — it only proves
    the link was minted with our secret. This is what closes that gap.

    Comparison is case-insensitive. A re-cased ID still passes signature
    verification, so a case-sensitive check here would refuse a genuine
    employee — the one direction this check must never fail in.
    """
    if not str(employee_id or "").strip():
        return False
    try:
        client = _get_client()
        spreadsheet = _open_spreadsheet(client)
        worksheet = spreadsheet.worksheet(config.WORKSHEET_REGISTRY)
        # Column B holds Employee ID; col_values is one call, not a full fetch.
        ids = {
            str(v).strip().casefold()
            for v in worksheet.col_values(2)[1:]
            if str(v).strip()
        }
    except gspread.WorksheetNotFound:
        logger.warning(
            "Registry tab '%s' not found; cannot verify employee IDs.",
            config.WORKSHEET_REGISTRY,
        )
        return None
    except GoogleSheetsUnavailableError as exc:
        logger.warning("Registry check unavailable: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.exception("Registry check failed: %s", exc)
        return None
    return str(employee_id).strip().casefold() in ids


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


# Employee Registry status columns (1-indexed, matching the live sheet).
# Unlike every other tab, the registry is never appended to by this app — it
# is owned by the Make scenario. These writers find an existing row by
# Employee ID and update named cells in place.
_REGISTRY_COL_EMPLOYEE_ID = 2
_REGISTRY_COL_CHAT_STARTED = 17
_REGISTRY_COL_CHAT_COMPLETED = 18
_REGISTRY_COL_RISK_CATEGORY = 19
_REGISTRY_COL_HUMAN_SUPPORT = 20
_REGISTRY_COL_SUMMARY_GENERATED = 22
_REGISTRY_COL_LAST_UPDATED = 23


def _find_registry_row(worksheet: gspread.Worksheet, employee_id: str) -> int | None:
    """Return the 1-indexed sheet row for ``employee_id``, or ``None``.

    Row 1 is skipped: it is the header, and its Employee ID cell contains the
    literal text "Employee ID". Searching from row 1 meant that string matched
    the header and returned row 1, so a status write would have overwritten the
    column headings.

    Matching is case-insensitive for the same reason ``employee_exists`` is —
    IDs are compared, not stored, and a re-cased ID should not silently miss.
    """
    ids = worksheet.col_values(_REGISTRY_COL_EMPLOYEE_ID)
    target = str(employee_id).strip().casefold()
    for i, value in enumerate(ids[1:], start=2):
        if str(value).strip().casefold() == target:
            return i
    return None


def _update_registry_status(employee_id: str, updates: dict[int, str]) -> bool:
    """Update named cells on the Employee Registry row for ``employee_id``.

    ``updates`` maps 1-indexed column number to the value to write. Silently
    does nothing if the ID is not found — an unregistered ID (a test chat, a
    hand-minted link) must not create a row here; ``employee_exists`` /
    ``REQUIRE_REGISTERED_ID`` are what gate access, not this writer.

    Fails soft like every other writer: returns ``False`` and logs rather than
    raising, so a Sheets hiccup never blocks the conversation itself.
    """
    if not str(employee_id or "").strip():
        return False
    try:
        client = _get_client()
        spreadsheet = _open_spreadsheet(client)
        worksheet = spreadsheet.worksheet(config.WORKSHEET_REGISTRY)
        row = _find_registry_row(worksheet, employee_id)
        if row is None:
            logger.info(
                "Registry status update skipped: '%s' not found.", employee_id
            )
            return False

        cells = [
            gspread.Cell(row, col, value) for col, value in updates.items()
        ]
        cells.append(
            gspread.Cell(row, _REGISTRY_COL_LAST_UPDATED, _now())
        )
        worksheet.update_cells(cells, value_input_option="USER_ENTERED")
        return True
    except gspread.WorksheetNotFound:
        logger.warning(
            "Registry tab '%s' not found; cannot update status.",
            config.WORKSHEET_REGISTRY,
        )
        return False
    except GoogleSheetsUnavailableError as exc:
        logger.warning("Registry status update unavailable: %s", exc)
        return False
    except Exception as exc:  # noqa: BLE001
        logger.exception("Registry status update failed: %s", exc)
        return False


def mark_chat_started(employee_id: str) -> bool:
    """Set ``Chat Started`` the first time an employee sends a message.

    Fire-and-forget: called on the first turn of every conversation, so it
    sits on the critical path of someone's first reply. A re-chat overwrites
    the previous timestamp — the registry tracks the most recent session, not
    a history of them (that history lives in Chat Summaries / Risk Flags).
    """
    return _update_registry_status(
        employee_id, {_REGISTRY_COL_CHAT_STARTED: _now()}
    )


def mark_chat_completed(
    employee_id: str, risk_category: str, human_support_requested: str = ""
) -> bool:
    """Set ``Chat Completed``, ``Risk Category`` and ``Human Support Requested``.

    Called both when a conversation reaches Finish and when it ends in
    crisis — a crisis never reaches Finish, so without this call that
    conversation would look permanently abandoned in the registry.
    """
    updates = {
        _REGISTRY_COL_CHAT_COMPLETED: _now(),
        _REGISTRY_COL_RISK_CATEGORY: _titled(risk_category),
    }
    if human_support_requested:
        updates[_REGISTRY_COL_HUMAN_SUPPORT] = _titled(human_support_requested)
    return _update_registry_status(employee_id, updates)


def mark_summary_generated(employee_id: str) -> bool:
    """Set ``Summary Generated`` once the AI summary has been written."""
    return _update_registry_status(
        employee_id, {_REGISTRY_COL_SUMMARY_GENERATED: "Yes"}
    )


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
    transcript_url: str = "",
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
        transcript_url,
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
