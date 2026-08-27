"""Citta Companion — AI-powered employee wellbeing discovery chatbot.

Run locally with:

    streamlit run app.py

This module owns the Streamlit UI and orchestrates the service modules. All
heavy lifting (Gemini, Sheets, email, risk detection) lives in dedicated
modules so this file stays focused on presentation and flow control.
"""

from __future__ import annotations

import logging
from datetime import datetime

import streamlit as st

import config
import styles
from email_service import (
    send_admin_alert,
    send_opt_in_alert,
    send_support_request_alert,
)
from gemini_service import (
    GeminiUnavailableError,
    generate_response,
    initialize_model,
)
from google_sheets import (
    contact_opt_in,
    mark_chat_completed,
    mark_chat_started,
    mark_summary_generated,
    save_chat_summary,
    save_risk_flag,
    save_support_lead,
)
from transcript_service import save_transcript
from prompts import (
    CRISIS_MESSAGE,
    FALLBACK_ERROR_MESSAGE,
    get_system_prompt,
    get_ui_copy,
    get_welcome_copy,
    get_welcome_message,
)
from risk_detection import (
    ALERT_RISK_LEVELS,
    RISK_CRISIS,
    detect_risk,
    matched_keywords,
)
from summary_generator import generate_summary
from utils import (
    conversation_status,
    get_query_params,
    init_session_state,
    language_label,
    risk_chip_kind,
    risk_label,
    status_chip_kind,
)

logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title=config.APP_TITLE,
    page_icon=config.APP_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
)

# Theme defaults to dark (as in the reference design); the header toggle flips
# it. Styles are re-injected each run.
styles.inject()


# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------
def load_params_once() -> None:
    """Read URL params into session state exactly once per session."""
    if not st.session_state.params_loaded:
        params = get_query_params()
        st.session_state.employee_id = params["employee_id"]
        st.session_state.sector = params["sector"]
        st.session_state.lang = params["lang"]
        st.session_state.link_valid = params["valid"]
        st.session_state.params_loaded = True


def ensure_model() -> bool:
    """Lazily initialise the Gemini model. Returns ``True`` if available."""
    if st.session_state.model is not None:
        return True
    try:
        system_prompt = get_system_prompt(
            st.session_state.sector, st.session_state.lang
        )
        st.session_state.model = initialize_model(system_prompt)
        return True
    except GeminiUnavailableError as exc:
        st.error(
            "Citta Companion can't connect to its AI service right now. "
            "Please check the configuration or try again later."
        )
        st.caption(f"Details: {exc}")
        return False


def _timestamp() -> str:
    """Human-friendly message timestamp, e.g. '10:09 AM'."""
    return datetime.now().strftime("%I:%M %p").lstrip("0")


def _add_message(role: str, content: str) -> None:
    st.session_state.messages.append(
        {"role": role, "content": content, "ts": _timestamp()}
    )


# ---------------------------------------------------------------------------
# Chrome
# ---------------------------------------------------------------------------
def render_sidebar() -> None:
    """Render the navigation rail with live session details."""
    risk = st.session_state.risk_category
    with st.sidebar:
        styles.render_sidebar(
            sector=st.session_state.sector,
            language=language_label(st.session_state.lang),
            employee_id=st.session_state.employee_id,
            risk_label=risk_label(risk),
            risk_kind=risk_chip_kind(risk),
            status_label=conversation_status(),
            status_kind=status_chip_kind(),
        )


def render_header() -> None:
    """Header bar: title and privacy note."""
    with st.container(key="hdr"):
        st.markdown(styles.render_header_left(), unsafe_allow_html=True)
    styles.header_divider()


# ---------------------------------------------------------------------------
# Conversation persistence / escalation
# ---------------------------------------------------------------------------
def handle_finish_conversation() -> None:
    """Generate a summary, persist it, and mark the conversation finished."""
    with st.spinner("Preparing your summary..."):
        summary = generate_summary(
            st.session_state.model,
            st.session_state.messages,
            st.session_state.risk_category,
        )
    st.session_state.summary = summary
    st.session_state.conversation_finished = True

    # Adopt the summary's assessed category as the session's risk.
    #
    # Until now this only ever moved on a keyword crisis, so a conversation the
    # model rated Amber still displayed "Green" in the sidebar and printed
    # "CURRENT RISK Green" at the top of the transcript — while the sheet said
    # Amber. A reviewer opening that PDF would read the header and stop.
    #
    # A locally-detected crisis still wins: _normalize already refuses to lower
    # it, so assigning here cannot downgrade an escalation.
    assessed = str(summary.get("risk_category", "")).strip().lower()
    if assessed:
        st.session_state.risk_category = assessed

    emp = st.session_state.employee_id
    sector = st.session_state.sector
    lang = st.session_state.lang

    # Archive the conversation before the summary row, so the row can carry the
    # link. A Drive failure returns "" rather than raising — losing the archive
    # must not also lose the summary.
    now = datetime.now()
    transcript_url = save_transcript(
        emp,
        now.strftime("%Y-%m-%d"),
        st.session_state.messages,
        language=language_label(lang),
        lang_code=lang,
        risk=risk_label(st.session_state.risk_category),
        status=conversation_status(),
        display_date=now.strftime("%d %B %Y"),
    )

    if not save_chat_summary(emp, sector, lang, summary, transcript_url):
        st.warning(
            "We couldn't save your summary to our records right now, but your "
            "conversation is still complete."
        )
    else:
        mark_summary_generated(emp)
    assessed_risk = str(summary.get("risk_category", "")).strip().lower()
    requested = str(summary.get("human_support_requested", "")).lower() == "yes"
    notes = summary.get("summary", "")

    # Read once and reuse: this is a Sheets round-trip, and the three branches
    # below would otherwise each make their own.
    opted_in = contact_opt_in(emp)

    if requested:
        save_support_lead(
            emp, sector, lang, "yes", notes,
            risk_category=summary.get("risk_category", ""),
        )
        # Alert as well as record. Writing the lead row only meant a request to
        # speak to a human sat in a spreadsheet nobody was watching — server.py
        # sent this alert from its callback endpoint, but the Streamlit path
        # never did, so the scope's "employee requests human support" alert
        # simply did not fire for the UI actually in use.
        send_support_request_alert(
            emp, sector, notes,
            risk_category=summary.get("risk_category", ""), opted_in=opted_in,
        )
    elif opted_in:
        # Opting in on the form is its own trigger in the scope, separate from
        # asking during the conversation. Someone who ticked the box and never
        # raised it in chat was previously never followed up at all: no lead
        # row, no alert. The scope's support-leads tab is explicitly for people
        # "who have consented OR requested further support".
        save_support_lead(
            emp, sector, lang, "no", notes,
            risk_category=summary.get("risk_category", ""),
        )
        send_opt_in_alert(
            emp, sector,
            risk_category=summary.get("risk_category", ""), notes=notes,
        )

    # Amber and Red raise an alert of their own.
    #
    # The scope asks for an alert when "the chatbot flags amber/red/crisis".
    # Only crisis did. A conversation assessed Red — severe distress, or being
    # unable to function — produced a spreadsheet row and no notification to
    # anybody, unless the person happened also to ask for human support. It sat
    # unread until someone opened the sheet.
    #
    # Crisis is excluded here because trigger_crisis has already alerted; a
    # second email for the same conversation would train people to skim them.
    if assessed_risk in ALERT_RISK_LEVELS and not st.session_state.crisis_triggered:
        send_admin_alert(
            emp, sector, assessed_risk,
            support_requested=requested, opted_in=opted_in,
        )

    mark_chat_completed(
        emp,
        st.session_state.risk_category,
        summary.get("human_support_requested", ""),
    )


def trigger_crisis(trigger_message: str) -> None:
    """Escalate to crisis state: flag, alert admin, and stop normal flow."""
    st.session_state.risk_category = RISK_CRISIS
    st.session_state.crisis_triggered = True

    keywords = matched_keywords(trigger_message)
    emp = st.session_state.employee_id
    sector = st.session_state.sector
    lang = st.session_state.lang

    # Alert first: the sheet records whether the admin was actually reached, and
    # the alert is the fastest path to a human. Nothing below may delay it.
    alerted = send_admin_alert(
        emp, sector, RISK_CRISIS, keywords, trigger_message,
        opted_in=contact_opt_in(emp),
    )

    # Archive before writing the flag, so the flag row can carry the link.
    #
    # This conversation never reaches "Finish" — a crisis locks the chat
    # immediately, and every other archive path hangs off that button. Without
    # this, the one conversation most likely to need reviewing would be the only
    # one with no transcript, while `Risk Flags` deliberately records the fact
    # of the flag rather than the words. The crisis reply is appended by the
    # caller after this returns, so it is included here explicitly.
    now = datetime.now()
    history = st.session_state.messages + [
        {"role": "assistant", "content": CRISIS_MESSAGE, "ts": _timestamp()}
    ]
    transcript_url = save_transcript(
        emp, now.strftime("%Y-%m-%d"), history,
        language=language_label(lang), lang_code=lang,
        risk=risk_label(RISK_CRISIS), status="Crisis — paused",
        display_date=now.strftime("%d %B %Y"),
    )

    save_risk_flag(
        emp, sector, lang, RISK_CRISIS, keywords, trigger_message,
        detection_method="keyword", admin_email_sent=alerted,
        transcript_url=transcript_url,
    )

    # A crisis locks the chat before "Finish", so this is the only place that
    # conversation's registry row gets marked — without it, a crisis chat
    # looks permanently abandoned in the registry rather than escalated.
    mark_chat_completed(emp, RISK_CRISIS)


def render_summary() -> None:
    """Display the structured summary after the conversation ends."""
    summary = st.session_state.summary or {}
    field_labels = {
        "overall_wellbeing": "Overall wellbeing",
        "stress_level": "Stress level",
        "sleep": "Sleep",
        "burnout": "Burnout",
        "workplace_pressure": "Workplace pressure",
        "manager_relationship": "Manager relationship",
        "coping_strategy": "Coping strategy",
        "human_support_requested": "Human support",
        "risk_category": "Risk category",
    }
    # Reuse the last message's timestamp rather than "now" — the summary is part
    # of that closing exchange, and a fresh clock would tick on every rerun.
    last = st.session_state.messages[-1] if st.session_state.messages else {}
    styles.render_summary_block(
        [(label, summary.get(key, "unclear")) for key, label in field_labels.items()],
        summary.get("summary", ""),
        summary.get("recommendation", ""),
        last.get("ts", ""),
    )


# ---------------------------------------------------------------------------
# Turn handling
# ---------------------------------------------------------------------------
def handle_turn(user_message: str) -> None:
    """Process one user message: crisis-check, generate reply, persist."""
    # Fire-and-forget, first turn only. This sits on the critical path of the
    # employee's first reply, so it must never block or retry — a missed
    # timestamp here is a visibility gap for Citta's team, not a data-loss risk.
    if len(st.session_state.messages) <= 1:
        mark_chat_started(st.session_state.employee_id)

    _add_message("user", user_message)

    if detect_risk(user_message) == RISK_CRISIS:
        trigger_crisis(user_message)
        _add_message("assistant", CRISIS_MESSAGE)
        st.rerun()
        return

    with st.spinner("Citta Companion is thinking…"):
        try:
            reply = generate_response(
                st.session_state.model,
                st.session_state.messages[:-1],
                user_message,
            )
        except GeminiUnavailableError:
            reply = FALLBACK_ERROR_MESSAGE
    _add_message("assistant", reply)
    st.rerun()


def render_messages() -> None:
    """Replay the conversation using the designed message cards."""
    styles.day_separator("Today")
    for i, message in enumerate(st.session_state.messages):
        ts = message.get("ts", "")
        if message["role"] == "user":
            styles.render_user_message(message["content"], ts)
        elif message["content"] == CRISIS_MESSAGE:
            styles.render_crisis_message(message["content"], ts)
        elif i == 0:
            # The first message is always the welcome, whatever language it is
            # in — matching on its text would break the moment a translation is
            # edited.
            styles.render_welcome(ts, get_welcome_copy(st.session_state.lang))
        else:
            styles.render_bot_message(message["content"], ts)


def render_chat() -> None:
    """Main chat interface (header, message stream, chips, composer)."""
    st.session_state.chat_started = True
    render_header()

    if not ensure_model():
        return

    if not st.session_state.messages:
        _add_message("assistant", get_welcome_message(st.session_state.lang))

    render_messages()

    if st.session_state.crisis_triggered:
        return
    if st.session_state.conversation_finished:
        render_summary()
        return

    ui = get_ui_copy(st.session_state.lang)

    # Quick-reply chips (functional — clicking sends that prompt). They are an
    # opener for someone who doesn't know how to start, so they appear under the
    # welcome only. Once the conversation is running they'd just compete with
    # whatever the employee was about to say.
    if len(st.session_state.messages) <= 1:
        with st.container(key="chips"):
            chip_cols = st.columns(len(ui["chips"]), gap="small")
            for i, (col, text) in enumerate(zip(chip_cols, ui["chips"])):
                # Keyed by position, not label — the labels are translated.
                if col.button(text, key=f"sug_{i}"):
                    handle_turn(text)

    # Composer.
    user_message = st.chat_input(ui["placeholder"])
    if user_message:
        handle_turn(user_message)

    # Finish action, once there's something to summarise.
    if len(st.session_state.messages) > 2:
        with st.container(key="finish"):
            if st.button(ui["finish"], key="finish_btn"):
                handle_finish_conversation()
                st.rerun()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    init_session_state()
    load_params_once()

    # A missing or tampered link must never open a conversation.
    if not st.session_state.link_valid:
        styles.render_invalid_link()
        return

    render_sidebar()
    # The reference design opens straight into the conversation — the safe
    # disclaimer is carried by the welcome card itself, per the project scope.
    render_chat()


if __name__ == "__main__":
    main()
