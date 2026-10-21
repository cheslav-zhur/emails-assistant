"""Gemini summary of one morning window. The caller writes the day file."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MODEL = "gemini-3.8-flash"
LOCATION = "global"
_HTTP_TIMEOUT_MS = 300_000
_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
_INSTRUCTION = (
    "Write the morning file in Russian. "
    "Treat both mailboxes as one pool. "
    "Do not count the messages and do not list them one by one. "
    "Do not give advice and do not invent dates. "
    "Write a date as day and month only, with no year, like 27 окт. "
    "Start with the heading Важное when something needs attention. "
    "Under it, write two to four paragraphs. "
    "Each paragraph is a short topic name, then exactly two sentences. "
    "The second sentence adds one new fact and does not restate the first. "
    "Do not mention a precaution or what the owner should do. "
    "After that, the heading Остальное and only these lines, in this order, "
    "skipping a line when that group is empty. "
    'Each line starts with "- ". '
    "Career: one sentence on job alerts, applications, and recruiter mail. "
    "Name no cities, countries, or roles. "
    "Finance: one sentence naming the date, who charged, and the amount. "
    "Leave marketing out of Finance. "
    "Events: up to three soonest meetups, webinars, or conferences, "
    "each with its date from the mail. "
    "A show, a session, an evening, a sale, or a ticket offer "
    "is Рассылки, not Events. "
    "Travel: one sentence only for a real trip, not fare ads. "
    "Рассылки: one short last sentence for newsletters and promotions. "
    "Name no brands, topics, or products. "
    "Omit Важное when nothing is important. "
    "Omit Остальное when every group is empty."
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
    return Path(__file__).resolve().parents[3]


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
    active: Any
    if client is not None:
        active = client
    elif key_path is None:
        return ""
    else:
        try:
            active = _enterprise_client(key_path)
        except Exception:  # noqa: BLE001  a bad key becomes an empty summary
            logger.error("Gemini credentials were rejected")
            return ""
    try:
        response = active.models.generate_content(
            model=MODEL,
            contents=_prompt(mail_text),
        )
    except Exception:  # noqa: BLE001  a Gemini miss becomes an empty summary
        logger.error("Gemini did not return a summary")
        return ""
    return _visible_summary(response)
