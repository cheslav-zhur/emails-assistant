"""Morning window, day file, and count. No Gmail, Keychain, or Docker."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from emails_assistant.morning import (
    MailboxRead,
    MorningMessage,
    decide_morning,
    resolve_morning_dir,
)

_NOW = datetime(2026, 9, 29, 10, 30, tzinfo=timezone.utc)


def _msg(moment: datetime, subject: str, sender: str = "a@example.com") -> MorningMessage:
    return MorningMessage(arrived_at=moment, subject=subject, sender=sender, date="Tue, 29 Sep 2026 10:00:00 +0000")


def _prior(directory: Path, name: str, moment: datetime, text: str = "prior\n") -> Path:
    path = directory / name
    path.write_text(text)
    epoch = int(moment.timestamp())
    os.utime(path, (epoch, epoch))
    return path


def _reads(*pairs: tuple[str, tuple[MorningMessage, ...]]) -> tuple[MailboxRead, ...]:
    return tuple(MailboxRead(alias=alias, messages=messages) for alias, messages in pairs)


def test_first_morning_window_starts_24_hours_before_clock(tmp_path: Path) -> None:
    decision = decide_morning(morning_dir=tmp_path, now=_NOW, mailboxes=_reads(("email1", ()), ("email2", ())))

    assert decision.window_start == _NOW - timedelta(hours=24)


def test_message_at_prior_mtime_is_outside_and_later_message_is_inside(tmp_path: Path) -> None:
    modified = datetime(2026, 9, 28, 8, 10, tzinfo=timezone.utc)
    _prior(tmp_path, "2026-09-28.txt", modified)
    at_boundary = _msg(modified, "at-boundary")
    inside = _msg(modified + timedelta(seconds=1), "after-boundary")

    decision = decide_morning(
        morning_dir=tmp_path,
        now=_NOW,
        mailboxes=_reads(("email1", (at_boundary, inside)), ("email2", ())),
    )

    assert decision.window_start == modified
    assert decision.write is True
    assert "after-boundary" in decision.text
    assert "at-boundary" not in decision.text


def test_window_starts_at_the_latest_prior_file(tmp_path: Path) -> None:
    older = datetime(2026, 9, 27, 8, 10, tzinfo=timezone.utc)
    newer = datetime(2026, 9, 28, 8, 10, tzinfo=timezone.utc)
    _prior(tmp_path, "2026-09-27.txt", older)
    _prior(tmp_path, "2026-09-28.txt", newer)

    decision = decide_morning(
        morning_dir=tmp_path,
        now=_NOW,
        mailboxes=_reads(("email1", ()), ("email2", ())),
    )

    assert decision.window_start == newer


def test_existing_today_file_is_left_and_sends_no_notice(tmp_path: Path) -> None:
    today = tmp_path / "2026-09-29.txt"
    today.write_text("already\n")
    subject = "should-not-notify"

    decision = decide_morning(
        morning_dir=tmp_path,
        now=_NOW,
        mailboxes=_reads(("email1", (_msg(_NOW, subject),)), ("email2", ())),
    )

    assert decision.write is False
    assert decision.count is None
    assert decision.notice is None
    assert today.read_text() == "already\n"
    assert subject not in (decision.notice or "")


def test_no_new_mail_still_plans_a_zero_file(tmp_path: Path) -> None:
    modified = datetime(2026, 9, 28, 8, 10, tzinfo=timezone.utc)
    _prior(tmp_path, "2026-09-28.txt", modified)
    stale = _msg(modified, "already-shown")

    decision = decide_morning(
        morning_dir=tmp_path,
        now=_NOW,
        mailboxes=_reads(("email1", (stale,)), ("email2", ())),
    )

    assert decision.write is True
    assert decision.count == 0
    assert decision.notice == "0"
    assert "There were no new messages." in decision.text
    assert "(none)" in decision.text
    assert "already-shown" not in decision.text
    assert "already-shown" not in (decision.notice or "")


def test_mailbox_error_writes_nothing_and_keeps_prior_window(tmp_path: Path) -> None:
    modified = datetime(2026, 9, 28, 8, 10, tzinfo=timezone.utc)
    _prior(tmp_path, "2026-09-28.txt", modified)
    subject = "unread-subject"

    decision = decide_morning(
        morning_dir=tmp_path,
        now=_NOW,
        mailboxes=(
            MailboxRead(alias="email1", messages=(_msg(_NOW, subject),)),
            MailboxRead(alias="email2", error="mailbox unreadable"),
        ),
    )

    assert decision.write is False
    assert decision.count is None
    assert decision.notice is None
    assert decision.text == ""
    assert decision.window_start == modified
    assert subject not in decision.text
    assert not (tmp_path / "2026-09-29.txt").exists()


def test_count_is_the_sum_across_both_aliases(tmp_path: Path) -> None:
    modified = datetime(2026, 9, 28, 8, 10, tzinfo=timezone.utc)
    _prior(tmp_path, "2026-09-28.txt", modified)
    first = tuple(_msg(_NOW, f"one-{index}", "one@example.com") for index in range(2))
    second = tuple(_msg(_NOW, f"two-{index}", "two@example.com") for index in range(3))

    decision = decide_morning(
        morning_dir=tmp_path,
        now=_NOW,
        mailboxes=_reads(("email1", first), ("email2", second)),
    )

    assert decision.write is True
    assert decision.count == 5
    assert decision.notice == "5"
    assert "email1" in decision.text
    assert "email2" in decision.text
    assert "one-0" in decision.text
    assert "two-2" in decision.text
    for message in first + second:
        assert message.subject not in (decision.notice or "")
        assert message.sender not in (decision.notice or "")


def test_morning_dir_defaults_to_library_and_honors_override(tmp_path: Path) -> None:
    home = tmp_path / "home"
    custom = tmp_path / "custom"

    assert resolve_morning_dir(environ={}, home=home) == (
        home / "Library" / "Application Support" / "emails-assistant" / "digests"
    )
    assert resolve_morning_dir(environ={"EMAILS_ASSISTANT_MORNING_DIR": str(custom)}, home=home) == custom
