"""Archive a conversation transcript as a PDF in Citta's Google Drive.

The app's service account cannot create Drive files — Google refuses with
"Service Accounts do not have storage quota" — so the PDF is produced by an
Apps Script Web App running as the Citta account (see
``transcript-endpoint.gs``). This module just hands it the text and returns the
resulting file URL.

Everything here fails soft. A Drive outage must never interrupt someone's
conversation or block their summary from being saved: the transcript link is
simply left blank and the failure logged.
"""

from __future__ import annotations

import logging

import requests

import config

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 30

_SPEAKERS = {"user": "Employee", "assistant": "Citta Companion"}


def format_transcript(history: list[dict]) -> str:
    """Render the message history as plain text, oldest first."""
    lines = []
    for message in history:
        speaker = _SPEAKERS.get(message.get("role", ""), message.get("role", ""))
        lines.append(f"{speaker}: {message.get('content', '')}")
    return "\n\n".join(lines)


def save_transcript(employee_id: str, session_date: str, history: list[dict]) -> str:
    """Archive ``history`` as a PDF. Returns its URL, or "" on any failure.

    Never raises.
    """
    if not config.TRANSCRIPT_WEBHOOK_URL or not config.TRANSCRIPT_SECRET:
        logger.info("Transcript archiving is not configured; skipping.")
        return ""

    transcript = format_transcript(history)
    if not transcript.strip():
        return ""

    try:
        response = requests.post(
            config.TRANSCRIPT_WEBHOOK_URL,
            json={
                "secret": config.TRANSCRIPT_SECRET,
                "employeeId": employee_id,
                "sessionDate": session_date,
                "transcript": transcript,
            },
            timeout=_TIMEOUT_SECONDS,
        )
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Could not archive transcript: %s", exc)
        return ""

    if not data.get("ok"):
        logger.warning("Transcript endpoint refused: %s", data.get("error"))
        return ""

    return str(data.get("url", ""))
