"""Signed employee links.

The chatbot URL carries the employee ID, sector and language. Those must not
be hand-editable — otherwise anyone could open a session as any employee — so
they travel inside a token signed with a shared secret.

Token format::

    <payload>.<signature>

    payload   = base64url("employee_id|sector|lang|exp")
    signature = base64url(HMAC-SHA256(LINK_SECRET, payload))
    exp       = expiry as unix seconds, or 0 for "never expires"

The signature is verified before a conversation starts, so changing any field
in the URL invalidates the link. This module has no Streamlit/Flask imports so
it can be reused by the link generator and by tests.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time

import config

logger = logging.getLogger(__name__)

_SEPARATOR = "|"


class LinkError(RuntimeError):
    """Raised when a token cannot be built (e.g. no secret configured)."""


def _b64encode(raw: bytes) -> str:
    """URL-safe base64 without padding (keeps links tidy)."""
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _signature(payload_b64: str, secret: str) -> str:
    digest = hmac.new(
        secret.encode(), payload_b64.encode(), hashlib.sha256
    ).digest()
    return _b64encode(digest)


def sign(
    employee_id: str,
    sector: str,
    lang: str,
    ttl_days: int = 0,
    secret: str | None = None,
) -> str:
    """Build a signed token for one employee.

    Args:
        employee_id: e.g. ``CITTA-EMP001``.
        sector: e.g. ``IT``.
        lang: language code, e.g. ``en``.
        ttl_days: days until the link expires; ``0`` means never.
        secret: overrides :data:`config.LINK_SECRET` (used by tests).

    Raises:
        LinkError: if no signing secret is configured.
    """
    key = secret if secret is not None else config.LINK_SECRET
    if not key:
        raise LinkError(
            "LINK_SECRET is not set — cannot create signed links. "
            "Add it to your .env / Streamlit secrets."
        )
    for field in (employee_id, sector, lang):
        if _SEPARATOR in str(field):
            raise LinkError(f"'{_SEPARATOR}' is not allowed in link fields.")

    expires_at = int(time.time()) + ttl_days * 86400 if ttl_days > 0 else 0
    payload = _SEPARATOR.join(
        [str(employee_id), str(sector), str(lang), str(expires_at)]
    )
    payload_b64 = _b64encode(payload.encode())
    return f"{payload_b64}.{_signature(payload_b64, key)}"


def verify(token: str, secret: str | None = None) -> dict | None:
    """Return the link's fields if ``token`` is authentic, else ``None``.

    Never raises: any malformed, tampered or expired token yields ``None``.
    """
    key = secret if secret is not None else config.LINK_SECRET
    if not key or not token or "." not in token:
        return None

    payload_b64, _, provided = token.partition(".")
    digest = hmac.new(key.encode(), payload_b64.encode(), hashlib.sha256).digest()
    # Accept either encoding of the same HMAC: base64url (what sign() emits)
    # or hex, which is what some automation tools (e.g. Make.com) produce.
    # Constant-time comparison keeps the check free of timing side channels.
    matches = hmac.compare_digest(_b64encode(digest), provided) or hmac.compare_digest(
        digest.hex(), provided.lower()
    )
    if not matches:
        logger.warning("Rejected chat link: bad signature")
        return None

    try:
        fields = _b64decode(payload_b64).decode().split(_SEPARATOR)
        employee_id, sector, lang, expires_at = fields
        expiry = int(expires_at)
    except (ValueError, UnicodeDecodeError, base64.binascii.Error):
        logger.warning("Rejected chat link: malformed payload")
        return None

    if expiry and time.time() > expiry:
        logger.info("Rejected chat link: expired")
        return None

    return {"employee_id": employee_id, "sector": sector, "lang": lang}


def build_url(
    base_url: str,
    employee_id: str,
    sector: str,
    lang: str,
    ttl_days: int = 0,
) -> str:
    """Return the full chat URL carrying a signed token."""
    token = sign(employee_id, sector, lang, ttl_days)
    return f"{base_url.rstrip('/')}/?t={token}"
