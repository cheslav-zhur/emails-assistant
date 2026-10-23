"""Daily window, day file, and count. No Gmail, Keychain, or Docker."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from emails_assistant.daily import (
    SUMMARY_MISS,
    DailyMessage,
    MailboxRead,
    decide_daily,
    record_summary_miss,
    render_summary_input,
    resolve_daily_dir,
)

_NOW = datetime(2026, 9, 29, 10, 30, tzinfo=UTC)


def _msg(moment: datetime, subject: str, sender: str = "a@example.com") -> DailyMessage:
    return DailyMessage(
        arrived_at=moment,
        subject=subject,
        sender=sender,
        date="Tue, 29 Sep 2026 10:00:00 +0000",
    )


def _prior(directory: Path, name: str, moment: datetime, text: str = "prior\n") -> Path:
    path = directory / name
    path.write_text(text)
    epoch = int(moment.timestamp())
    os.utime(path, (epoch, epoch))
    return path


def _reads(*pairs: tuple[str, tuple[DailyMessage, ...]]) -> tuple[MailboxRead, ...]:
    return tuple(
        MailboxRead(alias=alias, messages=messages) for alias, messages in pairs
    )


def test_first_daily_window_starts_24_hours_before_clock(tmp_path: Path) -> None:
    decision = decide_daily(
        daily_dir=tmp_path, now=_NOW, mailboxes=_reads(("email1", ()), ("email2", ()))
    )

    assert decision.window_start == _NOW - timedelta(hours=24)


def test_message_at_prior_mtime_is_outside_and_later_message_is_inside(
    tmp_path: Path,
) -> None:
    modified = datetime(2026, 9, 28, 8, 10, tzinfo=UTC)
    _prior(tmp_path, "2026-09-28.txt", modified)
    at_boundary = _msg(modified, "at-boundary")
    inside = _msg(modified + timedelta(seconds=1), "after-boundary")

    decision = decide_daily(
        daily_dir=tmp_path,
        now=_NOW,
        mailboxes=_reads(("email1", (at_boundary, inside)), ("email2", ())),
    )

    assert decision.window_start == modified
    assert decision.write is True
    assert "after-boundary" in decision.text
    assert "at-boundary" not in decision.text


def test_window_starts_at_the_latest_prior_file(tmp_path: Path) -> None:
    older = datetime(2026, 9, 27, 8, 10, tzinfo=UTC)
    newer = datetime(2026, 9, 28, 8, 10, tzinfo=UTC)
    _prior(tmp_path, "2026-09-27.txt", older)
    _prior(tmp_path, "2026-09-28.txt", newer)

    decision = decide_daily(
        daily_dir=tmp_path,
        now=_NOW,
        mailboxes=_reads(("email1", ()), ("email2", ())),
    )

    assert decision.window_start == newer


def test_a_newer_stray_txt_does_not_move_the_window(tmp_path: Path) -> None:
    prior = datetime(2026, 9, 28, 8, 10, tzinfo=UTC)
    stray = datetime(2026, 9, 28, 20, 0, tzinfo=UTC)
    _prior(tmp_path, "2026-09-28.txt", prior)
    _prior(tmp_path, "notes.txt", stray)

    decision = decide_daily(
        daily_dir=tmp_path,
        now=_NOW,
        mailboxes=_reads(("email1", ()), ("email2", ())),
    )

    assert decision.window_start == prior


def test_only_a_stray_txt_uses_the_24_hour_window(tmp_path: Path) -> None:
    _prior(tmp_path, "notes.txt", datetime(2026, 9, 28, 20, 0, tzinfo=UTC))

    decision = decide_daily(
        daily_dir=tmp_path,
        now=_NOW,
        mailboxes=_reads(("email1", ()), ("email2", ())),
    )

    assert decision.window_start == _NOW - timedelta(hours=24)


def test_existing_today_file_is_left_and_sends_no_notice(tmp_path: Path) -> None:
    today = tmp_path / "2026-09-29.txt"
    today.write_text("already\n")
    subject = "should-not-notify"

    decision = decide_daily(
        daily_dir=tmp_path,
        now=_NOW,
        mailboxes=_reads(("email1", (_msg(_NOW, subject),)), ("email2", ())),
    )

    assert decision.write is False
    assert decision.count is None
    assert decision.notice is None
    assert today.read_text() == "already\n"
    assert subject not in (decision.notice or "")


def test_no_new_mail_still_plans_a_zero_file(tmp_path: Path) -> None:
    modified = datetime(2026, 9, 28, 8, 10, tzinfo=UTC)
    _prior(tmp_path, "2026-09-28.txt", modified)
    stale = _msg(modified, "already-shown")

    decision = decide_daily(
        daily_dir=tmp_path,
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
    modified = datetime(2026, 9, 28, 8, 10, tzinfo=UTC)
    _prior(tmp_path, "2026-09-28.txt", modified)
    subject = "unread-subject"

    decision = decide_daily(
        daily_dir=tmp_path,
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
    modified = datetime(2026, 9, 28, 8, 10, tzinfo=UTC)
    _prior(tmp_path, "2026-09-28.txt", modified)
    first = tuple(_msg(_NOW, f"one-{index}", "one@example.com") for index in range(2))
    second = tuple(_msg(_NOW, f"two-{index}", "two@example.com") for index in range(3))

    decision = decide_daily(
        daily_dir=tmp_path,
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


def test_summary_replaces_the_list_and_keeps_the_count(tmp_path: Path) -> None:
    modified = datetime(2026, 9, 28, 8, 10, tzinfo=UTC)
    _prior(tmp_path, "2026-09-28.txt", modified)
    first = tuple(_msg(_NOW, f"one-{index}") for index in range(2))
    second = tuple(_msg(_NOW, f"two-{index}") for index in range(3))
    summary = "Коротко: два письма важны, остальные можно не открывать."

    decision = decide_daily(
        daily_dir=tmp_path,
        now=_NOW,
        mailboxes=_reads(("email1", first), ("email2", second)),
        summary=summary,
    )

    assert decision.write is True
    assert decision.count == 5
    assert decision.notice == "5"
    assert decision.failure is None
    assert "5 писем\nemail1: 2\nemail2: 3\n" in decision.text
    assert summary in decision.text
    assert "one-0" not in decision.text
    assert "two-2" not in decision.text
    assert "From:" not in decision.text
    for message in first + second:
        assert message.subject not in (decision.notice or "")


def test_summary_count_uses_the_window_and_russian_plurals(tmp_path: Path) -> None:
    modified = datetime(2026, 9, 28, 8, 10, tzinfo=UTC)
    _prior(tmp_path, "2026-09-28.txt", modified)
    outside = _msg(modified, "outside-subject")
    inside = _msg(modified + timedelta(seconds=1), "inside-subject")

    decision = decide_daily(
        daily_dir=tmp_path,
        now=_NOW,
        mailboxes=_reads(("email1", (outside, inside)), ("email2", ())),
        summary="Важное\n\nОдно письмо нужно открыть.",
    )

    assert "1 письмо\nemail1: 1\nemail2: 0\n" in decision.text
    assert "outside-subject" not in decision.text
    assert "inside-subject" not in decision.text

    plurals = (
        (2, 0, "2 письма\nemail1: 2\nemail2: 0"),
        (4, 1, "5 писем\nemail1: 4\nemail2: 1"),
        (11, 0, "11 писем\nemail1: 11\nemail2: 0"),
        (21, 0, "21 письмо\nemail1: 21\nemail2: 0"),
        (22, 0, "22 письма\nemail1: 22\nemail2: 0"),
    )
    for email1_count, email2_count, line in plurals:
        decision = decide_daily(
            daily_dir=tmp_path,
            now=_NOW,
            mailboxes=_reads(
                ("email1", tuple(_msg(_NOW, f"e1-{i}") for i in range(email1_count))),
                ("email2", tuple(_msg(_NOW, f"e2-{i}") for i in range(email2_count))),
            ),
            summary="Важное\n\nТекст.",
        )
        assert line in decision.text


def test_summary_length_does_not_block_the_file(tmp_path: Path) -> None:
    short = "Одно. Два."
    long = " ".join(f"Предложение {index}." for index in range(12))

    for summary in (short, long):
        decision = decide_daily(
            daily_dir=tmp_path,
            now=_NOW,
            mailboxes=_reads(
                ("email1", (_msg(_NOW, "hidden-subject"),)), ("email2", ())
            ),
            summary=summary,
        )
        assert decision.write is True
        assert summary in decision.text
        assert "hidden-subject" not in decision.text


def test_blank_summary_with_mail_writes_nothing(tmp_path: Path) -> None:
    modified = datetime(2026, 9, 28, 8, 10, tzinfo=UTC)
    _prior(tmp_path, "2026-09-28.txt", modified)
    subject = "unread-subject"

    decision = decide_daily(
        daily_dir=tmp_path,
        now=_NOW,
        mailboxes=_reads(("email1", (_msg(_NOW, subject),)), ("email2", ())),
        summary="  \n",
    )

    assert decision.write is False
    assert decision.count is None
    assert decision.notice is None
    assert decision.text == ""
    assert decision.failure == SUMMARY_MISS
    assert decision.window_start == modified
    assert subject not in decision.failure
    assert not (tmp_path / "2026-09-29.txt").exists()


def test_miss_marker_keeps_one_reason_line(tmp_path: Path) -> None:
    day = tmp_path / "2026-09-29.txt"
    marker = tmp_path / "2026-09-29.summary-miss"

    record_summary_miss(day, "finish:SAFETY")
    assert marker.read_text(encoding="utf-8") == "finish:SAFETY\n"

    record_summary_miss(day, "secret-subject")
    assert marker.read_text(encoding="utf-8") == ""

    record_summary_miss(day, "request:RuntimeError")
    assert marker.read_text(encoding="utf-8") == "request:RuntimeError\n"


def test_quiet_morning_ignores_a_blank_summary(tmp_path: Path) -> None:
    decision = decide_daily(
        daily_dir=tmp_path,
        now=_NOW,
        mailboxes=_reads(("email1", ()), ("email2", ())),
        summary="  ",
    )

    assert decision.write is True
    assert decision.count == 0
    assert decision.notice == "0"
    assert decision.failure is None
    assert "There were no new messages." in decision.text


def test_mailbox_error_ignores_a_summary(tmp_path: Path) -> None:
    subject = "unread-subject"
    decision = decide_daily(
        daily_dir=tmp_path,
        now=_NOW,
        mailboxes=(
            MailboxRead(alias="email1", messages=(_msg(_NOW, subject),)),
            MailboxRead(alias="email2", error="mailbox unreadable"),
        ),
        summary="Не записывать.",
    )

    assert decision.write is False
    assert decision.failure is None
    assert "Не записывать." not in decision.text
    assert subject not in decision.text


def test_summary_input_uses_body_then_snippet_and_drops_the_boundary(
    tmp_path: Path,
) -> None:
    del tmp_path
    start = datetime(2026, 9, 28, 8, 10, tzinfo=UTC)
    at_boundary = DailyMessage(
        arrived_at=start,
        subject="at-boundary",
        sender="a@example.com",
        date="Tue, 28 Sep 2026 08:10:00 +0000",
        snippet="boundary snippet",
        body="boundary body",
    )
    with_body = DailyMessage(
        arrived_at=start + timedelta(seconds=1),
        subject="has-body",
        sender="a@example.com",
        date="Tue, 29 Sep 2026 10:00:00 +0000",
        snippet="snippet-to-skip",
        body="plain body",
    )
    snippet_only = DailyMessage(
        arrived_at=start + timedelta(minutes=5),
        subject="snippet-only",
        sender="b@example.com",
        date="",
        snippet="only snippet",
    )

    text = render_summary_input(
        _reads(("email1", (at_boundary, with_body)), ("email2", (snippet_only,))),
        window_start=start,
    )

    assert "at-boundary" not in text
    assert "boundary body" not in text
    assert "email1" in text
    assert "Subject: has-body" in text
    assert "From: a@example.com" in text
    assert "Date: Tue, 29 Sep 2026 10:00:00 +0000" in text
    assert "plain body" in text
    assert "snippet-to-skip" not in text
    assert "email2" in text
    assert "Subject: snippet-only" in text
    assert "only snippet" in text
    assert "Date:" not in text.split("snippet-only", 1)[1]


def test_daily_dir_defaults_to_repo_digests_and_honors_override(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[3]
    custom = tmp_path / "custom"

    chosen = resolve_daily_dir(environ={})

    assert chosen == repo / "digests"
    assert "Application Support" not in chosen.parts
    assert (
        resolve_daily_dir(environ={"EMAILS_ASSISTANT_DAILY_DIR": str(custom)}) == custom
    )


def test_gitignore_ignores_digests() -> None:
    root = Path(__file__).resolve().parents[3]
    ignored = (root / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert "digests/" in ignored
