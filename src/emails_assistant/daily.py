"""Day-file window and count. Callers read mail and write the file."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path


@dataclass(frozen=True)
class DailyMessage:
    arrived_at: datetime
    subject: str
    sender: str
    date: str = ""
    snippet: str = ""
    body: str = ""


SUMMARY_MISS = "Summary did not run."
_DAY_FILE = re.compile(r"\d{4}-\d{2}-\d{2}\.txt")


@dataclass(frozen=True)
class MailboxRead:
    alias: str
    messages: tuple[DailyMessage, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class DailyDecision:
    write: bool
    text: str
    count: int | None
    notice: str | None
    window_start: datetime
    path: Path
    failure: str | None = None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_daily_dir(*, environ: Mapping[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    override = env.get("EMAILS_ASSISTANT_DAILY_DIR")
    if override:
        return Path(override)
    return _repo_root() / "digests"


def decide_daily(
    *,
    daily_dir: Path,
    now: datetime,
    mailboxes: Sequence[MailboxRead],
    summary: str | None = None,
) -> DailyDecision:
    """Return whether to write today's file, its text, and a count-only notice.

    ``summary=None`` keeps the message list. A non-blank summary replaces that
    list and is not checked for length. A blank summary with new mail writes
    nothing. No new mail still writes the quiet file and ignores ``summary``.
    """
    day_path = daily_dir / f"{now.date().isoformat()}.txt"
    start = _window_start(daily_dir, day_path, now)
    if day_path.is_file() or any(box.error for box in mailboxes):
        return DailyDecision(
            write=False,
            text="",
            count=None,
            notice=None,
            window_start=start,
            path=day_path,
        )

    kept_sections: list[tuple[str, tuple[DailyMessage, ...]]] = []
    total = 0
    for box in mailboxes:
        kept = tuple(
            message for message in box.messages if _as_utc(message.arrived_at) > start
        )
        total += len(kept)
        kept_sections.append((box.alias, kept))
    if total == 0:
        return DailyDecision(
            write=True,
            text=_format_daily(day=day_path.stem, sections=kept_sections, count=0),
            count=0,
            notice="0",
            window_start=start,
            path=day_path,
        )
    if summary is None:
        return DailyDecision(
            write=True,
            text=_format_daily(day=day_path.stem, sections=kept_sections, count=total),
            count=total,
            notice=str(total),
            window_start=start,
            path=day_path,
        )
    text = summary.strip()
    if not text:
        return DailyDecision(
            write=False,
            text="",
            count=None,
            notice=None,
            window_start=start,
            path=day_path,
            failure=SUMMARY_MISS,
        )
    return DailyDecision(
        write=True,
        text=_format_summary(day=day_path.stem, summary=text),
        count=total,
        notice=str(total),
        window_start=start,
        path=day_path,
    )


def render_summary_input(
    mailboxes: Sequence[MailboxRead],
    *,
    window_start: datetime,
) -> str:
    """Text for the model: alias, subject, sender, date, and body or snippet."""
    blocks: list[str] = []
    for box in mailboxes:
        for message in box.messages:
            if _as_utc(message.arrived_at) <= window_start:
                continue
            lines = [
                box.alias,
                f"Subject: {message.subject}",
                f"From: {message.sender}",
            ]
            if message.date:
                lines.append(f"Date: {message.date}")
            body = message.body.strip() or message.snippet.strip()
            if body:
                lines.append(body)
            blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _window_start(directory: Path, today: Path, now: datetime) -> datetime:
    prior = _latest_prior(directory, today)
    if prior is None:
        return now - timedelta(hours=24)
    epoch = int(prior.stat().st_mtime)
    return datetime.fromtimestamp(epoch, tz=UTC)


def _latest_prior(directory: Path, today: Path) -> Path | None:
    if not directory.is_dir():
        return None
    today_resolved = today.resolve()
    candidates = [
        path
        for path in directory.glob("*.txt")
        if path.is_file()
        and path.resolve() != today_resolved
        and _DAY_FILE.fullmatch(path.name)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _format_daily(
    *,
    day: str,
    sections: Sequence[tuple[str, tuple[DailyMessage, ...]]],
    count: int,
) -> str:
    header = [f"# emails-assistant daily digest — {day}", ""]
    if count == 0:
        header.extend(["There were no new messages.", ""])
    body = [_format_section(alias, messages) for alias, messages in sections]
    return "\n".join(header + body).rstrip() + "\n"


def _format_summary(*, day: str, summary: str) -> str:
    return f"# emails-assistant daily digest — {day}\n\n{summary}\n"


def _format_section(alias: str, messages: tuple[DailyMessage, ...]) -> str:
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
