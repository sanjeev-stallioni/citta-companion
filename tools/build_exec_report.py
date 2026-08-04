"""Rebuild the Executive Report tab from scratch.

    cd citta-companion && python3 tools/build_exec_report.py

Safe to re-run at any time: it clears the tab and rewrites it. Nothing is lost,
because the tab holds no typed-in data — every figure is a formula.

Design notes:

* Every figure is a live formula over `Chat Summaries` / `Risk Flags` /
  `Employee Registry`. Nothing is copied, so nothing can go stale, and no
  individual response is ever reproduced here.
* Participants are counted as DISTINCT Employee IDs, not rows. A second
  conversation by the same person must not count as a second participant.
* Sector participation suppresses any group below MIN_GROUP. The scope requires
  sector-wise participation "where anonymity is protected"; in a 3-person
  department an Amber count identifies someone.

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

MIN_GROUP = 5          # suppress sector rows below this headcount
SECTOR_ROWS = 12       # how many sector lines the block allows for
SHEET_ID = 773585386   # Executive Report

CS = "'Chat Summaries'"
RF = "'Risk Flags'"
ER = "'Employee Registry'"

# Distinct completed participants: unique IDs present in Chat Summaries.
#
# COUNTUNIQUEIFS, not COUNTA(UNIQUE(FILTER(...))). FILTER returns #N/A when
# nothing matches, and wrapping that in COUNTA counts the error itself as one
# item — so every empty risk category reported 1 instead of 0.
DISTINCT = f'COUNTUNIQUEIFS({CS}!A2:A,{CS}!A2:A,"<>")'
# Distinct IDs at a given risk category.
def risk(cat):
    return f'COUNTUNIQUEIFS({CS}!A2:A,{CS}!A2:A,"<>",{CS}!M2:M,"{cat}")'


# People at crisis, from either tab, counted once each.
#   flagged           - distinct IDs in Risk Flags
#   summarised crisis - distinct IDs whose summary says Crisis
#   overlap           - summarised-crisis IDs that are also flagged
CRISIS_PEOPLE = (
    f'COUNTUNIQUEIFS({RF}!A2:A,{RF}!A2:A,"<>")'
    f'+{risk("Crisis")}'
    f'-SUMPRODUCT(({CS}!M2:M="Crisis")*({CS}!A2:A<>"")'
    f'*(COUNTIF({RF}!A2:A,{CS}!A2:A)>0))'
)

# Everyone who had a conversation: summarised, plus anyone flagged who never
# got that far. Participation must include people whose chat ended in crisis.
#
# SUMPRODUCT, not COUNTA(UNIQUE(FILTER(...))). A COUNTIF *inside* FILTER does
# not evaluate per row, so the "not already in Chat Summaries" condition
# silently fails to exclude anyone — measured: FILTER returned 1 where the
# answer was 0. SUMPRODUCT evaluates row by row and is correct.
#
# Counts flag ROWS not yet summarised. Two crisis flags for the same person
# would count twice; acceptable while each crisis locks its own conversation,
# and visible because Crisis escalations is reported separately.
PARTICIPANTS = (
    f'COUNTUNIQUEIFS({CS}!A2:A,{CS}!A2:A,"<>")'
    f'+SUMPRODUCT(({RF}!A2:A<>"")*(COUNTIF({CS}!A2:A,{RF}!A2:A)=0))'
)

ROWS = [
    ["Citta Companion — Executive Report", "", ""],
    ["De-identified. Contains no names, emails, phone numbers, individual "
     "answers, transcripts, or identifiable risk data.", "", ""],
    ["Generated live from the data tabs — figures update as conversations complete.", "", ""],
    ["", "", ""],

    ["PARTICIPATION", "", ""],
    ["Metric", "Value", "Notes"],
    ["Employees invited", f'=COUNTUNIQUEIFS({ER}!B2:B,{ER}!B2:B,"<>")',
     "Distinct Employee IDs in the registry"],
    ["Employees who had a conversation", f"={PARTICIPANTS}",
     "Distinct people. Includes crisis chats, which never reach a summary"],
    ["Participation rate", '=IF(B7=0,"—",B8/B7)', "Completed ÷ invited"],
    ["Conversations recorded", f'=COUNTIF({CS}!A2:A,"<>")',
     "Total rows; exceeds participants if anyone chats twice"],
    ["", "", ""],

    ["RISK CATEGORY DISTRIBUTION", "", ""],
    ["Category", "Employees", "Share"],
    ["Green",  f"={risk('Green')}",  '=IF($B$8=0,"—",B14/$B$8)'],
    ["Yellow", f"={risk('Yellow')}", '=IF($B$8=0,"—",B15/$B$8)'],
    ["Amber",  f"={risk('Amber')}",  '=IF($B$8=0,"—",B16/$B$8)'],
    ["Red",    f"={risk('Red')}",    '=IF($B$8=0,"—",B17/$B$8)'],
    # Crisis counts BOTH sources, deduplicated.
    #
    # A crisis locks the chat before "Finish", so those conversations never
    # write a Chat Summaries row. Counting summaries alone reported "Crisis 0"
    # in a pilot where people had genuinely reached crisis — the single most
    # consequential figure to under-report. Anyone appearing in both tabs (a
    # crisis on a later visit, after an earlier completed chat) is counted once.
    ["Crisis", f"={CRISIS_PEOPLE}", '=IF($B$8=0,"—",B18/$B$8)'],
    ["Uncategorised", '=MAX(0,$B$8-SUM(B14:B18))', '=IF($B$8=0,"—",B19/$B$8)'],
    ["", "", ""],

    ["HUMAN SUPPORT", "", ""],
    ["Metric", "Value", "Notes"],
    ["Employees requesting human support",
     f'=COUNTUNIQUEIFS({CS}!A2:A,{CS}!A2:A,"<>",{CS}!K2:K,"Yes")',
     "Distinct IDs answering Yes"],
    ["Percentage requesting human support", '=IF($B$8=0,"—",B23/$B$8)',
     "Scope item: percentage, not count"],
    ["Crisis escalations raised", f'=COUNTIF({RF}!A2:A,"<>")',
     "Rows in Risk Flags; count only, never the trigger text"],
    ["", "", ""],

    ["PARTICIPATION BY SECTOR", "", ""],
    [f"Groups smaller than {MIN_GROUP} people are suppressed to protect anonymity, "
     "as required by the scope.", "", ""],
    ["Sector", "Invited", "Completed"],
]

# Sector rows are generated from the registry's distinct sectors, with
# suppression applied to both columns.
SECTOR_START = len(ROWS) + 1  # 1-indexed row of the first sector line
for i in range(SECTOR_ROWS):
    r = SECTOR_START + i
    src = (f'IFERROR(INDEX(SORT(UNIQUE(FILTER({ER}!I2:I,{ER}!I2:I<>""))),{i+1},1),"")')
    invited = f'COUNTIF({ER}!I2:I,$A{r})'
    # Count registry rows for this sector whose ID also appears in Chat
    # Summaries. SUMPRODUCT tolerates no matches; FILTER would return #N/A.
    completed = (f'SUMPRODUCT(({ER}!I2:I=$A{r})*'
                 f'(COUNTIF({CS}!A2:A,{ER}!B2:B)>0))')
    ROWS.append([
        f"={src}",
        f'=IF($A{r}="","",IF({invited}<{MIN_GROUP},"Suppressed (n<{MIN_GROUP})",{invited}))',
        f'=IF($A{r}="","",IF({invited}<{MIN_GROUP},"Suppressed (n<{MIN_GROUP})",{completed}))',
    ])

# No THEMES section. The scope lists four theme items for this sheet (top
# stress themes, top burnout/pressure themes, suggested interventions,
# next-step packages); they were removed at the developer's direction on
# 4 Aug 2026, before ever being committed — there is no version of this file
# with theme generation in git. Raise with the client at sign-off before
# calling the report done; it would need rebuilding from scratch.

# Row numbers the formatter needs. Derived, not hardcoded, so inserting a
# metric above them doesn't silently paint the wrong rows.
def _row_of(label):
    for i, row in enumerate(ROWS):
        if row[0] == label:
            return i
    raise ValueError(f"row not found: {label}")


BANNERS = [_row_of(t) for t in
           ("PARTICIPATION", "RISK CATEGORY DISTRIBUTION", "HUMAN SUPPORT",
            "PARTICIPATION BY SECTOR")]
TABLE_HEADS = [_row_of("Metric"), _row_of("Category"), _row_of("Sector")]

ACCENT = {"red": 0.541, "green": 0.392, "blue": 0.125}   # the app's bronze
SOFT = {"red": 0.961, "green": 0.937, "blue": 0.894}
MUTED = {"red": 0.55, "green": 0.52, "blue": 0.48}


def _fmt(r0, r1, cell, fields, c0=0, c1=3):
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
    reqs = [
        # The tab was created as a data grid, so it carries a basic filter over
        # every column. On a report it just paints row 1 blue and hangs dropdown
        # arrows off the title. There is nothing here to filter.
        {"clearBasicFilter": {"sheetId": SHEET_ID}},
        # Hide gridlines and the unused columns, so this reads as a report
        # rather than a spreadsheet someone stopped filling in.
        {"updateSheetProperties": {
            "properties": {"sheetId": SHEET_ID, "gridProperties": {
                "hideGridlines": True, "frozenRowCount": 3}},
            "fields": "gridProperties(hideGridlines,frozenRowCount)"}},
        {"updateDimensionProperties": {
            "range": {"sheetId": SHEET_ID, "dimension": "COLUMNS",
                      "startIndex": 3, "endIndex": 26},
            "properties": {"hiddenByUser": True}, "fields": "hiddenByUser"}},
        _fmt(0, 1, {"userEnteredFormat": {"textFormat": {
            "bold": True, "fontSize": 15, "foregroundColor": ACCENT}}},
            "userEnteredFormat.textFormat"),
        _fmt(1, 3, {"userEnteredFormat": {"textFormat": {
            "italic": True, "fontSize": 9, "foregroundColor": MUTED}}},
            "userEnteredFormat.textFormat"),
        _width(0, 1, 330),
        _width(1, 3, 170),
        {"updateSheetProperties": {
            "properties": {"sheetId": SHEET_ID,
                           "gridProperties": {"frozenRowCount": 3}},
            "fields": "gridProperties.frozenRowCount"}},
    ]
    for r in BANNERS:
        reqs.append(_fmt(r, r + 1, {"userEnteredFormat": {
            "backgroundColor": ACCENT,
            "textFormat": {"bold": True, "fontSize": 10,
                           "foregroundColor": {"red": 1, "green": 1, "blue": 1}}}},
            "userEnteredFormat(backgroundColor,textFormat)"))
    for r in TABLE_HEADS:
        reqs.append(_fmt(r, r + 1, {"userEnteredFormat": {
            "backgroundColor": SOFT, "textFormat": {"bold": True}}},
            "userEnteredFormat(backgroundColor,textFormat)"))
    # Percentage cells: participation rate, the risk shares, support share.
    pct = [(_row_of("Participation rate"), 1, 2),
           (_row_of("Green"), 2, 3),
           (_row_of("Percentage requesting human support"), 1, 2)]
    reqs.append(_fmt(pct[0][0], pct[0][0] + 1, {"userEnteredFormat": {
        "numberFormat": {"type": "PERCENT", "pattern": "0.0%"}}},
        "userEnteredFormat.numberFormat", 1, 2))
    reqs.append(_fmt(pct[1][0], pct[1][0] + 6, {"userEnteredFormat": {
        "numberFormat": {"type": "PERCENT", "pattern": "0.0%"}}},
        "userEnteredFormat.numberFormat", 2, 3))
    reqs.append(_fmt(pct[2][0], pct[2][0] + 1, {"userEnteredFormat": {
        "numberFormat": {"type": "PERCENT", "pattern": "0.0%"}}},
        "userEnteredFormat.numberFormat", 1, 2))
    # --- readability -------------------------------------------------------
    # Padding and alignment across the whole block: labels left, figures right,
    # everything vertically centred so the taller section rows don't look
    # top-heavy.
    reqs.append(_fmt(0, len(ROWS), {"userEnteredFormat": {
        "verticalAlignment": "MIDDLE",
        "padding": {"top": 3, "bottom": 3, "left": 10, "right": 10}}},
        "userEnteredFormat(verticalAlignment,padding)"))
    reqs.append(_fmt(0, len(ROWS), {"userEnteredFormat": {
        "horizontalAlignment": "RIGHT"}},
        "userEnteredFormat.horizontalAlignment", 1, 2))
    # Notes are supporting detail — recede them so the figures lead.
    reqs.append(_fmt(0, len(ROWS), {"userEnteredFormat": {"textFormat": {
        "fontSize": 9, "foregroundColor": MUTED}}},
        "userEnteredFormat.textFormat", 2, 3))
    # ...but the Share column is a figure, not a note.
    share_top = _row_of("Green")
    reqs.append(_fmt(share_top, share_top + 6, {"userEnteredFormat": {
        "horizontalAlignment": "RIGHT",
        "textFormat": {"fontSize": 10, "foregroundColor": {
            "red": 0.14, "green": 0.12, "blue": 0.09}}}},
        "userEnteredFormat(horizontalAlignment,textFormat)", 2, 3))

    # Risk labels carry their own meaning — colour them accordingly.
    for label, colour in [
            ("Green",  {"red": 0.18, "green": 0.45, "blue": 0.22}),
            ("Yellow", {"red": 0.68, "green": 0.56, "blue": 0.05}),
            ("Amber",  {"red": 0.76, "green": 0.44, "blue": 0.06}),
            ("Red",    {"red": 0.70, "green": 0.20, "blue": 0.14}),
            ("Crisis", {"red": 0.54, "green": 0.11, "blue": 0.08})]:
        r = _row_of(label)
        reqs.append(_fmt(r, r + 1, {"userEnteredFormat": {"textFormat": {
            "bold": True, "foregroundColor": colour}}},
            "userEnteredFormat.textFormat", 0, 1))

    # The denominator every rate divides by — worth finding at a glance.
    r = _row_of("Employees who had a conversation")
    reqs.append(_fmt(r, r + 1, {"userEnteredFormat": {
        "textFormat": {"bold": True}}}, "userEnteredFormat.textFormat", 0, 2))

    # Breathing room above each section banner.
    for r in BANNERS[1:]:
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": SHEET_ID, "dimension": "ROWS",
                      "startIndex": r - 1, "endIndex": r},
            "properties": {"pixelSize": 28}, "fields": "pixelSize"}})
    return reqs


def main():
    creds = Credentials.from_service_account_file(
        config.GOOGLE_CREDENTIALS_FILE,
        scopes=["https://www.googleapis.com/auth/spreadsheets"])
    svc = build("sheets", "v4", credentials=creds).spreadsheets()

    svc.values().clear(spreadsheetId=config.GOOGLE_SHEET_KEY,
                       range="'Executive Report'!A1:Z200", body={}).execute()
    svc.values().update(
        spreadsheetId=config.GOOGLE_SHEET_KEY,
        range="'Executive Report'!A1",
        valueInputOption="USER_ENTERED",
        body={"values": ROWS}).execute()
    svc.batchUpdate(spreadsheetId=config.GOOGLE_SHEET_KEY,
                    body={"requests": formatting_requests()}).execute()

    print(f"Executive Report rebuilt: {len(ROWS)} rows, "
          f"sector block at row {SECTOR_START}, suppression n<{MIN_GROUP}")


if __name__ == "__main__":
    main()
