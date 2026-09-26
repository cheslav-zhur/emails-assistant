"""Plain-text output formatting for digest / search / show."""

from __future__ import annotations

from emails_assistant.gmail_api import MessageDetail, MessageSummary


def format_account_section(
    alias: str,
    *,
    hours: int,
    messages: list[MessageSummary],
) -> str:
    lines = [
        f"## {alias} (last {hours}h) — {len(messages)} message(s)",
        "",
    ]
    if not messages:
        lines.append("(none)")
        lines.append("")
        return "\n".join(lines)

    for i, msg in enumerate(messages, start=1):
        lines.append(f"{i}. {msg.subject}")
        lines.append(f"   From: {msg.sender}")
        if msg.date:
            lines.append(f"   Date: {msg.date}")
        if msg.snippet:
            lines.append(f"   {msg.snippet}")
        lines.append("")
    return "\n".join(lines)


def format_digest(
    *,
    hours: int,
    sections: list[tuple[str, list[MessageSummary]]],
) -> str:
    header = [
        f"# emails-assistant digest — last {hours}h",
        "",
    ]
    body = [
        format_account_section(alias, hours=hours, messages=msgs)
        for alias, msgs in sections
    ]
    return "\n".join(header + body).rstrip() + "\n"


def format_search(
    alias: str,
    *,
    query: str,
    messages: list[MessageSummary],
) -> str:
    lines = [
        f"# search {alias} q={query!r} — {len(messages)} message(s)",
        "",
    ]
    if not messages:
        lines.append("(none)")
        lines.append("")
        return "\n".join(lines)

    for msg in messages:
        lines.append(f"{msg.id}  {msg.date}")
        lines.append(f"  From: {msg.sender}")
        lines.append(f"  Subject: {msg.subject}")
        if msg.snippet:
            lines.append(f"  {msg.snippet}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def format_show(alias: str, detail: MessageDetail) -> str:
    body = detail.body or detail.snippet or "(no body)"
    lines = [
        f"# show {alias} id={detail.id}",
        f"Thread: {detail.thread_id}" if detail.thread_id else "",
        f"From: {detail.sender}",
        f"To: {detail.to}" if detail.to else "",
        f"Date: {detail.date}" if detail.date else "",
        f"Subject: {detail.subject}",
        "",
        body,
        "",
    ]
    return "\n".join(line for line in lines if line).rstrip() + "\n"
