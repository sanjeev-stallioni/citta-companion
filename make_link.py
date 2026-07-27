"""Generate a signed Citta Companion chat link.

Usage::

    python make_link.py CITTA-EMP001 IT en
    python make_link.py CITTA-EMP001 IT en --ttl-days 30
    python make_link.py --secret            # print a fresh LINK_SECRET

The employee ID, sector and language are signed, so the resulting link cannot
be edited by hand. Requires ``LINK_SECRET`` in ``.env`` (see ``--secret``).
"""

from __future__ import annotations

import argparse
import secrets
import sys

import config
import link_tokens


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("employee_id", nargs="?", help="e.g. CITTA-EMP001")
    parser.add_argument("sector", nargs="?", help="e.g. IT")
    parser.add_argument("lang", nargs="?", default=config.DEFAULT_LANG,
                        help="language code (default: en)")
    parser.add_argument("--ttl-days", type=int, default=config.LINK_TTL_DAYS,
                        help="days until the link expires (0 = never)")
    parser.add_argument("--base-url", default=config.APP_BASE_URL,
                        help="public app URL")
    parser.add_argument("--secret", action="store_true",
                        help="print a new random LINK_SECRET and exit")
    args = parser.parse_args()

    if args.secret:
        print(f"LINK_SECRET={secrets.token_urlsafe(48)}")
        return 0

    if not args.employee_id or not args.sector:
        parser.error("employee_id and sector are required")

    try:
        url = link_tokens.build_url(
            args.base_url, args.employee_id, args.sector,
            args.lang, args.ttl_days,
        )
    except link_tokens.LinkError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
