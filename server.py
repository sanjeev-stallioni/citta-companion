"""Citta Companion — Flask server rendering the reference chat UI.

Serves the pixel-perfect frontend in ``templates/index.html`` (a faithful port
of the approved "Citta Companion Chat" design) and exposes a small JSON API
that reuses the existing service modules:

    python server.py            # then open http://localhost:8000
    http://localhost:8000/?id=CITTA-EMP001&sector=IT&lang=en

The Streamlit entry point (``app.py``) is unchanged and still works, but this
server is the primary UI because Streamlit cannot reproduce the design 1:1.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from flask import Flask, jsonify, render_template, request

import config
import link_tokens
from email_service import send_admin_alert, send_support_request_alert
from gemini_service import (
    GeminiUnavailableError,
    generate_response,
    initialize_model,
)
from google_sheets import save_chat_summary, save_risk_flag, save_support_lead
from prompts import (
    CRISIS_MESSAGE,
    FALLBACK_ERROR_MESSAGE,
    get_system_prompt,
    get_ui_copy,
    get_welcome_copy,
    get_welcome_message,
)
from risk_detection import RISK_CRISIS, detect_risk, matched_keywords
from summary_generator import generate_summary
from transcript_service import save_transcript
from utils import language_label, risk_label

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# In-memory session store: {session_id: {...}}. Suitable for the local,
# single-process deployment this app targets.
SESSIONS: dict[str, dict] = {}


def _first_param(key: str, default: str) -> str:
    value = request.args.get(key, default)
    return (value or default).strip()


def _get_session(session_id: str) -> dict | None:
    return SESSIONS.get(session_id)


def _ensure_model(session: dict):
    """Lazily initialise the Gemini model for this session."""
    if session.get("model") is None:
        system_prompt = get_system_prompt(session["sector"], session["lang"])
        session["model"] = initialize_model(system_prompt)
    return session["model"]


@app.get("/")
def index():
    # With a signing secret configured, only signed links may open a chat.
    if config.LINK_SECRET:
        link = link_tokens.verify(request.args.get("t", ""))
        if link is None:
            return render_template("invalid_link.html"), 403
        employee_id, sector, lang = link["employee_id"], link["sector"], link["lang"]
    else:
        employee_id = _first_param("id", config.DEFAULT_EMPLOYEE_ID)
        sector = _first_param("sector", config.DEFAULT_SECTOR)
        lang = _first_param("lang", config.DEFAULT_LANG)

    session_id = uuid.uuid4().hex
    # The welcome copy is kept in the model's history so the conversation
    # context matches what the employee actually saw, in their language.
    session = {
        "employee_id": employee_id,
        "sector": sector,
        "lang": lang,
        "messages": [{"role": "assistant", "content": get_welcome_message(lang)}],
        "model": None,
        "risk_category": "none",
        "crisis": False,
        "finished": False,
    }
    SESSIONS[session_id] = session
    return render_template(
        "index.html",
        session_id=session_id,
        employee_id=session["employee_id"],
        sector=session["sector"],
        language=language_label(session["lang"]),
        welcome=get_welcome_copy(lang),
        ui=get_ui_copy(lang),
    )


@app.post("/api/chat")
def api_chat():
    data = request.get_json(silent=True) or {}
    session = _get_session(str(data.get("session_id", "")))
    message = str(data.get("message", "")).strip()
    if session is None or not message:
        return jsonify({"error": "invalid session or empty message"}), 400
    if session["crisis"] or session["finished"]:
        return jsonify({"error": "conversation is closed"}), 409

    session["messages"].append({"role": "user", "content": message})

    # Deterministic crisis check runs before the model.
    if detect_risk(message) == RISK_CRISIS:
        session["risk_category"] = RISK_CRISIS
        session["crisis"] = True
        keywords = matched_keywords(message)
        # Alert first so the sheet can record whether the admin was reached.
        alerted = send_admin_alert(
            session["employee_id"], session["sector"], RISK_CRISIS,
            keywords, message,
        )
        save_risk_flag(
            session["employee_id"], session["sector"], session["lang"],
            RISK_CRISIS, keywords, message,
            detection_method="keyword", admin_email_sent=alerted,
        )
        session["messages"].append({"role": "assistant", "content": CRISIS_MESSAGE})
        return jsonify({"reply": CRISIS_MESSAGE, "crisis": True})

    try:
        model = _ensure_model(session)
        reply = generate_response(model, session["messages"][:-1], message)
    except GeminiUnavailableError as exc:
        logger.warning("Gemini unavailable: %s", exc)
        reply = FALLBACK_ERROR_MESSAGE

    session["messages"].append({"role": "assistant", "content": reply})
    return jsonify({"reply": reply, "crisis": False})


@app.post("/api/finish")
def api_finish():
    data = request.get_json(silent=True) or {}
    session = _get_session(str(data.get("session_id", "")))
    if session is None:
        return jsonify({"error": "invalid session"}), 400

    try:
        model = _ensure_model(session)
    except GeminiUnavailableError:
        model = None
    summary = generate_summary(model, session["messages"], session["risk_category"])
    session["finished"] = True

    now = datetime.now()
    transcript_url = save_transcript(
        session["employee_id"], now.strftime("%Y-%m-%d"), session["messages"],
        language=language_label(session["lang"]),
        lang_code=session["lang"],
        risk=risk_label(session["risk_category"]),
        status="Crisis — paused" if session["crisis"] else "Finished",
        display_date=now.strftime("%d %B %Y"),
    )
    saved = save_chat_summary(
        session["employee_id"], session["sector"], session["lang"], summary,
        transcript_url,
    )
    if str(summary.get("human_support_requested", "")).lower() == "yes":
        save_support_lead(
            session["employee_id"], session["sector"], session["lang"],
            "yes", summary.get("summary", ""),
            risk_category=summary.get("risk_category", ""),
        )
    return jsonify({"summary": summary, "saved": saved})


@app.post("/api/callback")
def api_callback():
    data = request.get_json(silent=True) or {}
    session = _get_session(str(data.get("session_id", "")))
    if session is None:
        return jsonify({"error": "invalid session"}), 400
    notes = "Employee requested a callback from the chat sidebar."
    saved = save_support_lead(
        session["employee_id"], session["sector"], session["lang"], "yes", notes
    )
    send_support_request_alert(session["employee_id"], session["sector"], notes)
    return jsonify({"saved": saved})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
