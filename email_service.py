"""Email notifications for Citta Companion.

Uses placeholder SMTP settings from :mod:`config`. No real credentials are
committed. All functions fail soft (return a boolean) so the UI never breaks if
mail delivery is unavailable.
"""

from __future__ import annotations

import logging
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage

import config

logger = logging.getLogger(__name__)


def _header_safe(value: str, limit: int = 200) -> str:
    """Flatten anything that could break out of an email header.

    The Employee ID reaches the subject line from a URL parameter. A signed
    link makes a crafted ID unlikely, but "unlikely" is not a security control
    — and the same value is also written to a spreadsheet and a PDF. Strip CR,
    LF and NUL, and cap the length so a very long ID cannot produce a folded
    header.
    """
    text = str(value or "")
    for ch in ("\r", "\n", "\x00"):
        text = text.replace(ch, " ")
    return text[:limit].strip()


def _send_email(to_address: str, subject: str, body: str) -> bool:
    """Send a plain-text email. Returns ``True`` on success.

    If credentials are still placeholders, the email is logged instead of sent,
    which keeps local development frictionless.
    """
    if not to_address:
        logger.warning("No recipient address provided; skipping email.")
        return False

    # Guard: a placeholder RECIPIENT is worse than no recipient at all.
    #
    # example.com is reserved and silently discards mail, so SMTP would report
    # success, this would return True, and `Risk Flags` would record "Admin
    # Email Sent: Yes" for a crisis alert nobody ever receives. Deployment has
    # always had a real address in Streamlit secrets, so this has never bitten
    # in production — it was the default sitting in a local .env. Kept because
    # the failure it prevents is invisible exactly where it matters most.
    if "@example.com" in to_address.lower():
        logger.error(
            "ADMIN_ALERT_EMAIL is still the placeholder %s — alert NOT "
            "delivered. Set a real address in Streamlit secrets.", to_address,
        )
        return False

    # Guard: don't attempt real delivery with placeholder credentials.
    if config.SMTP_PASSWORD in (None, "", "REPLACE_ME"):
        logger.info(
            "SMTP not configured — would send email to %s | subject=%s",
            to_address,
            subject,
        )
        return False

    # Header assembly is INSIDE the try.
    #
    # Python refuses a header containing a newline — correctly, since that is
    # how header injection works ("EMP001\nBcc: attacker@..."). But it refuses
    # by raising, and the subject line carries an Employee ID that arrives from
    # a URL parameter. Building the message outside the try meant a crafted ID
    # raised ValueError straight through this function and into the middle of
    # someone's conversation. Every other failure here is soft; this one was not.
    try:
        message = EmailMessage()
        message["From"] = config.EMAIL_FROM
        message["To"] = to_address
        message["Subject"] = _header_safe(subject)
        message.set_content(body)

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


def _tri(value: bool | None) -> str:
    """Render a yes/no/unknown value. ``None`` must never read as "No"."""
    if value is None:
        return "unknown"
    return "Yes" if value else "No"


def _admin_review_link() -> str:
    """Link to the Admin Review tab, as the scope requires in every alert."""
    if not config.GOOGLE_SHEET_KEY:
        return "n/a"
    return (
        f"https://docs.google.com/spreadsheets/d/{config.GOOGLE_SHEET_KEY}"
        f"/edit#gid={config.ADMIN_REVIEW_GID}"
    )


def _footer(employee_id: str, risk_category: str, support_requested: bool | None,
            opted_in: bool | None) -> str:
    """The field block the scope requires on every alert.

    Scope: alerts must carry Employee ID, risk category, whether human support
    was requested, whether the person opted in for further support, a
    timestamp, and a link to the admin review sheet.
    """
    return (
        f"Employee ID       : {employee_id}\n"
        f"Risk category     : {risk_category or 'n/a'}\n"
        f"Support requested : {_tri(support_requested)}\n"
        f"Opted in          : {_tri(opted_in)}\n"
        f"Timestamp         : {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC\n"
        f"Admin review      : {_admin_review_link()}\n"
    )


def send_admin_alert(
    employee_id: str,
    sector: str,
    risk_category: str,
    matched_keywords: list[str] | None = None,
    trigger_message: str = "",
    support_requested: bool | None = None,
    opted_in: bool | None = None,
) -> bool:
    """Notify the wellbeing admin of a risk/crisis event.

    ``trigger_message`` is included only for a keyword-detected crisis, where
    the exact words matter for an immediate duty-of-care judgement. It is never
    written to any sheet. For an Amber/Red alert raised from the summary there
    is no trigger message: the scope asks us to avoid sending sensitive chat
    content by email unless necessary, and for a non-crisis escalation the
    transcript link in the review sheet is the appropriate route.
    """
    keywords = ", ".join(matched_keywords or []) or "n/a"
    subject = f"[Citta Companion] Risk alert ({risk_category.upper()}) — {employee_id}"
    body = (
        "A Citta Companion conversation was flagged for review.\n\n"
        f"{_footer(employee_id, risk_category, support_requested, opted_in)}"
        f"Sector            : {sector}\n"
        f"Keywords          : {keywords}\n"
    )
    if trigger_message:
        body += f"Message           : {trigger_message}\n"
    body += "\nPlease follow your organisation's duty-of-care escalation process.\n"
    return _send_email(config.ADMIN_ALERT_EMAIL, subject, body)


def send_support_request_alert(
    employee_id: str,
    sector: str,
    notes: str = "",
    risk_category: str = "",
    opted_in: bool | None = None,
) -> bool:
    """Notify the wellbeing admin that an employee requested human support."""
    subject = f"[Citta Companion] Human support requested — {employee_id}"
    body = (
        "An employee has requested to speak with a wellbeing professional.\n\n"
        f"{_footer(employee_id, risk_category, True, opted_in)}"
        f"Sector            : {sector}\n"
        f"Notes             : {notes or 'n/a'}\n\n"
        "Please follow up according to the support-leads process.\n"
    )
    return _send_email(config.ADMIN_ALERT_EMAIL, subject, body)


def send_opt_in_alert(
    employee_id: str,
    sector: str,
    risk_category: str = "",
    notes: str = "",
) -> bool:
    """Notify the admin that an employee opted in to be contacted.

    A distinct trigger from "requested human support": someone can tick the
    opt-in box on the registration form and never raise it in conversation.
    The scope lists both separately, and without this that person is never
    followed up.
    """
    subject = f"[Citta Companion] Contact opt-in — {employee_id}"
    body = (
        "An employee opted in on the registration form to be contacted about "
        "further wellbeing support.\n\n"
        f"{_footer(employee_id, risk_category, False, True)}"
        f"Sector            : {sector}\n"
        f"Notes             : {notes or 'n/a'}\n\n"
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
