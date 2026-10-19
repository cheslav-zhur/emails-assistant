"""Gemini summary of one morning window. The caller writes the day file."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MODEL = "gemini-3.8-flash"
LOCATION = "global"
_HTTP_TIMEOUT_MS = 180_000
_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
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


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def gemini_key_path(*, root: Path | None = None) -> Path | None:
    """The one service-account file in keys/, or none when it is missing."""
    directory = (_repo_root() if root is None else root) / "keys"
    if not directory.is_dir():
        return None
    found = sorted(path for path in directory.glob("*.json") if path.is_file())
    if len(found) != 1:
        return None
    return found[0]


def _enterprise_client(key_path: Path) -> Any:
    from google import genai
    from google.oauth2 import service_account

    payload = json.loads(key_path.read_text(encoding="utf-8"))
    project_id = payload.get("project_id")
    if not isinstance(project_id, str) or not project_id.strip():
        raise ValueError("project_id")
    credentials = service_account.Credentials.from_service_account_info(
        payload,
        scopes=[_SCOPE],
    )
    return genai.Client(
        enterprise=True,
        project=project_id.strip(),
        location=LOCATION,
        credentials=credentials,
        http_options={"timeout": _HTTP_TIMEOUT_MS},
    )


def summarize(
    mail_text: str,
    *,
    key_path: Path | None = None,
    client: Any | None = None,
) -> str:
    """Return the finished summary, or an empty string when Gemini does not."""
    if client is None:
        if key_path is None:
            return ""
        try:
            client = _enterprise_client(key_path)
        except Exception:
            logger.error("Gemini credentials were rejected")
            return ""
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=_prompt(mail_text),
        )
    except Exception:
        logger.error("Gemini did not return a summary")
        return ""
    return _visible_summary(response)
