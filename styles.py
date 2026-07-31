"""UI styling for Citta Companion — matches the 'Citta Companion Chat' design.

Faithful port of the reference HTML: warm bronze-on-cream palette, Newsreader +
IBM Plex Sans typography, sidebar nav rail, labelled response cards, quick-reply
chips and a rounded composer. Supports light (default) and dark themes via CSS
custom properties re-injected each run — no JavaScript required.

All CSS/HTML lives here so ``app.py`` stays focused on flow control.
"""

from __future__ import annotations

import base64
import html
import re

import streamlit as st

import config

# ---------------------------------------------------------------------------
# Theme tokens (verbatim from the reference design)
# ---------------------------------------------------------------------------
_LIGHT = {
    "--bg": "#F6F2EA", "--panel": "#FFFDF9", "--surface": "#FFFFFF", "--surface-2": "#F1E9DB",
    "--line": "rgba(35,27,15,.10)", "--line-2": "rgba(35,27,15,.18)",
    "--text": "#241E16", "--text-2": "#6B6055", "--text-3": "#8D8277",
    "--accent": "#8A6420", "--accent-soft": "rgba(138,100,32,.10)", "--accent-ink": "#FFFFFF",
    "--bubble-user": "#8A6420", "--bubble-user-ink": "#FFF9EE",
    "--shadow": "0 1px 2px rgba(60,46,20,.07),0 10px 28px rgba(60,46,20,.06)", "--ring": "rgba(138,100,32,.28)",
    "--danger-bg": "#FBEAE6", "--danger-bd": "#E0A99D", "--danger-tx": "#8A2E20",
}

_FONTS = (
    "@import url('https://fonts.googleapis.com/css2?"
    "family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;1,6..72,400"
    "&family=IBM+Plex+Sans:wght@400;500;600&display=swap');"
)

_STATIC_CSS = """
html, body, [class*="css"], .stApp, input, textarea, button, select {
    font-family: 'IBM Plex Sans', system-ui, sans-serif !important;
}
/* Material icons render via font ligatures — the rule above must not apply. */
[data-testid="stIconMaterial"], .material-symbols-rounded, span[translate="no"] {
    font-family: 'Material Symbols Rounded' !important; }
.serif { font-family: 'Newsreader', serif !important; letter-spacing: -.01em; }
.stApp { background-color: var(--bg); color: var(--text); }
/* Full-bleed main column (so the header bar spans the whole area, as in the
   design); the conversation itself is re-centred to 760px further below. */
.block-container { max-width: 100% !important; padding: 0 10px 7rem !important; }
/* Hide Streamlit's chrome, but KEEP <header> and stToolbar alive: the
   "expand sidebar" button lives inside them and is only rendered while the
   rail is collapsed. Hiding them strands a collapsed sidebar. */
#MainMenu, footer, [data-testid="stDecoration"], [data-testid="stToolbarActions"],
[data-testid="stAppDeployButton"], [data-testid="stMainMenu"] { display: none !important; }
header[data-testid="stHeader"] { display: block !important; background: transparent !important;
    height: 0 !important; min-height: 0 !important; box-shadow: none !important;
    pointer-events: none !important; }
[data-testid="stToolbar"] { display: flex !important; background: transparent !important;
    pointer-events: none !important; }
/* This element *is* the button (not a wrapper), so style it directly. */
[data-testid="stExpandSidebarButton"] { pointer-events: auto !important;
    position: fixed !important; top: 15px !important; left: 14px !important; z-index: 1300 !important;
    width: 34px !important; height: 34px !important; border-radius: 10px !important;
    background-color: var(--surface) !important; border: 1px solid var(--line) !important;
    color: var(--text-2) !important; display: grid !important; place-items: center !important; }
[data-testid="stExpandSidebarButton"]:hover { color: var(--text) !important;
    border-color: var(--line-2) !important; }
/* Streamlit's Material glyph doesn't paint reliably here, so draw the menu
   icon with CSS instead (three rules, like the design's menu button). */
[data-testid="stExpandSidebarButton"] [data-testid="stIconMaterial"],
[data-testid="stExpandSidebarButton"] > span { display: none !important; }
[data-testid="stExpandSidebarButton"]::before { content: ""; width: 15px; height: 1.6px;
    background-color: currentColor; border-radius: 2px;
    box-shadow: 0 5px 0 currentColor, 0 -5px 0 currentColor; }
/* Keep the header title clear of that button while the rail is collapsed. */
.stApp:has([data-testid="stExpandSidebarButton"]) [class*="st-key-hdr"] { padding-left: 60px; }
h1,h2,h3,h4 { color: var(--text); }
p, li, span, label, div { color: var(--text); }
a { color: var(--accent); text-decoration: none; }
a:hover { color: var(--text); }
::placeholder { color: var(--text-3) !important; }
@keyframes rise { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }

/* ---------- Sidebar ---------- */
[data-testid="stSidebar"] { width: 292px !important; min-width: 0 !important;
    background-color: var(--panel) !important; border-right: 1px solid var(--line); }
/* Streamlit paints inner sidebar containers with the theme colour — override all */
[data-testid="stSidebar"] > div, [data-testid="stSidebarContent"],
[data-testid="stSidebarUserContent"], [data-testid="stSidebarHeader"],
[data-testid="stSidebarCollapseButton"] { background-color: var(--panel) !important; }
[data-testid="stSidebarHeader"] { border-bottom: none !important;
    height: 16px !important; min-height: 0 !important; padding: 0 !important; margin: 0; }
/* Rail padding matches the design (22px 18px). */
[data-testid="stSidebarContent"] { padding: 0 !important; }
[data-testid="stSidebarUserContent"] { padding: 22px 18px !important; }
[data-testid="stSidebarUserContent"] > div > div[data-testid="stVerticalBlock"] { gap: 0; }
.cc-sb-brand { display: flex; gap: 12px; align-items: center; margin-bottom: 4px; }
.cc-sb-brand .badge { width: 42px; height: 42px; border-radius: 13px; flex: none; display: grid; place-items: center;
    background-color: var(--accent); color: var(--accent-ink); }
.cc-sb-brand .badge svg { width: 20px; height: 20px; }
.cc-sb-brand .badge .logo-mark { width: 24px; height: 20px; }
.cc-ava-bot .logo-mark { width: 22px; height: 22px; }
.cc-consent .badge .logo-mark { width: 44px; height: 36px; }
.cc-sb-brand .t { font-family: 'Newsreader', serif; font-size: 19px; line-height: 1.15; }
.cc-sb-brand .s { font-size: 11.5px; color: var(--text-3); letter-spacing: .02em; margin-top: 2px; }

.cc-nav { display: flex; flex-direction: column; gap: 2px; margin: 18px 0 4px; }
.cc-nav .item { display: flex; align-items: center; gap: 11px; padding: 10px 12px; border-radius: 10px;
    color: var(--text-2); font-weight: 500; font-size: 14px; }
.cc-nav .item svg { width: 17px; height: 17px; flex: none; }
.cc-nav .item.active { background-color: var(--accent-soft); color: var(--text);
    box-shadow: inset 0 0 0 1px var(--line); }

.cc-sec-h { display: flex; align-items: center; gap: 8px; font-size: 10.5px; letter-spacing: .13em;
    text-transform: uppercase; color: var(--text-3); padding: 0 2px; margin: 20px 0 10px; }
.cc-sec-h svg { width: 13px; height: 13px; }
.cc-settings { background-color: var(--surface); border: 1px solid var(--line); border-radius: 12px;
    padding: 6px; display: flex; flex-direction: column; gap: 2px; }
.cc-settings .row { display: flex; justify-content: space-between; align-items: center; padding: 8px 10px;
    border-radius: 8px; font-size: 14px; }
.cc-settings .row span.k { color: var(--text-2); }
.cc-settings .row b { font-weight: 500; }
.cc-settings .row b.accent { color: var(--accent); }

.cc-session { display: flex; flex-direction: column; gap: 1px; font-size: 13px; }
.cc-session .row { display: flex; justify-content: space-between; align-items: center; padding: 9px 2px;
    border-bottom: 1px solid var(--line); }
.cc-session .row:last-child { border-bottom: none; }
.cc-session .row .k { color: var(--text-2); }
.cc-pill { padding: 2px 9px; border-radius: 99px; background-color: var(--surface-2);
    border: 1px solid var(--line); font-size: 11.5px; }
.cc-pill.live { display: inline-flex; align-items: center; gap: 6px; background-color: var(--accent-soft);
    color: var(--accent); border: none; font-weight: 500; }
.cc-pill.live .dot { width: 5px; height: 5px; border-radius: 99px; background-color: var(--accent); }
.cc-pill.crit { background-color: var(--danger-bg); color: var(--danger-tx); border: 1px solid var(--danger-bd); }

[class*="st-key-cbwrap"] { background-color: var(--surface); border: 1px solid var(--line-2);
    border-top: none; border-radius: 0 0 14px 14px; padding: 0 16px 16px; }

/* ---------- Header ---------- */
.cc-head { display: flex; align-items: baseline; column-gap: 10px; flex-wrap: wrap; }
.cc-head .title { font-family: 'Newsreader', serif; font-size: 18px; white-space: nowrap; }
.cc-head .sub { color: var(--text-3); font-size: 12.5px; white-space: nowrap; }
/* The injected <style> tag still occupies a flex child, and the column's 16px
   gap would push the header down — collapse those wrappers. */
[data-testid="stElementContainer"]:has(style) { display: none !important; }
/* Header bar: 64px tall, full width of the main area, single bottom rule. */
[class*="st-key-hdr"] { height: 64px !important; min-height: 64px !important;
    justify-content: center; margin: 0 0; padding: 0 0;
    border-bottom: 1px solid var(--line); }
[class*="st-key-hdr"] [data-testid="stHorizontalBlock"] { height: 64px; align-items: center; gap: 10px; }
[class*="st-key-hdr"] [data-testid="stElementContainer"] { margin: 0 !important; }
.cc-divider { height: 22px; }

/* ---------- Conversation column: re-centred to the design's 760px ---------- */
.cc-day, .cc-row, .cc-grid, .cc-panel { max-width: 760px; margin-left: auto !important; margin-right: auto !important; }
[class*="st-key-chips"] { max-width: 760px; margin: 0 auto; }

/* ---------- Day separator ---------- */
.cc-day { display: flex; align-items: center; gap: 14px; color: var(--text-3); font-size: 10.5px;
    letter-spacing: .14em; text-transform: uppercase; margin: 4px auto 22px; }
.cc-day::before, .cc-day::after { content: ""; flex: 1; height: 1px; background-color: transparent; }

/* ---------- Messages ---------- */
.cc-row { display: flex; gap: 14px; margin: 22px 0; animation: rise .35s ease both; }
.cc-row.user { justify-content: flex-end; align-items: flex-start; }
.cc-ava-bot { width: 32px; height: 32px; border-radius: 10px; flex: none; margin-top: 2px;
    background-color: var(--accent); color: var(--accent-ink); display: grid; place-items: center; }
.cc-ava-bot svg { width: 16px; height: 16px; }
.cc-ava-user { width: 32px; height: 32px; border-radius: 99px; flex: none; background-color: var(--surface-2);
    border: 1px solid var(--line-2); color: var(--text-2); display: grid; place-items: center; margin-top: 26px; }
.cc-ava-user svg { width: 16px; height: 16px; }
.cc-bot-body { min-width: 0; flex: 1; }
.cc-bot-meta { display: flex; align-items: baseline; gap: 9px; margin-bottom: 8px; }
.cc-bot-meta .name { font-weight: 600; font-size: 13px; }
.cc-bot-meta .time { color: var(--text-3); font-size: 11.5px; }
.cc-card { background-color: var(--surface); border: 1px solid var(--line); border-radius: 4px 16px 16px 16px;
    padding: 16px 20px; box-shadow: var(--shadow); line-height: 1.65; font-size: 14.5px; color: var(--text-2); }
.cc-card p { margin: 0 0 9px; } .cc-card p:last-child { margin-bottom: 0; }
.cc-card strong { color: var(--text); font-weight: 600; }
.cc-card ul { margin: 6px 0; padding-left: 18px; } .cc-card li { margin: 3px 0; }
.cc-card .hero { font-family: 'Newsreader', serif; font-size: 20px; line-height: 1.35; color: var(--text); }
.cc-note { display: flex; gap: 9px; align-items: flex-start; padding: 11px 13px; border-radius: 10px;
    background-color: var(--accent-soft); color: var(--text-2); font-size: 13px; line-height: 1.5; }
.cc-note svg { width: 15px; height: 15px; flex: none; margin-top: 2px; }
/* The English disclaimer sits under the translated one, quieter but legible. */
.cc-note-en { margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--line-2);
    color: var(--text-3); font-size: 12.5px; }
.cc-actions { display: flex; gap: 6px; margin-top: 9px; }
.cc-actions .act { width: 29px; height: 29px; border-radius: 8px; background: transparent; border: 1px solid var(--line);
    color: var(--text-3); display: grid; place-items: center; }
.cc-actions .act svg { width: 14px; height: 14px; }
.cc-user-wrap { max-width: 70%; display: flex; flex-direction: column; align-items: flex-end; }
.cc-user-time { color: var(--text-3); font-size: 11.5px; margin-bottom: 8px; }
.cc-bubble { background-color: var(--bubble-user); color: var(--bubble-user-ink); border-radius: 16px 4px 16px 16px;
    padding: 14px 18px; line-height: 1.6; font-size: 14.5px; }
.cc-bubble * { color: var(--bubble-user-ink) !important; }
.cc-bubble p { margin: 0; } .cc-bubble p + p { margin-top: 9px; }
.cc-crisis { background-color: var(--danger-bg); border: 1px solid var(--danger-bd); color: var(--danger-tx);
    border-radius: 4px 16px 16px 16px; padding: 16px 20px; line-height: 1.6; font-size: 14px; }
.cc-crisis strong { color: var(--text); }

/* ---------- Quick-reply chips label ---------- */
.cc-chiplabel { color: var(--text-3); font-size: 11px; letter-spacing: .04em; margin: 22px 0 8px 46px; }

/* ---------- Buttons ---------- */
div[data-testid="stButton"] > button[kind="secondary"] {
    background: transparent !important; border: 1px solid var(--line-2) !important; color: var(--text-2) !important;
    border-radius: 99px !important; font-size: 13px !important; font-weight: 500 !important;
    padding: .45rem .9rem !important; box-shadow: none !important; }
div[data-testid="stButton"] > button[kind="secondary"]:hover {
    background-color: var(--accent-soft) !important; color: var(--accent) !important;
    border-color: var(--accent) !important; }
div[data-testid="stButton"] > button[kind="primary"], .stFormSubmitButton > button {
    background-color: var(--accent) !important; color: var(--accent-ink) !important; border: none !important;
    border-radius: 12px !important; font-weight: 600 !important; padding: .55rem 1rem !important;
    box-shadow: var(--shadow) !important; transition: transform .15s ease, filter .2s !important; }
div[data-testid="stButton"] > button[kind="primary"] *, .stFormSubmitButton > button * {
    color: var(--accent-ink) !important; }
div[data-testid="stButton"] > button[kind="primary"]:hover { transform: translateY(-1px); filter: brightness(1.06); }
div[data-testid="stButton"] > button[kind="secondary"] * { color: inherit !important; }
button:focus-visible { outline: 3px solid var(--ring) !important; outline-offset: 2px; }

/* ---------- Composer ---------- */
[data-testid="stChatInput"] { background-color: var(--surface) !important;
    border-radius: 18px !important; box-shadow: var(--shadow) !important; }
/* Inner wrappers/textarea carry their own theme background — force to surface */
[data-testid="stChatInput"] > div, [data-testid="stChatInput"] div,
[data-testid="stChatInputTextArea"], [data-testid="stChatInput"] textarea {
    background-color: var(--surface) !important; }
[data-testid="stChatInput"] textarea { color: var(--text) !important; font-size: 14.5px !important; }
[data-testid="stChatInput"]:focus-within { border-color: var(--accent) !important; }
[data-testid="stChatInput"] button { background-color: var(--accent) !important; color: var(--accent-ink) !important;
    border-radius: 12px !important; }
[data-testid="stChatInput"] button svg { fill: var(--accent-ink) !important; color: var(--accent-ink) !important; }
.cc-foot { display: flex; justify-content: space-between; gap: 16px; margin-top: 9px; padding: 0 4px;
    color: var(--text-3); font-size: 11.5px; }

/* Bottom-pinned composer area: theme background, width aligned to content column */
[data-testid="stBottom"] { background-color: var(--bg) !important; position: relative; }
[data-testid="stBottom"] > div { background-color: var(--bg) !important; padding-bottom: 34px; }
[data-testid="stChatInput"] { max-width: 760px !important; margin: 0 auto !important; }
/* ::before paints beneath the composer's opaque background — lift it. */
[data-testid="stBottom"]::before { content: "Confidential · If you're in crisis, reach a human now";
    position: absolute; bottom: 12px; left: max(26px, calc((100% - 760px) / 2 + 4px));
    font-size: 11.5px; color: var(--text-3); z-index: 5; }
[data-testid="stBottom"]::after { content: "Enter to send";
    position: absolute; bottom: 12px; right: max(26px, calc((100% - 760px) / 2 + 4px));
    font-size: 11.5px; color: var(--text-3); }

/* ---------- Quick-reply chips: inline pills, indented under the bot card ---------- */
[class*="st-key-chips"] [data-testid="stHorizontalBlock"] {
    display: flex !important; flex-wrap: wrap; gap: 8px !important; padding-left: 46px; }
[class*="st-key-chips"] [data-testid="stColumn"] {
    width: auto !important; flex: 0 0 auto !important; min-width: 0 !important; }
[class*="st-key-chips"] button { white-space: nowrap !important; }
/* "Finish conversation" sits with the chips, indented under the bot card. */
[class*="st-key-finish"] { max-width: 760px; margin: 8px auto 0; }
[class*="st-key-finish"] [data-testid="stElementContainer"] { margin-left: 46px; }
[class*="st-key-finish"] button { white-space: nowrap !important; }

/* ---------- Streamlit alerts follow the palette ---------- */
[data-testid="stAlert"] { background-color: var(--surface) !important; border: 1px solid var(--line) !important;
    border-radius: 12px !important; }
[data-testid="stAlert"] * { color: var(--text) !important; }

/* ---------- Tooltips / popovers follow the theme ---------- */
[data-testid="stTooltipContent"], [data-baseweb="tooltip"] {
    background-color: var(--surface) !important; color: var(--text) !important;
    border: 1px solid var(--line-2) !important; border-radius: 8px !important; }
[data-testid="stTooltipContent"] * { color: var(--text) !important; }

/* ---------- Spinner / status follow the theme ---------- */
[data-testid="stSpinner"] * { color: var(--text-2) !important; }

/* ---------- Consent ---------- */
.cc-consent { text-align: center; padding: 30px 6px 4px; }
.cc-consent .badge { width: 74px; height: 74px; border-radius: 20px; margin: 0 auto 18px; display: grid;
    place-items: center; background-color: var(--accent); color: var(--accent-ink); }
.cc-consent .badge svg { width: 40px; height: 40px; }
.cc-consent h1 { font-family: 'Newsreader', serif; font-size: 34px; margin: 0; font-weight: 500; }
.cc-consent .sub { color: var(--text-3); margin-top: 6px; }
.cc-panel { background-color: var(--surface); border: 1px solid var(--line); border-radius: 16px;
    padding: 22px 24px; box-shadow: var(--shadow); }
.cc-lead { color: var(--text-2); line-height: 1.65; font-size: 14.5px; }

/* ---------- Summary ---------- */
/* The summary is emitted inside the bot shell, so its blocks fill that column
   instead of re-centring themselves on the 760px conversation width. */
.cc-bot-body .cc-grid, .cc-bot-body .cc-panel {
    max-width: none; margin-left: 0 !important; margin-right: 0 !important; }
.cc-sum-h { font-family: 'Newsreader', serif; font-size: 19px; font-weight: 500;
    color: var(--text); margin: 18px 0 10px; }
.cc-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 6px 0; }
.cc-tile { background-color: var(--surface); border: 1px solid var(--line); border-radius: 13px; padding: 12px 14px; }
.cc-tile .k { color: var(--accent); font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: .05em; }
.cc-tile .v { color: var(--text); font-size: 14px; margin-top: 3px; }
@media (max-width: 640px) { .cc-grid { grid-template-columns: 1fr; } [data-testid="stSidebar"] { width: 260px !important; min-width: 260px !important; } }

hr { border-color: var(--line) !important; }
@media (prefers-reduced-motion: reduce) { * { animation: none !important; transition: none !important; } }
"""

# ---------------------------------------------------------------------------
# Icons (paths lifted from the reference for pixel fidelity)
# ---------------------------------------------------------------------------
def _s(body: str, size: int, *, fill: bool = False, sw: str = "1.6") -> str:
    attrs = 'fill="currentColor"' if fill else f'fill="none" stroke="currentColor" stroke-width="{sw}"'
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" {attrs} '
            f'stroke-linecap="round" stroke-linejoin="round">{body}</svg>')

# Brand mark (logo-mark-v2.png) rendered as a CSS mask filled with
# currentColor so it takes the badge's ink colour in both themes. Falls back
# to the original heart if the asset is missing.
def _brand_mark() -> str:
    logo_path = config.ASSETS_DIR / "logo-mark-v2.png"
    if logo_path.exists():
        uri = "data:image/png;base64," + base64.b64encode(logo_path.read_bytes()).decode()
        # Paint with --accent-ink (dark on the gold badge in dark mode, light
        # on the bronze badge in light mode). currentColor can't be used here:
        # the global `span { color: var(--text) }` rule would win.
        return (
            f'<span class="logo-mark" style="display:block;'
            f'background-color:var(--accent-ink);'
            f'-webkit-mask:url({uri}) center/contain no-repeat;'
            f'mask:url({uri}) center/contain no-repeat"></span>'
        )
    return _s('<path d="M12 20s-7-4.35-7-9.2A4.3 4.3 0 0 1 12 7.6a4.3 4.3 0 0 1 7 3.2C19 15.65 12 20 12 20Z"/>', 16, fill=True)


HEART = _brand_mark()
IC = {
    "chat": _s('<path d="M21 12a8 8 0 0 1-8 8H7l-4 3 1-5a8 8 0 1 1 17-6Z"/>', 17),
    "history": _s('<path d="M12 8v4l3 2"/><path d="M3.5 12a8.5 8.5 0 1 0 2.6-6.1M3.5 5v4h4"/>', 17),
    "personas": _s('<circle cx="9" cy="9" r="3"/><path d="M3.5 19c.7-3 3-4.5 5.5-4.5S14 16 14.7 19M16 7.5a3 3 0 0 1 0 5.6M18.5 5.6a5.6 5.6 0 0 1 0 9.4"/>', 17),
    "gear": _s('<circle cx="12" cy="12" r="3.2"/><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M18.4 5.6 17 7M7 17l-1.4 1.4"/>', 13, sw="1.7"),
    "shield": _s('<path d="M12 3l7 3v5.5c0 4-3 7.4-7 8.5-4-1.1-7-4.5-7-8.5V6l7-3Z"/>', 16),
    "person": _s('<circle cx="12" cy="9" r="3.2"/><path d="M5 20c.9-3.4 3.6-5 7-5s6.1 1.6 7 5"/>', 16),
    "lock": _s('<rect x="4.5" y="10" width="15" height="9.5" rx="2.2"/><path d="M8.2 10V7.6a3.8 3.8 0 0 1 7.6 0V10"/>', 15, sw="1.7"),
    "like": _s('<path d="M7 21V10l4-7 1 1v5h5.5A2.5 2.5 0 0 1 20 11.5l-1.4 7A2.5 2.5 0 0 1 16 21H7Z"/>', 14),
    "dislike": _s('<path d="M17 3v11l-4 7-1-1v-5H6.5A2.5 2.5 0 0 1 4 12.5l1.4-7A2.5 2.5 0 0 1 8 3h9Z"/>', 14),
    "copy": _s('<rect x="9" y="9" width="11" height="11" rx="2.4"/><path d="M15 5.5A2.5 2.5 0 0 0 12.5 4H6.4A2.4 2.4 0 0 0 4 6.4V13a2.5 2.5 0 0 0 1.5 2.3"/>', 14),
    "warn": _s('<path d="M12 3.5 22 20H2z"/><path d="M12 10v4"/><path d="M12 17h.01"/>', 40),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def inject() -> None:
    """Inject fonts + palette + component CSS. Re-run each render."""
    root = ":root{" + ";".join(f"{k}:{v}" for k, v in _LIGHT.items()) + "}"
    st.markdown(f"<style>{_FONTS}{root}{_STATIC_CSS}</style>", unsafe_allow_html=True)


def md_to_html(text: str) -> str:
    """Minimal, safe markdown → HTML (bold, links, bullets, line breaks)."""
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\[(.+?)\]\((https?://[^\s)]+)\)", r'<a href="\2" target="_blank">\1</a>', text)
    bullet = re.compile(r"^\s*[-*]\s+")
    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [ln for ln in block.split("\n") if ln.strip()]
        if lines and all(bullet.match(ln) for ln in lines):
            out.append("<ul>" + "".join("<li>" + bullet.sub("", ln) + "</li>" for ln in lines) + "</ul>")
        else:
            out.append("<p>" + "<br>".join(lines) + "</p>")
    return "".join(out)


def render_sidebar(*, sector: str, language: str, employee_id: str,
                   risk_label: str, risk_kind: str, status_label: str,
                   status_kind: str, tone: str = "Empathetic", formality: str = "Warm") -> None:
    """Render the full navigation rail matching the reference design."""
    risk_cls = "cc-pill crit" if risk_kind == "crit" else "cc-pill"
    if status_kind in ("ok",):
        status_html = f'<span class="cc-pill live"><span class="dot"></span>{status_label}</span>'
    elif status_kind == "crit":
        status_html = f'<span class="cc-pill crit">{status_label}</span>'
    else:
        status_html = f'<span class="cc-pill">{status_label}</span>'

    st.markdown(
        f"""
        <div class="cc-sb-brand">
            <div class="badge">{HEART}</div>
            <div><div class="t">{config.APP_TITLE}</div><div class="s">{config.APP_SUBTITLE}</div></div>
        </div>
        <div class="cc-nav">
            <div class="item active">{IC['chat']}Chat</div>
        </div>
        <div class="cc-sec-h">Session</div>
        <div class="cc-session">
            <div class="row"><span class="k">Employee ID</span><span>{employee_id}</span></div>
            <div class="row"><span class="k">Sector</span><span>{sector}</span></div>
            <div class="row"><span class="k">Language</span><span>{language}</span></div>
            <div class="row"><span class="k">Current risk</span><span class="{risk_cls}">{risk_label}</span></div>
            <div class="row"><span class="k">Status</span>{status_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )



def render_header_left() -> str:
    """HTML for the header title block (left side)."""
    return (
        '<div class="cc-head"><span class="title">Wellbeing Discovery</span>'
        '<span class="sub">Private · not shared with your employer</span></div>'
    )



def header_divider() -> None:
    st.markdown('<div class="cc-divider"></div>', unsafe_allow_html=True)


def day_separator(text: str) -> None:
    st.markdown(f'<div class="cc-day">{text}</div>', unsafe_allow_html=True)


def render_user_message(content: str, ts: str) -> None:
    st.markdown(
        f'<div class="cc-row user"><div class="cc-user-wrap">'
        f'<div class="cc-user-time">{ts}</div>'
        f'<div class="cc-bubble">{md_to_html(content)}</div></div>'
        f'<div class="cc-ava-user">{IC["person"]}</div></div>',
        unsafe_allow_html=True,
    )


def _bot_shell(inner: str, ts: str) -> str:
    return (
        f'<div class="cc-row"><div class="cc-ava-bot">{HEART}</div>'
        f'<div class="cc-bot-body"><div class="cc-bot-meta">'
        f'<span class="name">{config.APP_TITLE}</span><span class="time">{ts}</span></div>'
        f'{inner}</div></div>'
    )


def render_bot_message(content: str, ts: str) -> None:
    inner = f'<div class="cc-card">{md_to_html(content)}</div>'
    st.markdown(_bot_shell(inner, ts), unsafe_allow_html=True)


def render_welcome(ts: str, copy: dict) -> None:
    """The designed hero greeting, in the employee's language.

    ``copy`` comes from ``prompts.get_welcome_copy``. Its ``note_en`` is the
    English disclaimer, shown beneath the translated one and blank when the
    employee's language is already English.
    """
    note_en = (
        f'<div class="cc-note-en">{html.escape(copy["note_en"])}</div>'
        if copy.get("note_en")
        else ""
    )
    card = (
        '<div class="cc-card">'
        f'<div class="hero">{html.escape(copy["hero"])}</div>'
        f'<p>{html.escape(copy["lead"])}</p>'
        f'<div class="cc-note">{IC["lock"]}'
        f'<div>{html.escape(copy["note"])}{note_en}</div></div>'
        f'<p>{html.escape(copy["question"])}</p></div>'
    )
    st.markdown(_bot_shell(card, ts), unsafe_allow_html=True)


def render_crisis_message(content: str, ts: str) -> None:
    inner = f'<div class="cc-crisis">{md_to_html(content)}</div>'
    st.markdown(_bot_shell(inner, ts), unsafe_allow_html=True)




def render_summary_block(
    pairs: list[tuple[str, str]], summary: str, recommendation: str, ts: str = ""
) -> None:
    """Render the closing summary as a single bot message.

    Built as one block on purpose. Streamlit's own ``st.success`` and headings
    span the full page, so mixing them with the 760px conversation column left
    the banner and the "Wellbeing Summary" heading hanging out to the left of
    the tiles. Everything here sits inside the bot shell instead, which keeps
    the summary aligned with the messages above it.
    """
    tiles = "".join(
        f'<div class="cc-tile"><div class="k">{k}</div>'
        f'<div class="v">{html.escape(str(v))}</div></div>'
        for k, v in pairs
    )
    inner = (
        '<div class="cc-card"><p>Thank you for sharing. Here\'s a gentle summary '
        "of our conversation.</p></div>"
        '<div class="cc-sum-h">Wellbeing Summary</div>'
        f'<div class="cc-grid">{tiles}</div>'
        '<div class="cc-panel" style="margin-top:12px">'
        '<p class="cc-lead" style="margin:0 0 8px">'
        f'<b style="color:var(--accent)">Summary.</b> {html.escape(summary)}</p>'
        '<p class="cc-lead" style="margin:0">'
        f'<b style="color:var(--accent)">Recommendation.</b> '
        f"{html.escape(recommendation)}</p></div>"
    )
    st.markdown(_bot_shell(inner, ts), unsafe_allow_html=True)


def render_invalid_link() -> None:
    """Shown when the URL has no valid signed token."""
    st.markdown(
        f"""
        <div class="cc-consent">
            <div class="badge">{HEART}</div>
            <h1>{config.APP_TITLE}</h1>
            <div class="sub">{config.APP_SUBTITLE}</div>
        </div>
        <div class="cc-panel" style="margin-top:22px;max-width:560px;
             margin-left:auto;margin-right:auto">
            <p class="cc-lead" style="margin:0 0 10px"><b>This link isn't valid.</b></p>
            <p class="cc-lead" style="margin:0">Please open Citta Companion using the
            personal link from your invitation email. If the link has expired or
            isn't working, contact your wellbeing team for a new one.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
