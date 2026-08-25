"""Rebuild the Admin Review tab from scratch.

    cd citta-companion && python3 tools/build_admin_review.py

Safe to re-run at any time: it clears the tab and rewrites it.

This is Citta's internal follow-up queue — the one place a reviewer can see
everybody who needs contacting, without reading three tabs and joining them by
eye. The scope calls for it as the destination for crisis flags and the link
included in every alert email.

Design notes:

* **A live view, not a copy.** Columns A-F are formulas reading `Risk Flags`
  and `Chat Summaries`. A copied row goes stale the moment the source changes,
  and there is no refresh step to forget. The alternative — having the app
  write rows here too — means two writers for one fact and inevitable drift.

* **Both source tabs feed it.** A crisis locks the chat before "Finish", so
  those people have a `Risk Flags` row and NO summary. Someone who calmly asks
  for support has a summary and no flag. Reading only one tab silently drops
  half the queue; this is the same mistake the Executive Report's sector block
  made until it was fixed on 24 Aug.

* **The reviewer's own columns (G-J) are typed in and never overwritten.**
  They sit to the right of the formula block so a rebuild cannot touch them —
  but note a rebuild does NOT preserve the row-to-person alignment if the
  underlying data changed, so review notes belong in `Risk Flags` H-J for
  anything that must survive. See the warning printed at the end.

* **Trigger text is never shown.** The words someone typed in distress go to
  the alert email only. This tab reports the fact of the flag, its risk band,
  and a link to the transcript for anyone who needs the full context.

Reads credentials the same way the app does, so it needs `service_account.json`
(or `GOOGLE_CREDENTIALS_JSON`) and must be run from the `citta-companion`
directory.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

import config

QUEUE_ROWS = 200       # how many follow-up lines the view allows for
SHEET_ID = 1865243568  # Admin Review

CS = "'Chat Summaries'"
RF = "'Risk Flags'"

# Risk bands that put someone in the queue when they appear in a summary.
# Green and Yellow are preventive/mild and are not chased individually.
FOLLOW_UP_BANDS = '{"Amber";"Red";"Crisis"}'

HEADERS = [
    "Employee ID",          # A - formula
    "Source",               # B - formula
    "Date",                 # C - formula
    "Risk Category",        # D - formula
    "Human Support",        # E - formula
    "Transcript",           # F - formula
    "Assigned To",          # G - typed by Citta
    "Contacted On",         # H - typed by Citta
    "Outcome",              # I - typed by Citta
    "Internal Notes",       # J - typed by Citta
]

TITLE = [
    ["Citta Companion — Admin Review"],
    ["Internal follow-up queue. Everyone flagged at Crisis, or summarised at "
     "Amber/Red/Crisis, or who asked to speak to a human."],
    ["Columns A-F update themselves from Risk Flags and Chat Summaries. "
     "Columns G-J are yours to fill in. The words that triggered a flag are "
     "never shown here — they go to the alert email only."],
]

HEADER_ROW = 5          # 1-indexed row holding HEADERS
FIRST_QUEUE_ROW = HEADER_ROW + 1


def queue_formula() -> str:
    """One array formula producing the whole queue: flags first, then summaries.

    Two stacked blocks:
      1. every Risk Flags row (all of them are escalations by definition)
      2. Chat Summaries rows at Amber/Red/Crisis OR asking for human support,
         excluding anyone already listed above so nobody appears twice.

    Three Sheets traps this formula has to route around, all of which fail
    SILENTLY rather than erroring — the reason it is written this awkwardly:

    * A brace literal ``{range, "constant", range}`` does NOT broadcast the
      constant down the rows. The Source column therefore uses
      ``IF(range<>"", "Crisis flag", "")`` so every row computes its own value.

    * Both tabs store their date as TEXT ("2026-08-24 13:06:42 UTC"), written
      by ``_now()`` in google_sheets.py. ``TEXT(...,"yyyy-mm-dd")`` is a no-op
      on a string, so the full timestamp came through; ``LEFT(...,10)`` takes
      the date portion. If those writers ever emit real date values, switch
      this back to TEXT().

    * ``COUNTIF`` used as a *criterion inside* FILTER does not evaluate per
      row. Measured here: it returned 989 where the answer was 0 — the same
      trap already documented in EXECUTIVE_REPORT.md. ``COUNTIF`` wrapped in
      ``ISNA(MATCH(...))`` evaluates row-wise correctly.

    * ``FILTER`` returns #N/A when nothing matches, and one #N/A anywhere in a
      VSTACK poisons the whole result. Each block gets its own IFERROR so an
      empty half cannot blank the other half.
    """
    flags = (
        f'IFERROR(FILTER('
        f'{{{RF}!A2:A,'
        f'IF({RF}!A2:A<>"","Crisis flag",""),'
        f'IF({RF}!A2:A<>"",LEFT({RF}!B2:B,10),""),'
        f'{RF}!C2:C,{RF}!F2:F,{RF}!K2:K}},'
        f'{RF}!A2:A<>""),)'
    )
    summaries = (
        f'IFERROR(FILTER('
        f'{{{CS}!A2:A,'
        f'IF({CS}!A2:A<>"","Conversation",""),'
        f'IF({CS}!A2:A<>"",LEFT({CS}!B2:B,10),""),'
        f'{CS}!M2:M,{CS}!K2:K,{CS}!N2:N}},'
        # In the queue if the band warrants it OR they asked for a human...
        f'(ISNUMBER(MATCH({CS}!M2:M,{FOLLOW_UP_BANDS},0))+({CS}!K2:K="Yes"))>0,'
        # ...and not already listed as a flag above. MATCH, not COUNTIF.
        f'ISNA(MATCH({CS}!A2:A,{RF}!A2:A,0)),'
        f'{CS}!A2:A<>""),)'
    )
    # Each block is included ONLY if its source tab has rows. An empty FILTER
    # still occupies one row inside VSTACK whatever its fallback is — measured:
    # ROWS()=1 while COUNTA()=0, with `,""` and with a bare `,` alike. That
    # phantom row rendered as an empty line 6 above the first real entry.
    # CHOOSEROWS/TOCOL tricks all inherit the same problem, so the fix is to
    # not stack an empty block at all.
    has_flags = f'COUNTA({RF}!A2:A)>0'
    has_summaries = (
        f'SUMPRODUCT(({CS}!A2:A<>"")*'
        f'((ISNUMBER(MATCH({CS}!M2:M,{FOLLOW_UP_BANDS},0))+({CS}!K2:K="Yes"))>0)*'
        f'(ISNA(MATCH({CS}!A2:A,{RF}!A2:A,0))))>0'
    )
    return (
        f'=IFERROR('
        f'IF({has_flags},'
        f'IF({has_summaries},VSTACK({flags},{summaries}),{flags}),'
        f'IF({has_summaries},{summaries},"")),)'
    )


def build_values() -> list[list]:
    rows: list[list] = []
    for line in TITLE:
        rows.append(line + [""] * (len(HEADERS) - 1))
    rows.append([""] * len(HEADERS))
    rows.append(HEADERS)
    # A single array formula in A6 spills across A:F for as many rows as match.
    rows.append([queue_formula()] + [""] * (len(HEADERS) - 1))
    return rows


ACCENT = {"red": 0.541, "green": 0.392, "blue": 0.125}
SOFT = {"red": 0.961, "green": 0.937, "blue": 0.894}
MUTED = {"red": 0.55, "green": 0.52, "blue": 0.48}
INPUT_TINT = {"red": 0.988, "green": 0.984, "blue": 0.973}


def _fmt(r0, r1, cell, fields, c0=0, c1=10):
    return {"repeatCell": {
        "range": {"sheetId": SHEET_ID, "startRowIndex": r0, "endRowIndex": r1,
                  "startColumnIndex": c0, "endColumnIndex": c1},
        "cell": cell, "fields": fields}}


def _width(c0, c1, px):
    return {"updateDimensionProperties": {
        "range": {"sheetId": SHEET_ID, "dimension": "COLUMNS",
                  "startIndex": c0, "endIndex": c1},
        "properties": {"pixelSize": px}, "fields": "pixelSize"}}


def formatting_requests():
    last = FIRST_QUEUE_ROW + QUEUE_ROWS
    reqs = [
        {"clearBasicFilter": {"sheetId": SHEET_ID}},
        # Reset everything first: a rebuild moves rows, and a format left
        # behind by an earlier layout silently restyles whatever lands there.
        _fmt(0, 400, {"userEnteredFormat": {}}, "userEnteredFormat", 0, 26),
        # Clear inherited data validation across the whole tab before adding
        # our own. This tab shipped with dropdowns from an older column layout
        # (B "Risk Category", C "Human Support", D "Review Status"). Those
        # columns now hold "Conversation" and a date, so every cell was marked
        # invalid with a red corner triangle — the sheet reporting that our own
        # formula output violated a rule nobody had removed. Clearing formats
        # does NOT clear validation; it needs its own request.
        {"setDataValidation": {
            "range": {"sheetId": SHEET_ID, "startRowIndex": 0,
                      "endRowIndex": 400, "startColumnIndex": 0,
                      "endColumnIndex": 26}}},
        {"updateSheetProperties": {
            "properties": {"sheetId": SHEET_ID, "gridProperties": {
                "hideGridlines": True, "frozenRowCount": HEADER_ROW}},
            "fields": "gridProperties(hideGridlines,frozenRowCount)"}},
        _fmt(0, 1, {"userEnteredFormat": {"textFormat": {
            "bold": True, "fontSize": 15, "foregroundColor": ACCENT}}},
            "userEnteredFormat.textFormat"),
        _fmt(1, 3, {"userEnteredFormat": {"textFormat": {
            "italic": True, "fontSize": 9, "foregroundColor": MUTED}}},
            "userEnteredFormat.textFormat"),
        # Header strip.
        _fmt(HEADER_ROW - 1, HEADER_ROW, {"userEnteredFormat": {
            "backgroundColor": ACCENT,
            "textFormat": {"bold": True, "fontSize": 10,
                           "foregroundColor": {"red": 1, "green": 1, "blue": 1}}}},
            "userEnteredFormat(backgroundColor,textFormat)"),
        # The reviewer's own columns get a tint, so it is obvious at a glance
        # which half of the sheet is safe to type in.
        _fmt(HEADER_ROW, last, {"userEnteredFormat": {
            "backgroundColor": INPUT_TINT}},
            "userEnteredFormat.backgroundColor", 6, 10),
        _fmt(0, last, {"userEnteredFormat": {
            "verticalAlignment": "MIDDLE",
            "padding": {"top": 3, "bottom": 3, "left": 10, "right": 10}}},
            "userEnteredFormat(verticalAlignment,padding)"),
        _width(0, 1, 130),   # Employee ID
        _width(1, 2, 105),   # Source
        _width(2, 3, 95),    # Date
        _width(3, 4, 105),   # Risk Category
        _width(4, 5, 115),   # Human Support
        _width(5, 6, 190),   # Transcript
        _width(6, 10, 150),  # reviewer columns
    ]

    # Risk bands carry meaning — colour column D like the Executive Report.
    for band, colour in [
            ("Amber",  {"red": 0.76, "green": 0.44, "blue": 0.06}),
            ("Red",    {"red": 0.70, "green": 0.20, "blue": 0.14}),
            ("Crisis", {"red": 0.54, "green": 0.11, "blue": 0.08})]:
        reqs.append({"addConditionalFormatRule": {"rule": {
            "ranges": [{"sheetId": SHEET_ID,
                        "startRowIndex": HEADER_ROW, "endRowIndex": last,
                        "startColumnIndex": 3, "endColumnIndex": 4}],
            "booleanRule": {
                "condition": {"type": "TEXT_EQ",
                              "values": [{"userEnteredValue": band}]},
                "format": {"textFormat": {"bold": True,
                                          "foregroundColor": colour}}}},
            "index": 0}})

    # A whole-row wash for crisis lines: the queue must not read as a flat list
    # when one line is someone in danger and the next is a routine callback.
    reqs.append({"addConditionalFormatRule": {"rule": {
        "ranges": [{"sheetId": SHEET_ID,
                    "startRowIndex": HEADER_ROW, "endRowIndex": last,
                    "startColumnIndex": 0, "endColumnIndex": 10}],
        "booleanRule": {
            "condition": {"type": "CUSTOM_FORMULA", "values": [
                {"userEnteredValue": f'=$D{FIRST_QUEUE_ROW}="Crisis"'}]},
            "format": {"backgroundColor": {
                "red": 0.996, "green": 0.949, "blue": 0.941}}}},
        "index": 0}})

    # Dropdowns for the reviewer's columns, so the queue stays sortable.
    reqs.append({"setDataValidation": {
        "range": {"sheetId": SHEET_ID,
                  "startRowIndex": HEADER_ROW, "endRowIndex": last,
                  "startColumnIndex": 8, "endColumnIndex": 9},
        "rule": {"condition": {"type": "ONE_OF_LIST", "values": [
            {"userEnteredValue": v} for v in
            ["Not started", "Attempted contact", "Contacted",
             "Referred to clinician", "Closed — no action needed"]]},
            "showCustomUi": True, "strict": False}}})
    return reqs


def main() -> None:
    creds = Credentials.from_service_account_file(
        config.GOOGLE_CREDENTIALS_FILE,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    service = build("sheets", "v4", credentials=creds)
    sheets = service.spreadsheets()
    key = config.GOOGLE_SHEET_KEY

    values = build_values()
    sheets.values().clear(
        spreadsheetId=key, range="'Admin Review'!A1:Z400", body={}
    ).execute()
    sheets.values().update(
        spreadsheetId=key,
        range="'Admin Review'!A1",
        valueInputOption="USER_ENTERED",
        body={"values": values},
    ).execute()
    sheets.batchUpdate(
        spreadsheetId=key, body={"requests": formatting_requests()}
    ).execute()

    print(f"Admin Review rebuilt: queue starts at row {FIRST_QUEUE_ROW}, "
          f"room for {QUEUE_ROWS} lines")
    print("NOTE: columns G-J are typed in by hand and are NOT preserved by a "
          "rebuild — anything that must survive belongs in Risk Flags H-J.")


if __name__ == "__main__":
    main()
