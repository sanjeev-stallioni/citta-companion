"""Create or refresh the Company Register tab.

    cd citta-companion && python3 tools/build_company_register.py

One row per company. This tab is the authority on which company codes exist:
a company-prefixed Employee ID whose prefix is NOT listed here belongs to no
company, appears on no company's report, and surfaces on the unregistered line
instead. That is the whole point of it -- without a register, a mistyped
prefix would silently invent a company and quietly take an employee's data
with it.

SAFE TO RE-RUN. Existing rows are preserved: the script only adds the tab if
it is missing, rewrites the header, reapplies formatting and validation, and
appends company codes it finds in the registry but not here. It never deletes
a row, because the payment and pilot statuses are typed in by Citta and are
not recoverable from anywhere else.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

import config
from company import company_of, normalise_code, UNKNOWN

HEADERS = [
    "Company ID",
    "Company Name",
    "Payment Status",
    "Pilot Status",
    "Registered Employees",
    "Notes",
]

# The client's exact lists (27 Aug 2026). Kept verbatim -- these drive Citta's
# internal tracking and renaming one would silently orphan existing rows.
PAYMENT_STATUSES = ["Not Paid", "Paid", "Active", "Completed", "Renewed", "Suspended"]
PILOT_STATUSES = ["Setup", "Awaiting Payment", "Active", "Completed",
                  "Renewed", "Paused", "Suspended"]

ACCENT = {"red": 0.541, "green": 0.392, "blue": 0.125}
SOFT = {"red": 0.976, "green": 0.953, "blue": 0.918}


def _service():
    creds = Credentials.from_service_account_file(
        config.GOOGLE_CREDENTIALS_FILE,
        scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return build("sheets", "v4", credentials=creds).spreadsheets()


def _sheet_id(svc, title):
    """The numeric id of ``title``, creating the tab if it does not exist."""
    meta = svc.get(spreadsheetId=config.GOOGLE_SHEET_KEY).execute()
    for sh in meta["sheets"]:
        if sh["properties"]["title"] == title:
            return sh["properties"]["sheetId"], False
    result = svc.batchUpdate(
        spreadsheetId=config.GOOGLE_SHEET_KEY,
        body={"requests": [{"addSheet": {"properties": {
            "title": title,
            "gridProperties": {"rowCount": 50, "columnCount": len(HEADERS)},
        }}}]}).execute()
    return result["replies"][0]["addSheet"]["properties"]["sheetId"], True


def _existing_codes(svc):
    """Company codes already listed, upper-cased."""
    rows = svc.values().get(
        spreadsheetId=config.GOOGLE_SHEET_KEY,
        range=f"'{config.WORKSHEET_COMPANIES}'!A2:A",
    ).execute().get("values", [])
    return {normalise_code(r[0]) for r in rows if r and r[0].strip()}


def _codes_in_registry(svc):
    """Company codes derived from Employee IDs actually in the registry.

    Order preserved so a first run lists companies as they were onboarded.
    UNKNOWN is skipped: an unparseable ID is a data error to investigate, not
    a company to create.
    """
    rows = svc.values().get(
        spreadsheetId=config.GOOGLE_SHEET_KEY,
        range=f"'{config.WORKSHEET_REGISTRY}'!B2:B",
    ).execute().get("values", [])
    seen, ordered = set(), []
    for row in rows:
        if not row or not row[0].strip():
            continue
        code = company_of(row[0])
        if code != UNKNOWN and code not in seen:
            seen.add(code)
            ordered.append(code)
    return ordered


def _count_formula() -> str:
    """ONE formula in E2 that counts every row, present and future.

    ARRAYFORMULA over the whole column, not a formula per row, so a company
    typed in by hand starts counting the moment its code is entered -- with no
    script run. The per-row version meant adding a company and running this
    tool were two separate steps, and forgetting the second left that company's
    count blank forever without any error. Nobody should have to remember a
    command to make a count work.

    INDIRECT for the same reason every formula on the Executive Report uses it:
    Make inserts registrations as ROW INSERTS at the top, and Sheets rewrites
    any range pointing below one. A range written as B2:B became B3:B, then
    B4:B, drifting one row per registration until the formula read past its own
    data. INDIRECT takes a string, so there is nothing for Sheets to adjust.

    COUNTIF with a "CODE-*" pattern, not LEFT(): COUNTIF's wildcard matches the
    prefix followed by anything, which is exactly the rule company_of applies.
    """
    reg = f'INDIRECT("\'{config.WORKSHEET_REGISTRY}\'!B2:B")'
    codes = f'INDIRECT("\'{config.WORKSHEET_COMPANIES}\'!A2:A")'
    return (f'=ARRAYFORMULA(IF({codes}="","",'
            f'COUNTIF({reg},{codes}&"-*")))')


def _install_count_formula(svc):
    """Put the single ARRAYFORMULA in E2, clearing any per-row leftovers.

    Idempotent: returns False when E2 already holds it, so re-running this
    tool does not churn the sheet. The clear matters because earlier versions
    wrote one formula per row -- leaving those in place would make every row
    below E2 a #REF! against the array's output.
    """
    want = _count_formula()
    col = svc.values().get(
        spreadsheetId=config.GOOGLE_SHEET_KEY,
        range=f"'{config.WORKSHEET_COMPANIES}'!E2:E",
        valueRenderOption="FORMULA",
    ).execute().get("values", [])

    current = col[0][0] if col and col[0] else ""
    stale_below = any(r and str(r[0]).strip() for r in col[1:])
    if str(current).replace(" ", "") == want.replace(" ", "") and not stale_below:
        return False

    svc.values().clear(
        spreadsheetId=config.GOOGLE_SHEET_KEY,
        range=f"'{config.WORKSHEET_COMPANIES}'!E2:E", body={}).execute()
    svc.values().update(
        spreadsheetId=config.GOOGLE_SHEET_KEY,
        range=f"'{config.WORKSHEET_COMPANIES}'!E2",
        valueInputOption="USER_ENTERED", body={"values": [[want]]}).execute()
    return True


def _report_orphans(svc):
    """Warn about registry prefixes that no registered company claims.

    These employees are INVISIBLE: no company tab counts them, because every
    report tab is built from the Company Register, and they do not fall into
    another company's figures either. They can still register, still chat,
    still reach crisis -- their conversations simply reach no employer report.

    Nothing here deletes or rewrites anything; the codes may be legitimate
    companies somebody forgot to register. It prints, and the operator decides.
    """
    reg = svc.values().get(
        spreadsheetId=config.GOOGLE_SHEET_KEY,
        range=f"'{config.WORKSHEET_REGISTRY}'!B2:B",
    ).execute().get("values", [])
    listed = _existing_codes(svc)

    orphans = {}
    for row in reg:
        if not row or not row[0].strip():
            continue
        code = company_of(row[0])
        if code == UNKNOWN or code in listed:
            continue
        orphans.setdefault(code, []).append(row[0].strip())

    for code, ids in sorted(orphans.items()):
        print(f"  WARNING: '{code}' has {len(ids)} employee(s) but is not on "
              f"the register — they appear on NO report. e.g. {ids[0]}")
    return orphans


def main():
    svc = _service()
    sheet_id, created = _sheet_id(svc, config.WORKSHEET_COMPANIES)

    existing = set() if created else _existing_codes(svc)
    discovered = [c for c in _codes_in_registry(svc) if c not in existing]

    # Header first, then append only what is missing. Never a full rewrite:
    # payment and pilot status are typed in by Citta and exist nowhere else.
    svc.values().update(
        spreadsheetId=config.GOOGLE_SHEET_KEY,
        range=f"'{config.WORKSHEET_COMPANIES}'!A1",
        valueInputOption="RAW", body={"values": [HEADERS]}).execute()

    if discovered:
        # Columns A-D only. Column E belongs to the ARRAYFORMULA in E2 and
        # writing a value into it would break the array for every row below.
        rows = [[code, "", "Not Paid", "Setup"] for code in discovered]
        svc.values().append(
            spreadsheetId=config.GOOGLE_SHEET_KEY,
            range=f"'{config.WORKSHEET_COMPANIES}'!A1",
            valueInputOption="USER_ENTERED", insertDataOption="INSERT_ROWS",
            body={"values": rows}).execute()

    total = len(existing) + len(discovered)
    _format(svc, sheet_id, max(total, 1))
    installed = _install_count_formula(svc)

    print(f"{config.WORKSHEET_COMPANIES}: "
          f"{'created' if created else 'updated'}, "
          f"{total} compan{'y' if total == 1 else 'ies'}"
          + (f" (added {', '.join(discovered)})" if discovered else ""))
    if discovered:
        print("  Fill in Company Name for each, and set Payment/Pilot status.")
    if installed:
        print("  Installed the column-wide count formula in E2.")
    print("  Counts are self-maintaining: a company typed into column A is "
          "counted at once, with no need to re-run this tool.")
    _report_orphans(svc)


def _format(svc, sheet_id, rows):
    # Reach well past the last company so the NEXT one added by hand lands on
    # a row that already has its dropdowns and tint. Sizing this to the current
    # count meant every new company arrived on an unformatted row -- the same
    # trap the count formula used to set, and just as quiet.
    last = max(rows + 1, 200)
    reqs = [
        {"repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
            "cell": {"userEnteredFormat": {
                "backgroundColor": ACCENT,
                "textFormat": {"bold": True, "foregroundColor":
                               {"red": 1, "green": 1, "blue": 1}}}},
            "fields": "userEnteredFormat(backgroundColor,textFormat)"}},
        {"updateSheetProperties": {
            "properties": {"sheetId": sheet_id,
                           "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount"}},
        # Company ID is a key, not prose -- make it visibly so.
        {"repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": last,
                      "startColumnIndex": 0, "endColumnIndex": 1},
            "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
            "fields": "userEnteredFormat.textFormat"}},
        # Registered Employees is a formula. Tint it so nobody types over it:
        # doing so would replace a live count with a number frozen forever.
        {"repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": last,
                      "startColumnIndex": 4, "endColumnIndex": 5},
            "cell": {"userEnteredFormat": {"backgroundColor": SOFT}},
            "fields": "userEnteredFormat.backgroundColor"}},
    ]
    for col, values in ((2, PAYMENT_STATUSES), (3, PILOT_STATUSES)):
        reqs.append({"setDataValidation": {
            "range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": last,
                      "startColumnIndex": col, "endColumnIndex": col + 1},
            "rule": {"condition": {"type": "ONE_OF_LIST",
                                   "values": [{"userEnteredValue": v} for v in values]},
                     "showCustomUi": True, "strict": False}}})
    for col, width in ((0, 130), (1, 220), (2, 130), (3, 150), (4, 160), (5, 260)):
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                      "startIndex": col, "endIndex": col + 1},
            "properties": {"pixelSize": width}, "fields": "pixelSize"}})
    svc.batchUpdate(spreadsheetId=config.GOOGLE_SHEET_KEY,
                    body={"requests": reqs}).execute()


if __name__ == "__main__":
    main()
