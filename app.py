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
from email_service import send_admin_alert
from gemini_service import (
    GeminiUnavailableError,
    generate_response,
    initialize_model,
)
from google_sheets import save_chat_summary, save_risk_flag, save_support_lead
from transcript_service import save_transcript
from prompts import (
    CRISIS_MESSAGE,
    FALLBACK_ERROR_MESSAGE,
    WELCOME_MESSAGE,
    get_system_prompt,
)
from risk_detection import RISK_CRISIS, detect_risk, matched_keywords
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

# Quick-reply chips (from the reference design).
SUGGESTIONS = ["Workload", "Sleep", "Team pressure", "Something personal"]

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

    emp = st.session_state.employee_id
    sector = st.session_state.sector
    lang = st.session_state.lang

    # Archive the conversation before the summary row, so the row can carry the
    # link. A Drive failure returns "" rather than raising — losing the archive
    # must not also lose the summary.
    transcript_url = save_transcript(
        emp, datetime.now().strftime("%Y-%m-%d"), st.session_state.messages
    )

    if not save_chat_summary(emp, sector, lang, summary, transcript_url):
        st.warning(
            "We couldn't save your summary to our records right now, but your "
            "conversation is still complete."
        )
    if str(summary.get("human_support_requested", "")).lower() == "yes":
        save_support_lead(
            emp, sector, lang, "yes", summary.get("summary", ""),
            risk_category=summary.get("risk_category", ""),
        )


def trigger_crisis(trigger_message: str) -> None:
    """Escalate to crisis state: flag, alert admin, and stop normal flow."""
    st.session_state.risk_category = RISK_CRISIS
    st.session_state.crisis_triggered = True

    keywords = matched_keywords(trigger_message)
    emp = st.session_state.employee_id
    sector = st.session_state.sector
    lang = st.session_state.lang

    # Alert first so the sheet can record whether the admin was actually reached.
    alerted = send_admin_alert(emp, sector, RISK_CRISIS, keywords, trigger_message)
    save_risk_flag(
        emp, sector, lang, RISK_CRISIS, keywords, trigger_message,
        detection_method="keyword", admin_email_sent=alerted,
    )


def render_summary() -> None:
    """Display the structured summary after the conversation ends."""
    summary = st.session_state.summary or {}
    st.success("Thank you for sharing. Here's a gentle summary of our conversation.")
    st.markdown("#### Wellbeing Summary")

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
    styles.render_summary_grid(
        [(label, summary.get(key, "unclear")) for key, label in field_labels.items()]
    )
    styles.render_summary_card(
        summary.get("summary", ""), summary.get("recommendation", "")
    )


# ---------------------------------------------------------------------------
# Turn handling
# ---------------------------------------------------------------------------
def handle_turn(user_message: str) -> None:
    """Process one user message: crisis-check, generate reply, persist."""
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
        elif i == 0 and message["content"] == WELCOME_MESSAGE:
            styles.render_welcome(ts)
        else:
            styles.render_bot_message(message["content"], ts)


def render_chat() -> None:
    """Main chat interface (header, message stream, chips, composer)."""
    st.session_state.chat_started = True
    render_header()

    if not ensure_model():
        return

    if not st.session_state.messages:
        _add_message("assistant", WELCOME_MESSAGE)

    render_messages()

    if st.session_state.crisis_triggered:
        return
    if st.session_state.conversation_finished:
        render_summary()
        return

    # Quick-reply chips (functional — clicking sends that prompt).
    with st.container(key="chips"):
        chip_cols = st.columns(len(SUGGESTIONS), gap="small")
        for col, text in zip(chip_cols, SUGGESTIONS):
            if col.button(text, key=f"sug_{text}"):
                handle_turn(text)

    # Composer.
    user_message = st.chat_input("Share how you're feeling…")
    if user_message:
        handle_turn(user_message)

    # Finish action — rendered as a chip alongside the quick replies.
    if len(st.session_state.messages) > 2:
        with st.container(key="finish"):
            if st.button("Finish conversation", key="finish_btn"):
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
