"""Protect the cells nobody should edit by hand.

    cd citta-companion && python3 tools/protect_sheets.py
    cd citta-companion && python3 tools/protect_sheets.py --remove

Safe to re-run: it clears the protections it previously created (matched by
description prefix) and reapplies them, so it will not pile up duplicates.

What this protects, and why only these ranges:

* **Executive Report — the whole tab.** Every cell is either a title, a label
  or a formula. There is nothing here a human is meant to type. One overwritten
  formula silently changes a number the employer acts on, and because the tab
  looks like a spreadsheet the damage is invisible.

* **Admin Review — headers and columns A-F.** Those columns are the live queue
  formula. Columns G-J are deliberately LEFT UNPROTECTED: they are where
  Citta's team records who contacted whom. Protecting them would make the tab
  useless.

* **Header rows on the data tabs.** Rows are appended positionally by
  ``google_sheets.py`` — a reordered or renamed header silently corrupts every
  future write. The data rows themselves stay editable: the client asked to be
  able to correct and delete records by hand.

Two Sheets constraints this had to work around, both confirmed by probing the
live API rather than assumed:

* A protection's editor list **cannot exclude the account creating it** —
  "You can't remove yourself as an editor". The service account must therefore
  stay an editor, which is also required for the app to keep writing.

* The service account is a **writer, not the owner**. A writer's protection
  stops accidental edits, but another editor can still remove the protection
  deliberately. This is a guardrail against slips, not a permissions model.

Warn-on-edit (default) vs strict (``--strict``):

**Google Sheets cannot block a file's OWNER from editing their own file.** An
owner is never bound by a protection's editor list, and removing them changes
nothing because an owner can always restore their own access. Tested directly:
with strict protections applied and `companion@cittarecovery.com` signed in,
every protected cell — including the whole Executive Report — was still freely
editable.

So the default here is ``warningOnly``: Sheets interrupts with "You are trying
to edit part of a protected range. Are you sure?" before the edit lands. That
DOES apply to the owner, and it is the strongest guard available against the
realistic risk, which is clicking a formula cell and typing over it.

``--strict`` blocks outright, but only for accounts that are neither the owner
nor on the editor list. Use it once the sheet is shared with Citta's wider
team, where it will actually bind.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

import config

# Every protection this script creates is tagged, so a re-run can find and
# replace exactly its own and never touch one added by hand in the UI.
TAG = "[auto]"

OWNER_EMAIL = "companion@cittarecovery.com"


def _sheet_ids(sheets, key):
    meta = sheets.get(spreadsheetId=key,
                      fields="sheets(properties(title,sheetId,gridProperties"
                             "(rowCount,columnCount)),protectedRanges"
                             "(protectedRangeId,description))").execute()
    return meta["sheets"]


def _targets(by_title):
    """Ranges to protect, as (title, description, range-dict)."""
    out = []

    # --- Executive Report: everything. ------------------------------------
    if "Executive Report" in by_title:
        sid = by_title["Executive Report"]["properties"]["sheetId"]
        out.append(("Executive Report",
                    f"{TAG} Executive Report is generated — rebuild it with "
                    f"tools/build_exec_report.py instead of editing cells",
                    {"sheetId": sid}))

    # --- Admin Review: title block, header row, and the formula columns. ---
    if "Admin Review" in by_title:
        sid = by_title["Admin Review"]["properties"]["sheetId"]
        rows = by_title["Admin Review"]["properties"]["gridProperties"]["rowCount"]
        # Rows 1-5 (title + header) across all columns.
        out.append(("Admin Review",
                    f"{TAG} Admin Review headings — rebuild with "
                    f"tools/build_admin_review.py",
                    {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 5}))
        # Columns A-F below the header: the live queue formula.
        # G-J are intentionally left editable for Citta's follow-up notes.
        out.append(("Admin Review",
                    f"{TAG} Admin Review queue columns A-F are live formulas "
                    f"— type your notes in G-J instead",
                    {"sheetId": sid, "startRowIndex": 5, "endRowIndex": rows,
                     "startColumnIndex": 0, "endColumnIndex": 6}))

    # --- Data tabs: header row only. Data rows stay editable. -------------
    for title in ("Employee Registry", "Chat Summaries", "Risk Flags",
                  "Support Leads", "Form Responses"):
        if title not in by_title:
            continue
        sid = by_title[title]["properties"]["sheetId"]
        out.append((title,
                    f"{TAG} {title} header row — rows are appended by column "
                    f"position, so renaming or reordering breaks every future "
                    f"write",
                    {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1}))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--remove", action="store_true",
                    help="remove the protections this script created")
    ap.add_argument("--strict", action="store_true",
                    help="block edits outright instead of warning. Has NO "
                         "effect on the sheet's owner, who cannot be locked "
                         "out of their own file — only on other editors.")
    args = ap.parse_args()

    sa_email = json.load(open(config.GOOGLE_CREDENTIALS_FILE))["client_email"]
    creds = Credentials.from_service_account_file(
        config.GOOGLE_CREDENTIALS_FILE,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    sheets = build("sheets", "v4", credentials=creds).spreadsheets()
    key = config.GOOGLE_SHEET_KEY

    live = _sheet_ids(sheets, key)
    by_title = {s["properties"]["title"]: s for s in live}

    # Clear our own previous protections first, so re-running is idempotent.
    requests = []
    removed = 0
    for s in live:
        for pr in (s.get("protectedRanges") or []):
            if str(pr.get("description", "")).startswith(TAG):
                requests.append(
                    {"deleteProtectedRange":
                     {"protectedRangeId": pr["protectedRangeId"]}})
                removed += 1

    if args.remove:
        if requests:
            sheets.batchUpdate(spreadsheetId=key,
                               body={"requests": requests}).execute()
        print(f"Removed {removed} protection(s).")
        return

    added = 0
    for title, description, rng in _targets(by_title):
        protected = {"range": rng, "description": description}
        if args.strict:
            # The creating account CANNOT be excluded from its own editor list
            # ("You can't remove yourself as an editor"), and the app needs
            # write access regardless. The owner is listed for the same reason
            # it would be implicit anyway: an owner cannot be locked out.
            protected["warningOnly"] = False
            protected["editors"] = {"users": [sa_email, OWNER_EMAIL]}
        else:
            # Default. Unlike a strict lock, a warning DOES interrupt the
            # owner — which is the whole point, since the owner is the person
            # editing this sheet day to day.
            protected["warningOnly"] = True
        requests.append({"addProtectedRange": {"protectedRange": protected}})
        added += 1

    sheets.batchUpdate(spreadsheetId=key, body={"requests": requests}).execute()

    mode = "locked" if args.strict else "warn-on-edit"
    print(f"Replaced {removed} protection(s) with {added} ({mode}).")
    print("Editable by hand, deliberately: Admin Review G-J (follow-up notes) "
          "and every data row below the header on the data tabs.")
    if args.strict:
        print("NOTE: strict mode does NOT bind the sheet's owner — Google "
              "never locks an owner out of their own file. It only binds "
              "other editors.")
    else:
        print("Editing a protected cell now raises 'are you sure?' first. "
              "This is the strongest guard that applies to the owner.")


if __name__ == "__main__":
    main()
