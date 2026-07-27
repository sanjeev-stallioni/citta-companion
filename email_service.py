"""Email notifications for Citta Companion.

Uses placeholder SMTP settings from :mod:`config`. No real credentials are
committed. All functions fail soft (return a boolean) so the UI never breaks if
mail delivery is unavailable.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

import config

logger = logging.getLogger(__name__)


def _send_email(to_address: str, subject: str, body: str) -> bool:
    """Send a plain-text email. Returns ``True`` on success.

    If credentials are still placeholders, the email is logged instead of sent,
    which keeps local development frictionless.
    """
    if not to_address:
        logger.warning("No recipient address provided; skipping email.")
        return False

    # Guard: don't attempt real delivery with placeholder credentials.
    if config.SMTP_PASSWORD in (None, "", "REPLACE_ME"):
        logger.info(
            "SMTP not configured — would send email to %s | subject=%s",
            to_address,
            subject,
        )
        return False

    message = EmailMessage()
    message["From"] = config.EMAIL_FROM
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as server:
            if config.SMTP_USE_TLS:
                server.starttls()
            server.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
            server.send_message(message)
        logger.info("Email sent to %s", to_address)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to send email: %s", exc)
        return False


def send_admin_alert(
    employee_id: str,
    sector: str,
    risk_category: str,
    matched_keywords: list[str] | None = None,
    trigger_message: str = "",
) -> bool:
    """Notify the wellbeing admin of a risk/crisis event."""
    keywords = ", ".join(matched_keywords or []) or "n/a"
    subject = f"[Citta Companion] Risk alert ({risk_category.upper()}) — {employee_id}"
    body = (
        "A Citta Companion conversation was flagged for review.\n\n"
        f"Employee ID : {employee_id}\n"
        f"Sector      : {sector}\n"
        f"Risk level  : {risk_category}\n"
        f"Keywords    : {keywords}\n"
        f"Message     : {trigger_message}\n\n"
        "Please follow your organisation's duty-of-care escalation process.\n"
    )
    return _send_email(config.ADMIN_ALERT_EMAIL, subject, body)


def send_support_request_alert(employee_id: str, sector: str, notes: str = "") -> bool:
    """Notify the wellbeing admin that an employee requested human support."""
    subject = f"[Citta Companion] Human support requested — {employee_id}"
    body = (
        "An employee has requested to speak with a wellbeing professional.\n\n"
        f"Employee ID : {employee_id}\n"
        f"Sector      : {sector}\n"
        f"Notes       : {notes or 'n/a'}\n\n"
        "Please follow up according to the support-leads process.\n"
    )
    return _send_email(config.ADMIN_ALERT_EMAIL, subject, body)


def send_welcome_email(to_address: str, employee_id: str) -> bool:
    """Send a welcome/confirmation email to an employee (optional)."""
    subject = "Welcome to Citta Companion"
    body = (
        f"Hello {employee_id},\n\n"
        "Thank you for taking a moment for your wellbeing with Citta Companion.\n\n"
        "Please remember this tool is not therapy, diagnosis or an emergency "
        "service. If you ever need urgent help, contact your local emergency "
        "services or a trusted professional.\n\n"
        "Warm regards,\nThe Citta Companion Team\n"
    )
    return _send_email(to_address, subject, body)
