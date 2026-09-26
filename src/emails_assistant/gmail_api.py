"""Gmail API helpers: smoke, search, show, recent fetch."""

from __future__ import annotations

import base64
import logging
import re
from dataclasses import dataclass
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MessageSummary:
    id: str
    subject: str
    sender: str
    date: str
    snippet: str


@dataclass(frozen=True)
class MessageDetail:
    id: str
    thread_id: str
    subject: str
    sender: str
    to: str
    date: str
    snippet: str
    body: str


def build_gmail_service(creds: Credentials) -> Any:
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _headers_map(msg: dict[str, Any]) -> dict[str, str]:
    return {
        h["name"].lower(): h["value"]
        for h in (msg.get("payload") or {}).get("headers") or []
    }


def _b64url_decode(data: str) -> str:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad).decode("utf-8", errors="replace")


def _strip_html(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<br\s*/?>", "\n", text)
    text = re.sub(r"(?s)</p>", "\n\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _walk_body_parts(payload: dict[str, Any] | None) -> tuple[str, str]:
    """Return (text/plain, text/html) found under payload (first wins per type)."""
    plain = ""
    html = ""
    if not payload:
        return plain, html

    mime = payload.get("mimeType") or ""
    data = (payload.get("body") or {}).get("data")
    if data:
        decoded = _b64url_decode(data)
        if mime == "text/plain" and not plain:
            plain = decoded
        elif mime == "text/html" and not html:
            html = decoded

    for part in payload.get("parts") or []:
        p, h = _walk_body_parts(part)
        if p and not plain:
            plain = p
        if h and not html:
            html = h
        if plain and html:
            break
    return plain, html


def extract_body_text(msg: dict[str, Any]) -> str:
    plain, html = _walk_body_parts(msg.get("payload"))
    if plain.strip():
        return plain.strip()
    if html.strip():
        return _strip_html(html)
    return (msg.get("snippet") or "").strip()


def smoke_list_one(creds: Credentials) -> dict[str, str]:
    """Fetch one message metadata; returns id + subject/from when present."""
    service = build_gmail_service(creds)
    listing = (
        service.users()
        .messages()
        .list(userId="me", maxResults=1)
        .execute()
    )
    messages = listing.get("messages") or []
    if not messages:
        return {"id": "", "subject": "(mailbox empty)", "from": ""}

    detail = get_message(creds, messages[0]["id"], format="metadata")
    result = {
        "id": detail.id,
        "subject": detail.subject,
        "from": detail.sender,
    }
    logger.info("Smoke OK id=%s", detail.id)
    return result


def search_messages(
    creds: Credentials,
    *,
    query: str,
    max_results: int = 20,
) -> list[MessageSummary]:
    """List message summaries matching a Gmail search query."""
    service = build_gmail_service(creds)
    summaries: list[MessageSummary] = []
    page_token: str | None = None

    while True:
        remaining = max_results - len(summaries)
        if remaining <= 0:
            break
        listing = (
            service.users()
            .messages()
            .list(
                userId="me",
                q=query,
                maxResults=min(50, remaining),
                pageToken=page_token,
            )
            .execute()
        )
        for ref in listing.get("messages") or []:
            msg = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=ref["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"],
                )
                .execute()
            )
            headers = _headers_map(msg)
            summaries.append(
                MessageSummary(
                    id=ref["id"],
                    subject=headers.get("subject", "(no subject)"),
                    sender=headers.get("from", ""),
                    date=headers.get("date", ""),
                    snippet=(msg.get("snippet") or "").strip(),
                )
            )
            if len(summaries) >= max_results:
                break

        page_token = listing.get("nextPageToken")
        if not page_token or len(summaries) >= max_results:
            break

    logger.info("Search fetched %s messages (q=%s)", len(summaries), query)
    return summaries


def list_recent_messages(
    creds: Credentials,
    *,
    hours: int,
    max_results: int = 100,
) -> list[MessageSummary]:
    """List message summaries newer than ``hours`` (Gmail ``newer_than``)."""
    return search_messages(
        creds,
        query=f"newer_than:{hours}h",
        max_results=max_results,
    )


def get_message(
    creds: Credentials,
    message_id: str,
    *,
    format: str = "full",
) -> MessageDetail:
    """Fetch one message; ``format`` is Gmail get format (full/metadata)."""
    service = build_gmail_service(creds)
    kwargs: dict[str, Any] = {
        "userId": "me",
        "id": message_id,
        "format": format,
    }
    if format == "metadata":
        kwargs["metadataHeaders"] = ["From", "Subject", "Date", "To"]
    msg = service.users().messages().get(**kwargs).execute()
    headers = _headers_map(msg)
    body = extract_body_text(msg) if format == "full" else ""
    return MessageDetail(
        id=msg["id"],
        thread_id=msg.get("threadId", ""),
        subject=headers.get("subject", "(no subject)"),
        sender=headers.get("from", ""),
        to=headers.get("to", ""),
        date=headers.get("date", ""),
        snippet=(msg.get("snippet") or "").strip(),
        body=body,
    )
