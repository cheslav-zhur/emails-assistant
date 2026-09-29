"""Morning window, day file, and count. Callers read mail and write the file."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclass(frozen=True)
class MorningMessage:
    arrived_at: datetime
    subject: str
    sender: str
    date: str = ""
    snippet: str = ""


@dataclass(frozen=True)
class MailboxRead:
    alias: str
    messages: tuple[MorningMessage, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class MorningDecision:
    write: bool
    text: str
    count: int | None
    notice: str | None
    window_start: datetime
    path: Path


def resolve_morning_dir(
    *,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    env = os.environ if environ is None else environ
    override = env.get("EMAILS_ASSISTANT_MORNING_DIR")
    if override:
        return Path(override)
    base = Path.home() if home is None else home
    return base / "Library" / "Application Support" / "emails-assistant" / "digests"


def decide_morning(
    *,
    morning_dir: Path,
    now: datetime,
    mailboxes: Sequence[MailboxRead],
) -> MorningDecision:
    """Return whether to write today's file, its text, and a count-only notice."""
    day_path = morning_dir / f"{now.date().isoformat()}.txt"
    start = _window_start(morning_dir, day_path, now)
    if day_path.is_file() or any(box.error for box in mailboxes):
        return MorningDecision(
            write=False,
            text="",
            count=None,
            notice=None,
            window_start=start,
            path=day_path,
        )

    kept_sections: list[tuple[str, tuple[MorningMessage, ...]]] = []
    total = 0
    for box in mailboxes:
        kept = tuple(message for message in box.messages if _as_utc(message.arrived_at) > start)
        total += len(kept)
        kept_sections.append((box.alias, kept))
    return MorningDecision(
        write=True,
        text=_format_morning(day=day_path.stem, sections=kept_sections, count=total),
        count=total,
        notice=str(total),
        window_start=start,
        path=day_path,
    )


def _window_start(directory: Path, today: Path, now: datetime) -> datetime:
    prior = _latest_prior(directory, today)
    if prior is None:
        return now - timedelta(hours=24)
    epoch = int(prior.stat().st_mtime)
    return datetime.fromtimestamp(epoch, tz=timezone.utc)


def _latest_prior(directory: Path, today: Path) -> Path | None:
    if not directory.is_dir():
        return None
    today_resolved = today.resolve()
    candidates = [
        path
        for path in directory.glob("*.txt")
        if path.is_file() and path.resolve() != today_resolved
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _format_morning(
    *,
    day: str,
    sections: Sequence[tuple[str, tuple[MorningMessage, ...]]],
    count: int,
) -> str:
    header = [f"# emails-assistant morning digest — {day}", ""]
    if count == 0:
        header.extend(["There were no new messages.", ""])
    body = [_format_section(alias, messages) for alias, messages in sections]
    return "\n".join(header + body).rstrip() + "\n"


def _format_section(alias: str, messages: tuple[MorningMessage, ...]) -> str:
    lines = [f"## {alias} — {len(messages)} message(s)", ""]
    if not messages:
        lines.append("(none)")
        lines.append("")
        return "\n".join(lines)

    for index, message in enumerate(messages, start=1):
        lines.append(f"{index}. {message.subject}")
        lines.append(f"   From: {message.sender}")
        if message.date:
            lines.append(f"   Date: {message.date}")
        if message.snippet:
            lines.append(f"   {message.snippet}")
        lines.append("")
    return "\n".join(lines)
