"""Rebuild the Executive Report tab from scratch.

    cd citta-companion && python3 tools/build_exec_report.py

Safe to re-run at any time: it clears the tab and rewrites it. Nothing is lost,
because the tab holds no typed-in data — every figure is a formula.

Design notes:

* Every figure is a live formula over `Chat Summaries` / `Risk Flags` /
  `Employee Registry`. Nothing is copied, so nothing can go stale, and no
  individual response is ever reproduced here.
* Participants are counted as DISTINCT REGISTERED Employee IDs, not rows.
  A second conversation by the same person must not count as a second
  participant, and an ID absent from the registry (test chat, deleted
  registration) must not count at all — it once pushed participation past
  100%. Excluded rows surface in "Conversations from unregistered IDs".
* Sector participation suppresses any group below MIN_GROUP. The scope requires
  sector-wise participation "where anonymity is protected"; in a 3-person
  department an Amber count identifies someone.
* NOTHING on this tab is generated text. The theme rows count the stress and
  burnout levels the chatbot already recorded at the end of each conversation,
  so this script makes no AI calls at all and the tab cannot reproduce anyone's
  words. It replaced a Gemini theme generator on 27 Aug 2026 — see the THEMES
  block for why.

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

# Ranges are built with INDIRECT so Google cannot rewrite them.
#
# Make inserts each new registration as a ROW INSERT at the top of the data
# area, and Sheets helpfully "fixes" every formula pointing below it: a range
# written as B2:B silently became B3:B, then B4:B, drifting one row per
# registration. The report then read past its own data and declared every
# registered employee unregistered — invited 0, "Conversations from
# unregistered IDs" 2, with two perfectly good employees in the registry.
#
# This was misdiagnosed once as a stale rebuild (24 Aug). Rebuilding did fix
# it, but only by resetting ranges that promptly drifted again on the next two
# registrations. INDIRECT takes a STRING, so there is no reference for Sheets
# to adjust and the range means the same thing forever.
#
# Cost: INDIRECT is not lazily evaluated, so the tab recalculates a little more
# eagerly. At this data size that is irrelevant, and correctness wins.
def _r(tab: str, a1: str) -> str:
    """A range immune to row insertion, e.g. _r(ER, "B2:B")."""
    return f'INDIRECT("{tab}!{a1}")'


CS = "'Chat Summaries'"
RF = "'Risk Flags'"
ER = "'Employee Registry'"

# Every people-count below walks the REGISTRY and asks "does this person
# appear in the data tab?", never the other way round. Registry IDs are unique
# per person, so distinctness is free — and an ID that is not in the registry
# (a test chat, a self-minted link before the registry check existed, a row
# deleted after the fact) cannot inflate any figure. Counting the data tabs
# directly let those rows push the participation rate past 100%.
#
# The excluded rows are not hidden: "Conversations from unregistered IDs"
# reports them, and should read 0.
#
# SUMPRODUCT, not COUNTA(UNIQUE(FILTER(...))) and not COUNTIF inside FILTER —
# both fail silently (see EXECUTIVE_REPORT.md). COUNTIF/COUNTIFS with a range
# as the criterion evaluates per row inside SUMPRODUCT.

# Registered people whose summary says a given risk category.
def risk(cat):
    return (f'SUMPRODUCT(({_r(ER,"B2:B")}<>"")'
            f'*(COUNTIFS({_r(CS,"A2:A")},{_r(ER,"B2:B")},{_r(CS,"M2:M")},"{cat}")>0))')


# Registered people at crisis, from either tab, counted once each. A crisis
# locks the chat before "Finish", so those conversations often exist only as
# a Risk Flags row, never a summary.
CRISIS_PEOPLE = (
    f'SUMPRODUCT(({_r(ER,"B2:B")}<>"")'
    f'*((COUNTIF({_r(RF,"A2:A")},{_r(ER,"B2:B")})'
    f'+COUNTIFS({_r(CS,"A2:A")},{_r(ER,"B2:B")},{_r(CS,"M2:M")},"Crisis"))>0))'
)

# Registered people who had a conversation: a summary, a risk flag, or both.
PARTICIPANTS = (
    f'SUMPRODUCT(({_r(ER,"B2:B")}<>"")'
    f'*((COUNTIF({_r(CS,"A2:A")},{_r(ER,"B2:B")})+COUNTIF({_r(RF,"A2:A")},{_r(ER,"B2:B")}))>0))'
)

# Rows in the data tabs whose ID is NOT in the registry — the rows every
# figure above excludes. Anything other than 0 deserves a look.
UNMATCHED = (
    f'SUMPRODUCT(({_r(CS,"A2:A")}<>"")*(COUNTIF({_r(ER,"B2:B")},{_r(CS,"A2:A")})=0))'
    f'+SUMPRODUCT(({_r(RF,"A2:A")}<>"")*(COUNTIF({_r(ER,"B2:B")},{_r(RF,"A2:A")})=0))'
)

ROWS = [
    ["Citta Companion — Executive Report", "", ""],
    ["De-identified. Contains no names, emails, phone numbers, individual "
     "answers, transcripts, or identifiable risk data.", "", ""],
    ["Generated live from the data tabs — figures update as conversations complete.", "", ""],
    ["", "", ""],

    ["PARTICIPATION", "", ""],
    ["Metric", "Value", "Notes"],
    ["Employees invited", f'=COUNTUNIQUEIFS({_r(ER,"B2:B")},{_r(ER,"B2:B")},"<>")',
     "Distinct Employee IDs in the registry"],
    ["Employees who had a conversation", f"={PARTICIPANTS}",
     "Distinct registered people. Includes crisis chats, which never reach a summary"],
    ["Participation rate", '=IF(B7=0,"—",B8/B7)', "Completed ÷ invited"],
    ["Conversations recorded", f'=COUNTIF({_r(CS,"A2:A")},"<>")',
     "Total rows; exceeds participants if anyone chats twice"],
    ["Conversations from unregistered IDs", f"={UNMATCHED}",
     "Should be 0. Rows whose ID is not in the registry — test chats or "
     "deleted registrations; excluded from every figure above"],
    ["", "", ""],

    ["RISK CATEGORY DISTRIBUTION", "", ""],
    ["Category", "Employees", "Share"],
    ["Green",  f"={risk('Green')}",  '=IF($B$8=0,"—",B15/$B$8)'],
    ["Yellow", f"={risk('Yellow')}", '=IF($B$8=0,"—",B16/$B$8)'],
    ["Amber",  f"={risk('Amber')}",  '=IF($B$8=0,"—",B17/$B$8)'],
    ["Red",    f"={risk('Red')}",    '=IF($B$8=0,"—",B18/$B$8)'],
    # Crisis counts BOTH sources, deduplicated. Counting summaries alone
    # reported "Crisis 0" in a pilot where someone had genuinely reached
    # crisis — the single most consequential figure to under-report.
    ["Crisis", f"={CRISIS_PEOPLE}", '=IF($B$8=0,"—",B19/$B$8)'],
    ["Uncategorised", '=MAX(0,$B$8-SUM(B15:B19))', '=IF($B$8=0,"—",B20/$B$8)'],
    ["", "", ""],

    ["HUMAN SUPPORT", "", ""],
    ["Metric", "Value", "Notes"],
    ["Employees requesting human support",
     f'=SUMPRODUCT(({_r(ER,"B2:B")}<>"")'
     f'*(COUNTIFS({_r(CS,"A2:A")},{_r(ER,"B2:B")},{_r(CS,"K2:K")},"Yes")>0))',
     "Distinct registered people answering Yes"],
    ["Percentage requesting human support", '=IF($B$8=0,"—",B24/$B$8)',
     "Scope item: percentage, not count"],
    ["Crisis escalations raised", f'=COUNTIF({_r(RF,"A2:A")},"<>")',
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
    src = (f'IFERROR(INDEX(SORT(UNIQUE(FILTER({_r(ER,"I2:I")},{_r(ER,"I2:I")}<>""))),{i+1},1),"")')
    invited = f'COUNTIF({_r(ER,"I2:I")},$A{r})'
    # Count registry rows for this sector whose ID appears in Chat Summaries
    # OR Risk Flags. Both tabs, for the same reason the headline participation
    # figure counts both: a crisis locks the chat before "Finish", so those
    # people have a Risk Flags row and no summary. Counting summaries alone
    # reported a sector's completed as 0 while the person was in genuine
    # crisis — verified live on 24 Aug with two probe employees.
    #
    # SUMPRODUCT tolerates no matches; FILTER would return #N/A.
    completed = (f'SUMPRODUCT(({_r(ER,"I2:I")}=$A{r})*'
                 f'((COUNTIF({_r(CS,"A2:A")},{_r(ER,"B2:B")})'
                 f'+COUNTIF({_r(RF,"A2:A")},{_r(ER,"B2:B")}))>0))')
    ROWS.append([
        f"={src}",
        f'=IF($A{r}="","",IF({invited}<{MIN_GROUP},"Suppressed (n<{MIN_GROUP})",{invited}))',
        f'=IF($A{r}="","",IF({invited}<{MIN_GROUP},"Suppressed (n<{MIN_GROUP})",{completed}))',
    ])

# --- THEMES ---------------------------------------------------------------
#
# The scope asks this sheet for four theme rows. Two are built here — top
# stress themes and top burnout/workplace pressure themes. The other two,
# suggested intervention themes and suggested next-step packages, are not in
# this sheet at all: they need Citta's actual programme names and clinical
# review, and inventing them would be the same failure as the chatbot
# inventing a helpline number. See the note below the burnout block.
#
# These were originally generated by Gemini, which grouped the free-text
# summary fields into invented labels. That is gone, and the reasoning is
# worth keeping because it applies to any future "let the model summarise it"
# idea on this tab.
#
# The chatbot ALREADY classifies stress and burnout at the end of every
# conversation, into a closed vocabulary fixed in prompts.py:
#
#     stress_level : low / moderate / high / unclear
#     burnout      : none / mild / moderate / severe / unclear
#
# So the old code paid Gemini a second time to re-group values Gemini had
# already grouped, and stored the result as text that could not update itself.
# Counting the columns instead is not a workaround — it is reading the answer
# that was already computed. That buys, in one change:
#
#   * zero API calls per rebuild (was two)
#   * live formulas, so the block updates itself like every other figure and
#     needs no schedule, no cron, and no "last generated" stamp
#   * no generated text anywhere on this tab, so the sheet the EMPLOYER reads
#     is now structurally incapable of carrying an employee's words across.
#     That is a stronger guarantee than the three prompt rules it replaces.
#
# What was given up: emergent themes. Gemini could surface "childcare
# pressure" if several people raised it; a fixed vocabulary cannot. Columns
# F-I (sleep, workplace pressure, manager/team, coping) are still free text
# and still available if the client later wants richer themes. Raise it at
# sign-off rather than assuming the trade is welcome.
#
# Suppression still applies: a band below MIN_THEME_PEOPLE shows a dash, never
# a number. A band of one is a description of one identifiable person.
MIN_THEME_PEOPLE = 3      # a band below this shows "—", not a count

# "unclear" is deliberately absent from both lists. It is the model declining
# to classify, not a finding about anyone, and showing it as a theme would
# invite the employer to read meaning into a non-answer.
# ORDER MATTERS: worst first. Each band excludes anyone who also reported a
# band above it, so a person is counted once, in their most severe band.
STRESS_BANDS = [("High stress", "high"),
                ("Moderate stress", "moderate"),
                ("Low stress", "low")]
BURNOUT_BANDS = [("Severe burnout", "severe"),
                 ("Moderate burnout", "moderate"),
                 ("Mild burnout", "mild"),
                 ("No burnout reported", "none")]

# The five themes added Sep 2026, counted from the graded columns O-S written
# at the end of every conversation. Same mechanism as stress and burnout: a
# closed vocabulary the chatbot fills in, counted by formula, never generated.
#
# Each entry is (heading, column, bands worst-first). Worst-first matters —
# band() excludes anyone who also reported a band above, so a person is counted
# once, in their most severe band.
#
# "unclear" is deliberately never a band. It is the model declining to
# classify, not a finding about anyone, and showing it would invite the
# employer to read meaning into a non-answer.
EXTRA_THEMES = [
    ("Top sleep and fatigue themes", "O",
     [("Poor sleep", "poor"), ("Fair sleep", "fair"), ("Good sleep", "good")]),
    ("Top workplace pressure themes", "P",
     [("High pressure", "high"), ("Moderate pressure", "moderate"),
      ("Low pressure", "low")]),
    ("Top manager and team themes", "Q",
     [("Manager unsupportive", "unsupportive"), ("Manager support mixed", "mixed"),
      ("Manager supportive", "supportive")]),
    ("Top workplace conflict themes", "R",
     [("Significant conflict", "significant"), ("Some conflict", "some"),
      ("No conflict reported", "none")]),
    ("Coping themes", "S",
     [("No coping strategies", "none"), ("Limited coping", "limited"),
      ("Healthy coping", "healthy")]),
]


def band(col: str, value: str, higher: list) -> str:
    """Registered people whose HIGHEST severity in ``col`` is ``value``.

    Highest, not latest, and each person lands in exactly one band.

    "Latest" was tried first and failed silently: Session Date is stored as
    TEXT, so MAXIFS found no numbers, returned 0, and every band showed a dash
    that looked exactly like correct suppression. The same shape as every other
    bug on this tab — no error, plausible output, wrong.

    Highest is also the better rule for a wellbeing report. Someone who
    reported severe burnout in June and "none" in August still warrants
    attention, and under-stating severity is the dangerous direction to err in.
    Because a person is counted only in their worst band — ``higher`` lists the
    bands that outrank this one — the bands cannot double-count and sum to the
    participant total.
    """
    rng = _r(CS, f"{col}2:{col}")
    ids = _r(CS, "A2:A")
    me = _r(ER, "B2:B")
    has = f'COUNTIFS({ids},{me},{rng},"{value}")>0'
    if not higher:
        return f'SUMPRODUCT(({me}<>"")*({has}))'
    worse = "+".join(f'COUNTIFS({ids},{me},{rng},"{h}")' for h in higher)
    return f'SUMPRODUCT(({me}<>"")*({has})*(({worse})=0))'


def _band_row(label: str, col: str, value: str, higher: list) -> list:
    """One theme line: label, blank, suppressed count."""
    expr = band(col, value, higher)
    return [f"   {label}", "",
            f'=IF({expr}<{MIN_THEME_PEOPLE},"—",{expr})']


ROWS += [
    ["", "", ""],
    ["THEMES", "", ""],
    ["Counted from the wellbeing levels recorded at the end of each "
     "conversation. Within each theme a person is counted once, in their most "
     f"severe band. A band with fewer than {MIN_THEME_PEOPLE} people shows "
     "\u2014 rather than a count, so no band can describe one identifiable "
     "person.", "", ""],
    ["Top stress themes", "", "Employees"],
]
ROWS += [_band_row(lbl, "D", val, [v for _, v in STRESS_BANDS[:i]])
         for i, (lbl, val) in enumerate(STRESS_BANDS)]

ROWS += [
    ["Top burnout / workplace pressure themes", "", "Employees"],
]
ROWS += [_band_row(lbl, "E", val, [v for _, v in BURNOUT_BANDS[:i]])
         for i, (lbl, val) in enumerate(BURNOUT_BANDS)]

# The five themes added Sep 2026. Same shape as the two above.
for _head, _col, _bands in EXTRA_THEMES:
    ROWS += [[_head, "", "Employees"]]
    ROWS += [_band_row(lbl, _col, val, [v for _, v in _bands[:i]])
             for i, (lbl, val) in enumerate(_bands)]

# Help-seeking is not a severity scale, so it is not a band() call: column K
# already holds a plain Yes/No written at the end of every conversation. Only
# the "Yes" line is shown — a "No" count would tell the employer how many of
# their staff declined support, which is a step toward reading individuals and
# is no part of what this report is for.
_HELP = (f'SUMPRODUCT(({_r(ER,"B2:B")}<>"")'
         f'*(COUNTIFS({_r(CS,"A2:A")},{_r(ER,"B2:B")},{_r(CS,"K2:K")},"Yes")>0))')
ROWS += [
    ["Help-seeking interest", "", "Employees"],
    ["   Asked to speak with someone", "",
     f'=IF({_HELP}<{MIN_THEME_PEOPLE},"—",{_HELP})'],
]


def _row_of(label):
    for i, row in enumerate(ROWS):
        if row[0] == label:
            return i
    raise ValueError(f"row not found: {label}")


# --- RECOMMENDATIONS -------------------------------------------------------
#
# Sections E and F of the scope: "suggested intervention themes" and "suggested
# next-step packages or programmes". Unbuilt until now because they need
# Citta's real programme names and clinical judgement, and inventing either
# would be the same failure as the chatbot inventing a helpline number.
#
# The client resolved this on 1 Sep by scoping them as HYBRID, in their words:
# "basic data signals + editable recommendation text + final human review by
# Citta", and explicitly NOT "a clinical recommendation engine". The system
# must not diagnose, prescribe therapy, or determine individual treatment.
#
# So each line is a suggestion the sheet computes and a blank cell Citta fills
# in. The suggestion is a prompt for a human, never the thing that gets sent.
#
# TWO COLUMNS, NOT ONE. The suggestion is a formula in column B; Citta's final
# wording is typed into column C. Letting someone type over the suggestion
# would destroy the formula permanently — and the next report for that company
# would show a blank where a recommendation should be, which looks exactly like
# "no recommendation needed". Nobody would notice. Separating them removes the
# failure entirely.
#
# Thresholds live in named cells at the top of the block rather than buried in
# formulas, so Citta can retune them without touching a formula. The client
# said only "high"; these are defaults to be confirmed.
THRESH_SHARE = 0.30    # a theme covering this share of participants is "high"
THRESH_SUPPORT = 0.20  # this share asking for a human triggers the support line

ROWS += [
    ["", "", ""],
    ["RECOMMENDED INTERVENTIONS", "", ""],
    ["Suggested from the figures above. Citta reviews and rewrites every line "
     "before anything reaches an employer — the suggestions are a starting "
     "point, not a decision. Nothing here names or describes an individual.",
     "", ""],
    ["Threshold: theme share", THRESH_SHARE, "A theme above this share of participants counts as high"],
    ["Threshold: support share", THRESH_SUPPORT, "This share requesting human support triggers the support line"],
    ["Signal", "Suggested intervention", "Citta's final wording"],
]


def _bcell(label: str) -> str:
    """The B-column cell for a labelled row, e.g. the threshold cells."""
    return f"$B${_row_of(label) + 1}"


def _count_cell(label: str) -> str:
    """The C-column cell holding a theme's count, e.g. C47 for High stress.

    Resolved by label rather than a hard-coded row so reordering the themes
    cannot silently point a rule at the wrong figure.
    """
    return f"C{_row_of('   ' + label) + 1}"


def _share(label: str) -> str:
    """A theme's count as a share of participants.

    A suppressed band shows an em dash, not a number, so every rule has to
    tolerate text where it expects a figure. N() coerces the dash to 0 — a
    band too small to report is also too small to justify recommending a
    company-wide workshop, which is the same answer either way.
    """
    participants = _bcell("Employees who had a conversation")
    return f'IF({participants}=0,0,N({_count_cell(label)})/{participants})'


def _rule(signal: str, condition: str, suggestion: str) -> list:
    """One intervention line: what triggered it, the suggestion, blank for Citta."""
    return [signal, f'=IF({condition},"{suggestion}","")', ""]


# The client's own five rules, in their order. The wording is their category
# names, NOT Citta programme titles — those have been requested and are still
# outstanding. A report must not reach an employer recommending a workshop that
# does not exist under that name.
ROWS += [
    _rule("High stress or burnout",
          f'OR({_share("High stress")}>{_bcell("Threshold: theme share")},{_share("Severe burnout")}>{_bcell("Threshold: theme share")})',
          "Burnout / workload pressure workshop"),
    _rule("High stress",
          f'{_share("High stress")}>{_bcell("Threshold: theme share")}',
          "Stress and emotional regulation webinar"),
    _rule("Manager or team pressure",
          f'{_share("Manager unsupportive")}>{_bcell("Threshold: theme share")}',
          "Manager communication / psychological safety session"),
    _rule("Sleep and fatigue",
          f'{_share("Poor sleep")}>{_bcell("Threshold: theme share")}',
          "Sleep, fatigue and recovery webinar"),
    _rule("Workplace conflict",
          f'{_share("Significant conflict")}>{_bcell("Threshold: theme share")}',
          "Workplace conflict / team dynamics session"),
    _rule("Requests for human support",
          f'{_share("Asked to speak with someone")}>{_bcell("Threshold: support share")}',
          "Help-seeking and confidential support awareness session"),
    _rule("Voluntary interest in support",
          f'N({_count_cell("Asked to speak with someone")})>={MIN_THEME_PEOPLE}',
          "Group support / retreat-style programme for employees who express interest"),
]

# The client's fifth rule, and the most important one: high risk goes to Citta,
# NOT to the employer. Deliberately worded as an internal action so that even
# if this line were left in an exported report it recommends a Citta review
# rather than disclosing anything about an individual.
ROWS += [
    _rule("Elevated risk present",
          "OR(" + ",".join(f'N(C{_row_of(lbl) + 1})>0'
                           for lbl in ("Amber", "Red", "Crisis")) + ")",
          "Internal Citta review — not for employer-level individual disclosure"),
]


# --- NEXT-STEP RECOMMENDATION ----------------------------------------------
#
# Scope section F, "suggested next-step packages or programmes". Same hybrid
# shape as the interventions above, from the client's own suggested structure.
#
# The 30/60/90-day reassessment line is unconditional: it is a cadence, not a
# finding, and applies to every employer whatever their figures show.
ROWS += [
    ["", "", ""],
    ["NEXT-STEP RECOMMENDATION", "", ""],
    ["Suggested next steps from the same figures. As above, Citta finalises "
     "the wording before anything is sent.", "", ""],
    ["Signal", "Suggested next step", "Citta's final wording"],
]

ROWS += [
    _rule("Pilot completed",
          f'{_bcell("Employees who had a conversation")}>0',
          "Continue Citta Companion access as a retainer"),
    _rule("Top theme identified",
          f'{_bcell("Employees who had a conversation")}>={MIN_THEME_PEOPLE}',
          "Conduct one targeted webinar or workshop on the leading theme"),
    _rule("Manager or workplace pressure",
          f'OR({_share("Manager unsupportive")}>{_bcell("Threshold: theme share")},'
          f'{_share("High pressure")}>{_bcell("Threshold: theme share")})',
          "Offer a manager support session"),
    _rule("Enough voluntary interest",
          f'N({_count_cell("Asked to speak with someone")})>={MIN_THEME_PEOPLE}',
          "Offer voluntary group support or a retreat-style programme"),
    _rule("Support opt-ins recorded",
          f'N({_count_cell("Asked to speak with someone")})>0',
          "Review support opt-ins internally through Citta intake"),
    ["Review cadence", "Reassess after 30 / 60 / 90 days", ""],
]

# No "last generated" stamp any more, and that is the point: these are live
# formulas like everything else on the tab, so there is no generation moment
# to date. The stamp existed only because the AI version could go stale.

# The scope's other two theme rows — suggested intervention themes and
# suggested next-step packages — are NOT in this sheet. They need Citta's
# actual programme names and clinical review, and inventing them would be the
# same failure as the chatbot inventing a helpline number. Placeholder rows
# saying so were removed at the developer's direction on 27 Aug 2026.
# Raise the gap with the client at sign-off: the scope's stated purpose for
# this report ("support future upsell into deeper Citta programmes") rests on
# the packages row in particular.


BANNERS = [_row_of(t) for t in
           ("PARTICIPATION", "RISK CATEGORY DISTRIBUTION", "HUMAN SUPPORT",
            "PARTICIPATION BY SECTOR", "THEMES")]
# Theme category headings are sub-headings inside the THEMES block, not banners.
THEME_HEADS = [_row_of(t) for t in
               ["Top stress themes", "Top burnout / workplace pressure themes"]
               + [h for h, _, _ in EXTRA_THEMES]
               + ["Help-seeking interest"]]
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
        # Reset ALL formatting first. Rebuilds move rows, and a number format
        # left behind by an earlier layout silently restyles whatever lands on
        # that row next — a count of 1 once rendered as "100.0%" because the
        # percentage row had shifted down one.
        _fmt(0, 200, {"userEnteredFormat": {}}, "userEnteredFormat", 0, 26),
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

    # Theme sub-headings: bold, but not the full bronze banner treatment —
    # they sit inside the THEMES block rather than starting a new section.
    for r in THEME_HEADS:
        reqs.append(_fmt(r, r + 1, {"userEnteredFormat": {
            "backgroundColor": SOFT, "textFormat": {"bold": True}}},
            "userEnteredFormat(backgroundColor,textFormat)"))
    # Theme counts are figures: right-align them like every other count.
    # Found by label rather than by a start-row constant, so adding or
    # reordering a band cannot silently format the wrong rows.
    _count_rows = [lbl for lbl, _ in STRESS_BANDS + BURNOUT_BANDS]
    for _, _, _bands in EXTRA_THEMES:
        _count_rows += [lbl for lbl, _ in _bands]
    _count_rows.append("Asked to speak with someone")
    for label in _count_rows:
        r = _row_of(f"   {label}")
        reqs.append(_fmt(r, r + 1, {"userEnteredFormat": {
            "horizontalAlignment": "RIGHT",
            "textFormat": {"fontSize": 10, "foregroundColor": {
                "red": 0.14, "green": 0.12, "blue": 0.09}}}},
            "userEnteredFormat(horizontalAlignment,textFormat)", 2, 3))

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
