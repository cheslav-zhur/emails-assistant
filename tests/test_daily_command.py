"""Daily subcommand: both mailboxes, then one day file. No live Gmail."""

from __future__ import annotations

import base64
import json
import os
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from google.auth import _helpers

from emails_assistant.cli import main
from emails_assistant.daily import MailboxRead, render_summary_input
from emails_assistant.gmail_api import MessageSummary

_SHM_DIR = Path("/dev/shm/emails-assistant")
_NOW = datetime(2026, 9, 29, 10, 30, tzinfo=timezone.utc)
_TOKEN = "ya29-example-access"
_TOKEN_2 = "ya29-email2"
_REFRESH = "1//refresh-secret-value"
_SUBJECT = "secret-subject"
_FAILURE = "Daily digest did not run."


def _expiry() -> str:
    moment = (_helpers.utcnow() + _helpers.REFRESH_THRESHOLD + timedelta(minutes=30)).replace(microsecond=0)
    return moment.isoformat() + "Z"


def _payload(token: str = _TOKEN, **extra: object) -> dict[str, object]:
    body: dict[str, object] = {"access_token": token, "expiry": _expiry()}
    body.update(extra)
    return body


def _line(payload: dict[str, object]) -> str:
    return json.dumps(payload, separators=(",", ":"))


def _stdin(*payloads: dict[str, object]) -> str:
    return "\n".join(_line(payload) for payload in payloads)


def _run(argv: list[str], *, stdin: str = "") -> tuple[object, str, str]:
    stdout = StringIO()
    stderr = StringIO()
    with (
        patch("sys.stdout", stdout),
        patch("sys.stderr", stderr),
        patch("sys.stdin", StringIO(stdin)),
        patch("emails_assistant.cli._daily_now", return_value=_NOW),
    ):
        try:
            main(argv)
        except SystemExit as exc:
            code = exc.code if exc.code is not None else 0
            return code, stdout.getvalue(), stderr.getvalue()
    return 0, stdout.getvalue(), stderr.getvalue()


def _prior(directory: Path) -> int:
    moment = datetime(2026, 9, 28, 8, 10, tzinfo=timezone.utc)
    path = directory / "2026-09-28.txt"
    path.write_text("yesterday\n")
    epoch = int(moment.timestamp())
    os.utime(path, (epoch, epoch))
    return epoch


def _assert_failed(code: object, out: str, err: str, *forbidden: str) -> None:
    assert code not in (0, None)
    assert out.strip() == _FAILURE
    blob = f"{out}\n{err}"
    for item in forbidden:
        assert item not in blob


class _Exec:
    def __init__(self, result: dict[str, object]) -> None:
        self._result = result

    def execute(self) -> dict[str, object]:
        return self._result


class _Messages:
    def __init__(
        self,
        ids: list[str],
        *,
        error: Exception | None = None,
        bodies: dict[str, str] | None = None,
        snippets: dict[str, str] | None = None,
    ) -> None:
        self.ids = ids
        self.error = error
        self.bodies = bodies or {}
        self.snippets = snippets or {}
        self.queries: list[str] = []
        self.formats: list[str] = []
        self._offset = 0

    def list(self, **kwargs: object) -> _Exec:
        if self.error is not None:
            raise self.error
        self.queries.append(str(kwargs["q"]))
        page = self.ids[self._offset : self._offset + 50]
        self._offset += len(page)
        body: dict[str, object] = {"messages": [{"id": message_id} for message_id in page]}
        if self._offset < len(self.ids):
            body["nextPageToken"] = str(self._offset)
        return _Exec(body)

    def get(self, **kwargs: object) -> _Exec:
        message_id = str(kwargs["id"])
        self.formats.append(str(kwargs.get("format")))
        payload: dict[str, object] = {
            "headers": [
                {"name": "Subject", "value": f"subject-{message_id}"},
                {"name": "From", "value": "owner@example.com"},
                {"name": "Date", "value": "Tue, 29 Sep 2026 10:00:00 +0000"},
            ]
        }
        plain = self.bodies.get(message_id)
        if plain is not None:
            payload["mimeType"] = "text/plain"
            payload["body"] = {
                "data": base64.urlsafe_b64encode(plain.encode()).decode(),
            }
        return _Exec(
            {
                "id": message_id,
                "snippet": self.snippets.get(message_id, ""),
                "payload": payload,
            }
        )


class _Service:
    def __init__(self, messages: _Messages) -> None:
        self._messages = messages

    def users(self) -> _Service:
        return self

    def messages(self) -> _Messages:
        return self._messages


@pytest.fixture
def daily_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("EMAILS_ASSISTANT_ACCOUNTS", "email1,email2")
    monkeypatch.setenv("EMAILS_ASSISTANT_DAILY_DIR", str(tmp_path))
    monkeypatch.setenv("EMAILS_ASSISTANT_SINCE_HOURS", "12")
    if _SHM_DIR.exists():
        for path in _SHM_DIR.glob("access-*.json"):
            path.unlink()
    yield tmp_path
    if _SHM_DIR.exists():
        for path in _SHM_DIR.glob("access-*.json"):
            path.unlink()


def _install_mailboxes(*boxes: _Messages) -> tuple[list[_Messages], object]:
    pending = list(boxes)

    def build(creds: object) -> _Service:
        del creds
        return _Service(pending.pop(0))

    return list(boxes), patch("emails_assistant.gmail_api.build_gmail_service", side_effect=build)


def test_two_mailboxes_become_one_file_and_a_count(daily_dir: Path) -> None:
    first = _Messages(["a", "b"])
    second = _Messages(["c", "d", "e"])
    _boxes, patched = _install_mailboxes(first, second)

    with patched:
        code, out, err = _run(["daily"], stdin=_stdin(_payload(_TOKEN), _payload(_TOKEN_2)))

    day = daily_dir / "2026-09-29.txt"
    text = day.read_text(encoding="utf-8")
    assert code == 0, err
    assert out.strip() == "5"
    assert "email1" in text
    assert "email2" in text
    assert _TOKEN not in text
    assert _TOKEN_2 not in text
    assert _TOKEN not in out
    assert _TOKEN_2 not in out


def test_daily_reads_the_plain_body_into_the_model_input(daily_dir: Path) -> None:
    first = _Messages(
        ["a"],
        bodies={"a": "plain body"},
        snippets={"a": "snippet-to-skip"},
    )
    second = _Messages(["b"], snippets={"b": "only snippet"})
    _boxes, patched = _install_mailboxes(first, second)
    captured: list[str] = []

    def _capture(mailboxes: Sequence[MailboxRead], *, window_start: datetime) -> str:
        text = render_summary_input(mailboxes, window_start=window_start)
        captured.append(text)
        return text

    with patched, patch("emails_assistant.cli.render_summary_input", side_effect=_capture):
        code, out, err = _run(["daily"], stdin=_stdin(_payload(_TOKEN), _payload(_TOKEN_2)))

    day = (daily_dir / "2026-09-29.txt").read_text(encoding="utf-8")
    assert code == 0, err
    assert out.strip() == "2"
    assert first.formats == ["full"]
    assert second.formats == ["full"]
    assert captured == [
        "\n".join(
            [
                "email1",
                "Subject: subject-a",
                "From: owner@example.com",
                "Date: Tue, 29 Sep 2026 10:00:00 +0000",
                "plain body",
                "",
                "email2",
                "Subject: subject-b",
                "From: owner@example.com",
                "Date: Tue, 29 Sep 2026 10:00:00 +0000",
                "only snippet",
            ]
        )
    ]
    assert "snippet-to-skip" not in captured[0]
    assert "subject-a" in day
    assert "subject-b" in day
    assert _TOKEN not in captured[0]


def test_query_uses_after_epoch_from_the_previous_file(daily_dir: Path) -> None:
    epoch = _prior(daily_dir)
    first = _Messages(["a"])
    second = _Messages(["b"])
    _boxes, patched = _install_mailboxes(first, second)

    with patched:
        code, out, _err = _run(["daily"], stdin=_stdin(_payload(_TOKEN), _payload(_TOKEN_2)))

    assert code == 0, out
    assert first.queries == [f"after:{epoch}"]
    assert second.queries == [f"after:{epoch}"]
    assert all("newer_than" not in query for query in first.queries + second.queries)


def test_one_hundred_twenty_messages_are_all_written(daily_dir: Path) -> None:
    ids = [str(index) for index in range(120)]
    first = _Messages(ids)
    second = _Messages([])
    _boxes, patched = _install_mailboxes(first, second)

    with patched:
        code, out, err = _run(["daily"], stdin=_stdin(_payload(_TOKEN), _payload(_TOKEN_2)))

    text = (daily_dir / "2026-09-29.txt").read_text(encoding="utf-8")
    assert code == 0, err
    assert out.strip() == "120"
    assert "subject-119" in text
    assert "subject-99" in text
    assert text.count("subject-") == 120


def test_digest_prints_and_does_not_write_a_daily_file(daily_dir: Path) -> None:
    from emails_assistant.cli import write_access_token_file

    kept = daily_dir / "2026-09-28.txt"
    kept.write_text("keep\n")
    write_access_token_file("email1", _line(_payload(_TOKEN)))
    write_access_token_file("email2", _line(_payload(_TOKEN_2)))
    summary = MessageSummary(id="1", subject="hello", sender="a@example.com", date="", snippet="")

    with patch("emails_assistant.cli.list_recent_messages", return_value=[summary]):
        code, out, err = _run(["digest"])

    assert code == 0, err
    assert "last 12h" in out
    assert "hello" in out
    assert kept.read_text(encoding="utf-8") == "keep\n"
    assert [path.name for path in daily_dir.iterdir()] == ["2026-09-28.txt"]


def test_second_alias_failure_writes_no_file_and_hides_the_subject(daily_dir: Path) -> None:
    first = _Messages(["a"])
    second = _Messages([], error=RuntimeError(_SUBJECT))
    _boxes, patched = _install_mailboxes(first, second)

    with patched:
        code, out, err = _run(["daily"], stdin=_stdin(_payload(_TOKEN), _payload(_TOKEN_2)))

    _assert_failed(code, out, err, _SUBJECT, _TOKEN, _TOKEN_2)
    assert not (daily_dir / "2026-09-29.txt").exists()


def test_refresh_token_on_stdin_writes_no_file(daily_dir: Path) -> None:
    code, out, err = _run(
        ["daily"],
        stdin=_line(_payload(_TOKEN, refresh_token=_REFRESH, subject=_SUBJECT)),
    )

    _assert_failed(code, out, err, _REFRESH, _TOKEN, _SUBJECT)
    assert not (daily_dir / "2026-09-29.txt").exists()
    assert not list(_SHM_DIR.glob("access-*.json")) if _SHM_DIR.exists() else True


def test_payload_count_must_match_aliases(daily_dir: Path) -> None:
    code, out, err = _run(
        ["daily"],
        stdin=_stdin(_payload(_TOKEN), _payload(_TOKEN_2), _payload("ya29-extra")),
    )

    _assert_failed(code, out, err, _TOKEN, _TOKEN_2, "ya29-extra")
    assert not (daily_dir / "2026-09-29.txt").exists()
    assert not list(_SHM_DIR.glob("access-*.json")) if _SHM_DIR.exists() else True
