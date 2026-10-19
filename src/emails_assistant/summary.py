"""Gemini summary of one morning window. The caller writes the day file."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

MODEL = "gemini-3.8-flash"
LOCATION = "global"
_INSTRUCTION = (
    "Summarize what is important across both mailboxes as one pool, "
    "in about 4 to 10 sentences. "
    "Leave out a mailbox when nothing in it is important. "
    "Do not list the messages."
)


def _prompt(mail_text: str) -> str:
    return f"{_INSTRUCTION}\n\n{mail_text}\n\n{_INSTRUCTION}"


def _finish_reason(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw).strip().upper()


def _visible_summary(response: object) -> str:
    """Non-thought text when the model finished with STOP, otherwise empty."""
    candidates = getattr(response, "candidates", None) or ()
    if not candidates:
        return ""
    candidate = candidates[0]
    if _finish_reason(getattr(candidate, "finish_reason", None)) != "STOP":
        return ""
    content = getattr(candidate, "content", None)
    parts = getattr(content, "parts", None) or ()
    chunks: list[str] = []
    for part in parts:
        if getattr(part, "thought", False):
            continue
        text = getattr(part, "text", None)
        if isinstance(text, str) and text:
            chunks.append(text)
    return "".join(chunks).strip()


def _enterprise_client(bearer: str, project_id: str) -> Any:
    from google import genai
    from google.oauth2.credentials import Credentials

    return genai.Client(
        enterprise=True,
        project=project_id,
        location=LOCATION,
        credentials=Credentials(token=bearer),
    )


def summarize(
    mail_text: str,
    *,
    bearer: str,
    project_id: str,
    client: Any | None = None,
) -> str:
    """Return the finished summary, or an empty string when Gemini does not."""
    if client is None:
        client = _enterprise_client(bearer, project_id)
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=_prompt(mail_text),
        )
    except Exception:
        logger.error("Gemini did not return a summary")
        return ""
    return _visible_summary(response)
