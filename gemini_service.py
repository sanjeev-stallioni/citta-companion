"""Thin wrapper around Google's Generative AI (Gemini) SDK.

Keeps all model configuration and error handling in one place so the Streamlit
layer only deals with plain strings.
"""

from __future__ import annotations

import logging

import google.generativeai as genai

import config

logger = logging.getLogger(__name__)


class GeminiUnavailableError(RuntimeError):
    """Raised when the Gemini service cannot be reached or is misconfigured."""


# Generation defaults keep answers short and focused, matching the assistant's
# "one short question at a time" behaviour.
_GENERATION_CONFIG = {
    "temperature": 0.7,
    "top_p": 0.95,
    "top_k": 40,
    # Newer "flash" models spend part of the budget on internal reasoning
    # before emitting text, so keep enough headroom to avoid mid-sentence
    # truncation while the system prompt still keeps replies short.
    "max_output_tokens": 1024,
}

# Safety settings — we keep the SDK defaults so the model can still discuss
# difficult wellbeing topics compassionately. Crisis handling is enforced
# separately and deterministically by :mod:`risk_detection`, so we intentionally
# do not override per-category thresholds here (their accepted keys vary between
# SDK versions).
_SAFETY_SETTINGS = None


def initialize_model(system_instruction: str) -> "genai.GenerativeModel":
    """Configure and return a Gemini model instance.

    Args:
        system_instruction: The system prompt controlling assistant behaviour.

    Raises:
        GeminiUnavailableError: If the API key is missing or initialisation fails.
    """
    if not config.GEMINI_API_KEY:
        raise GeminiUnavailableError(
            "GEMINI_API_KEY is not set. Add it to your .env file."
        )

    try:
        genai.configure(api_key=config.GEMINI_API_KEY)
        model = genai.GenerativeModel(
            model_name=config.GEMINI_MODEL_NAME,
            system_instruction=system_instruction,
            generation_config=_GENERATION_CONFIG,
            safety_settings=_SAFETY_SETTINGS,
        )
        return model
    except Exception as exc:  # noqa: BLE001 - surface as a domain error
        logger.exception("Failed to initialise Gemini model")
        raise GeminiUnavailableError(str(exc)) from exc


def _to_gemini_history(history: list[dict]) -> list[dict]:
    """Convert internal chat history to the Gemini ``contents`` format.

    Internal messages use ``{"role": "user"|"assistant", "content": str}``.
    Gemini expects ``{"role": "user"|"model", "parts": [str]}``.
    """
    role_map = {"user": "user", "assistant": "model"}
    converted: list[dict] = []
    for message in history:
        role = role_map.get(message.get("role", "user"), "user")
        converted.append({"role": role, "parts": [message.get("content", "")]})
    return converted


def generate_response(
    model: "genai.GenerativeModel",
    history: list[dict],
    user_message: str,
) -> str:
    """Generate the assistant's next reply.

    Args:
        model: A model returned by :func:`initialize_model`.
        history: Prior conversation (excluding ``user_message``).
        user_message: The latest user message.

    Returns:
        The assistant's reply text.

    Raises:
        GeminiUnavailableError: On any transport/API failure.
    """
    try:
        chat = model.start_chat(history=_to_gemini_history(history))
        response = chat.send_message(user_message)
        text = (getattr(response, "text", "") or "").strip()
        if not text:
            raise GeminiUnavailableError("Empty response from Gemini.")
        return text
    except GeminiUnavailableError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Gemini generate_response failed")
        raise GeminiUnavailableError(str(exc)) from exc


def generate_json(model: "genai.GenerativeModel", history: list[dict], instruction: str) -> str:
    """Send a one-off instruction over ``history`` and return raw JSON text.

    Used by the summary generator to request a structured JSON payload.
    A dedicated analyst model is used instead of the conversational ``model``:
    the empathetic chat system prompt ("one short question at a time") makes
    the model keep chatting instead of obeying the JSON instruction, and JSON
    output mode guarantees a parseable payload.
    """
    if not config.GEMINI_API_KEY:
        raise GeminiUnavailableError("GEMINI_API_KEY is not set.")
    try:
        genai.configure(api_key=config.GEMINI_API_KEY)
        summarizer = genai.GenerativeModel(
            model_name=config.GEMINI_MODEL_NAME,
            system_instruction=(
                "You are an analyst producing structured wellbeing summaries "
                "of conversations. Follow the user's formatting instructions "
                "exactly and return only valid JSON."
            ),
            generation_config={
                "temperature": 0.2,
                # The summary is much longer than a chat turn, and "flash"
                # models spend part of the budget on internal reasoning —
                # give enough headroom that the JSON is never truncated.
                "max_output_tokens": 8192,
                "response_mime_type": "application/json",
            },
        )
        transcript = "\n".join(
            f"{'Employee' if m.get('role') == 'user' else 'Assistant'}: {m.get('content', '')}"
            for m in history
        )
        response = summarizer.generate_content(
            f"Conversation transcript:\n\n{transcript}\n\n{instruction}"
        )
        return (getattr(response, "text", "") or "").strip()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Gemini generate_json failed")
        raise GeminiUnavailableError(str(exc)) from exc
