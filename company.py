"""Company identity, derived from the Employee ID prefix.

Multi-company readiness, Phase 2. The client's requirement (27 Aug 2026) was
"basic multi-company readiness for 3-4 companies", Option A: ONE shared
spreadsheet with Company ID filtering, not a spreadsheet per company.

WHY THE PREFIX AND NOT A SEPARATE COLUMN
----------------------------------------
The client asked for company-prefixed Employee IDs -- ACME-EMP001,
BETA-EMP001 -- so the company is already inside every ID. Deriving it costs
nothing and buys three things a separate `company_id` column could not:

* **Nothing to migrate.** Every registry row, summary, risk flag and support
  lead already carries its company. No new column on four tabs, no backfill.
* **It cannot drift.** One source of truth. A separate column would be a
  second field that must agree with the prefix forever, and the moment they
  disagree there is no way to tell which is right.
* **It is already tamper-proof.** The chat link signs the WHOLE employee ID
  (see link_tokens.sign), so the company travels inside the signature. A
  separate token field would have invalidated every link already emailed.

THE RISK THIS CREATES
---------------------
The prefix becomes load-bearing: ACME-EMP001 and ACNE-EMP001 are different
companies, and a typo in a Make.com scenario would route somebody's data into
the wrong employer's report -- silently, because both look plausible. So a
prefix is only a company if it is REGISTERED (see the Company Register tab).
An ID whose prefix is unknown belongs to no company and is counted nowhere;
it surfaces on the report's "unregistered" line instead, the same way an
unknown Employee ID already does.
"""

from __future__ import annotations

import re

# CITTA-EMP001 -> ("CITTA", "EMP001"). Anchored and case-insensitive.
#
# The separator is the FIRST hyphen: company codes are alphanumeric by
# convention, but a hyphenated one ("MY-CO-EMP001") would otherwise split in
# the wrong place. Splitting once from the left makes "MY" the company, which
# is wrong but predictable; the register check then rejects it rather than
# silently inventing a company. Prefer codes without hyphens.
_ID_PATTERN = re.compile(r"^([A-Za-z0-9]+)-(.+)$")

# The company for IDs that do not parse, or whose prefix is not registered.
# Deliberately not "" -- an empty string reads as "no value yet" in a sheet,
# where this means "we looked and it belongs to nobody".
UNKNOWN = "UNKNOWN"


def company_of(employee_id: str) -> str:
    """The company code in ``employee_id``, or :data:`UNKNOWN`.

    Case is normalised upward: the registry, the Make scenario and hand-typed
    test rows have all disagreed on case before now, and a company that splits
    into "ACME" and "Acme" would split its report in half without erroring.

    This does NOT check the company is registered. Whether a prefix appears on
    the Company Register is a question about the SHEET, not about the ID, so it
    is answered where the sheet is read: tools/build_company_register.py warns
    about registry prefixes no registered company claims. Parsing and
    validating stay separate so a caller can tell an unparseable ID from a
    well-formed one naming a company nobody has set up.
    """
    match = _ID_PATTERN.match(str(employee_id or "").strip())
    if not match:
        return UNKNOWN
    return match.group(1).upper()


def normalise_code(code: str) -> str:
    """Canonical form of a company code, for comparing register entries."""
    return str(code or "").strip().upper()


def is_valid_code(code: str) -> bool:
    """Is ``code`` usable as a company prefix?

    Alphanumeric only, because the ID separator is a hyphen and a hyphenated
    code would parse at the wrong place.
    """
    return bool(re.fullmatch(r"[A-Za-z0-9]+", str(code or "").strip()))
