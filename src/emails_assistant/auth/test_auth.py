"""Bearer access-token loader and mail commands that never refresh."""

from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import timedelta
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import httplib2
from google.auth import _helpers
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google_auth_httplib2 import AuthorizedHttp

from emails_assistant.auth import (
    ACCESS_RERUN_NOTICE,
    CredentialError,
    load_access_credentials,
)
from emails_assistant.cli import main
from login.__main__ import main as login_main
from shared import GMAIL_APP_SCOPES

_SHM_DIR = Path("/dev/shm/emails-assistant")

_TOKEN = "ya29-example-access"
_REFRESH = "1//refresh-secret-value"
_CLIENT_SECRET = "client-secret-value"
_GMAIL_URL = "https://gmail.googleapis.com/gmail/v1/users/me/profile"
_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"


def _expiry_z(delta: timedelta) -> str:
    moment = (_helpers.utcnow() + delta).replace(microsecond=0)
    return moment.isoformat() + "Z"


def _safe_payload(**extra: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "access_token": _TOKEN,
        "expiry": _expiry_z(_helpers.REFRESH_THRESHOLD + timedelta(minutes=30)),
    }
    payload.update(extra)
    return payload


def _assert_bearer_only(test: unittest.TestCase, cred: Credentials) -> None:
    test.assertIsNone(cred.refresh_token)
    test.assertIsNone(cred.client_secret)
    test.assertIsNone(cred.token_uri)


@contextmanager
def _gmail_transport(
    status: int, payload: bytes
) -> Iterator[tuple[list[str], list[Credentials]]]:
    """Record AuthorizedHttp calls. The inner httplib2 transport never leaves the test."""
    uris: list[str] = []
    seen: list[Credentials] = []
    real_init = AuthorizedHttp.__init__

    def spy_init(
        self: AuthorizedHttp,
        credentials: Credentials,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        seen.append(credentials)
        real_init(self, credentials, *args, **kwargs)

    def request(
        self: object,
        uri: str,
        method: str = "GET",
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        **kwargs: object,
    ) -> tuple[httplib2.Response, bytes]:
        del self, method, body, headers, kwargs
        uris.append(uri)
        return httplib2.Response({"status": str(status)}), payload

    with (
        patch.object(AuthorizedHttp, "__init__", spy_init),
        patch("httplib2.Http.request", request),
    ):
        yield uris, seen


class _RecordingHttp:
    def __init__(self) -> None:
        self.uris: list[str] = []
        self.headers: list[dict[str, str]] = []

    def request(
        self,
        uri: str,
        method: str = "GET",
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        redirections: int = 5,
        connection_type: object | None = None,
    ) -> tuple[httplib2.Response, bytes]:
        self.uris.append(uri)
        self.headers.append(dict(headers or {}))
        return httplib2.Response(
            {"status": "200"}
        ), b'{"emailAddress":"alias@example.com"}'


class LoadAccessCredentialsTest(unittest.TestCase):
    def test_future_expiry_builds_bearer_and_skips_token_endpoint(self) -> None:
        creds = load_access_credentials(_safe_payload())
        self.assertEqual(creds.token, _TOKEN)
        self.assertIsNone(creds.refresh_token)
        self.assertIsNone(creds.client_secret)
        self.assertIsNone(creds.token_uri)
        self.assertFalse(creds.expired)

        http = _RecordingHttp()
        AuthorizedHttp(creds, http=http).request(_GMAIL_URL)
        self.assertEqual(http.uris, [_GMAIL_URL])
        self.assertNotIn(_TOKEN_ENDPOINT, http.uris)
        joined = " ".join(uri for uri in http.uris)
        self.assertNotIn("/token", joined)

    def test_past_expiry_raises_before_http(self) -> None:
        http = _RecordingHttp()
        with self.assertRaises(CredentialError):
            load_access_credentials(
                _safe_payload(expiry=_expiry_z(timedelta(hours=-1)))
            )
        self.assertEqual(http.uris, [])

    def test_expiry_inside_refresh_window_raises_before_http(self) -> None:
        http = _RecordingHttp()
        inside = _helpers.REFRESH_THRESHOLD - timedelta(seconds=30)
        with self.assertRaises(CredentialError):
            load_access_credentials(_safe_payload(expiry=_expiry_z(inside)))
        self.assertEqual(http.uris, [])

    def test_refresh_token_rejected_before_credential(self) -> None:
        with self.assertRaises(CredentialError) as caught:
            load_access_credentials(_safe_payload(refresh_token=_REFRESH))
        self.assertNotIn(_REFRESH, str(caught.exception))
        self.assertNotIn(_TOKEN, str(caught.exception))

    def test_client_secret_rejected_before_credential(self) -> None:
        with self.assertRaises(CredentialError) as caught:
            load_access_credentials(_safe_payload(client_secret=_CLIENT_SECRET))
        self.assertNotIn(_CLIENT_SECRET, str(caught.exception))

    def test_missing_expiry_rejected(self) -> None:
        payload = _safe_payload()
        del payload["expiry"]
        with self.assertRaises(CredentialError) as caught:
            load_access_credentials(payload)
        self.assertNotIn(_TOKEN, str(caught.exception))

    def test_empty_access_token_rejected(self) -> None:
        with self.assertRaises(CredentialError):
            load_access_credentials(_safe_payload(access_token=""))


def _run_cli(
    argv: list[str],
    *,
    stdin: str = "",
    entry: Callable[[list[str] | None], None] = main,
) -> tuple[object, str, str]:
    stdout = StringIO()
    stderr = StringIO()
    with (
        patch("sys.stdout", stdout),
        patch("sys.stderr", stderr),
        patch("sys.stdin", StringIO(stdin)),
    ):
        try:
            entry(argv)
        except SystemExit as exc:
            return (
                exc.code if exc.code is not None else 0,
                stdout.getvalue(),
                stderr.getvalue(),
            )
    return 0, stdout.getvalue(), stderr.getvalue()


def _write_access_file(alias: str, payload: dict[str, object]) -> Path:
    from emails_assistant.cli import write_access_token_file

    return write_access_token_file(alias, json.dumps(payload))


def _live_access_names() -> set[str]:
    if not _SHM_DIR.is_dir():
        return set()
    return {path.name for path in _SHM_DIR.glob("access-*.json")}


def _project_files() -> set[Path]:
    root = Path.cwd()
    return {
        path
        for path in root.rglob("*")
        if path.is_file()
        and ".venv" not in path.relative_to(root).parts
        and "__pycache__" not in path.parts
    }


class MailCommandAccessTokenTest(unittest.TestCase):
    def setUp(self) -> None:
        self._env = patch.dict(
            os.environ,
            {"EMAILS_ASSISTANT_ACCOUNTS": "email1,email2"},
            clear=False,
        )
        self._env.start()
        self._tmp = tempfile.TemporaryDirectory()
        self.access_dir = Path(self._tmp.name)
        self._dir = patch("emails_assistant.cli.ACCESS_TOKEN_DIR", self.access_dir)
        self._dir.start()
        self._live_before = _live_access_names()

    def tearDown(self) -> None:
        try:
            self.assertEqual(_live_access_names(), self._live_before)
        finally:
            for name in _live_access_names() - self._live_before:
                (_SHM_DIR / name).unlink(missing_ok=True)
            self._dir.stop()
            self._tmp.cleanup()
            self._env.stop()

    def test_digest_reads_two_access_files_and_skips_token_endpoint(self) -> None:
        _write_access_file("email1", _safe_payload())
        _write_access_file("email2", _safe_payload(access_token="ya29-email2"))
        empty = b'{"messages":[],"resultSizeEstimate":0}'
        with _gmail_transport(200, empty) as (uris, seen):
            code, out, err = _run_cli(["digest"])
        self.assertEqual(code, 0, err)
        self.assertIn("email1", out)
        self.assertIn("email2", out)
        self.assertEqual([cred.token for cred in seen], [_TOKEN, "ya29-email2"])
        for cred in seen:
            _assert_bearer_only(self, cred)
        self.assertTrue(uris)
        self.assertTrue(
            all(uri.startswith("https://gmail.googleapis.com/") for uri in uris)
        )
        self.assertNotIn(_TOKEN_ENDPOINT, uris)
        self.assertNotIn("/token", " ".join(uris))
        self.assertNotIn(_TOKEN, err)

    def test_digest_401_stays_on_gmail_and_exits_with_notice(self) -> None:
        _write_access_file("email1", _safe_payload())
        with _gmail_transport(401, b'{"error":"unauthorized"}') as (uris, seen):
            code, out, err = _run_cli(["digest", "--alias", "email1"])
        combined = f"{code}\n{out}\n{err}"
        self.assertIn(ACCESS_RERUN_NOTICE, combined)
        self.assertEqual(len(seen), 1)
        _assert_bearer_only(self, seen[0])
        self.assertEqual(len(uris), 1)
        self.assertTrue(uris[0].startswith("https://gmail.googleapis.com/"))
        self.assertNotIn(_TOKEN_ENDPOINT, uris[0])
        self.assertNotIn("/token", uris[0])
        self.assertNotIn(_TOKEN, combined)

    def test_digest_expired_alias_skips_gmail(self) -> None:
        _write_access_file("email1", _safe_payload())
        _write_access_file(
            "email2",
            _safe_payload(
                access_token="ya29-expired-alias",
                expiry=_expiry_z(timedelta(minutes=-5)),
            ),
        )
        with patch(
            "emails_assistant.cli.list_recent_messages", return_value=[]
        ) as gmail:
            code, _out, err = _run_cli(["digest"])
        self.assertNotEqual(code, 0)
        self.assertIn(ACCESS_RERUN_NOTICE, f"{code}\n{err}")
        called_tokens = [call.args[0].token for call in gmail.call_args_list]
        self.assertNotIn("ya29-expired-alias", called_tokens)
        for call in gmail.call_args_list:
            _assert_bearer_only(self, call.args[0])

    def test_search_missing_file_exits_with_notice(self) -> None:
        with patch("emails_assistant.cli.search_messages") as gmail:
            code, _out, err = _run_cli(["search", "email1", "newer_than:1d"])
        self.assertNotEqual(code, 0)
        self.assertIn(ACCESS_RERUN_NOTICE, f"{code}\n{err}")
        gmail.assert_not_called()

    def test_refresh_error_notice_omits_payload(self) -> None:
        _write_access_file("email1", _safe_payload())
        leaked = "Authorization: Bearer ya29-leaked-body"
        with patch(
            "emails_assistant.cli.list_recent_messages",
            side_effect=RefreshError(leaked),
        ) as gmail:
            code, out, err = _run_cli(["-v", "digest", "--alias", "email1"])
        combined = f"{code}\n{out}\n{err}"
        self.assertIn(ACCESS_RERUN_NOTICE, combined)
        _assert_bearer_only(self, gmail.call_args.args[0])
        self.assertNotIn("ya29-leaked-body", combined)
        self.assertNotIn("Authorization", combined)
        self.assertNotIn(_TOKEN, combined)
        self.assertNotIn(str(self.access_dir / "access-email1.json"), combined)
        self.assertNotIn(str(_SHM_DIR / "access-email1.json"), combined)

    def test_full_token_file_is_not_an_access_file(self) -> None:
        legacy = self.access_dir / "token-email1.json"
        legacy.write_text(
            json.dumps(
                {
                    "token": _TOKEN,
                    "refresh_token": _REFRESH,
                    "client_secret": _CLIENT_SECRET,
                    "expiry": _expiry_z(timedelta(hours=1)),
                }
            ),
            encoding="utf-8",
        )
        with patch("emails_assistant.cli.list_recent_messages") as gmail:
            code, _out, err = _run_cli(["digest", "--alias", "email1"])
        combined = f"{code}\n{err}"
        self.assertIn(ACCESS_RERUN_NOTICE, combined)
        self.assertNotIn(_REFRESH, combined)
        self.assertNotIn(_CLIENT_SECRET, combined)
        gmail.assert_not_called()

    def test_tmpfs_path_is_allowed_when_cwd_is_root(self) -> None:
        from emails_assistant import cli

        with patch.object(cli.Path, "cwd", return_value=Path("/")):
            self.assertFalse(cli._under_workspace(_SHM_DIR / "access-email1.json"))
            self.assertTrue(cli._under_workspace(Path(__file__).resolve()))

    def test_workspace_path_rejected(self) -> None:
        from emails_assistant.cli import load_access_token_file

        workspace_file = Path.cwd() / "access-email1.json"
        workspace_file.write_text(json.dumps(_safe_payload()), encoding="utf-8")
        try:
            with self.assertRaises(CredentialError) as caught:
                load_access_token_file(workspace_file)
            self.assertNotIn("access-email1.json", str(caught.exception))
            self.assertNotIn(_TOKEN, str(caught.exception))
        finally:
            workspace_file.unlink(missing_ok=True)

    def test_login_stdout_is_mailbox_json_only(self) -> None:
        expiry = _helpers.utcnow().replace(microsecond=0) + timedelta(hours=1)
        creds = Credentials(
            token="ya29-login",
            refresh_token=_REFRESH,
            token_uri="https://oauth2.googleapis.com/token",
            client_id="client-id",
            client_secret=_CLIENT_SECRET,
            expiry=expiry,
        )
        client = json.dumps(
            {
                "installed": {
                    "client_id": "client-id",
                    "client_secret": _CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["http://localhost"],
                }
            }
        )
        auth_url = "https://accounts.google.com/o/oauth2/auth?test=1"
        before = _project_files()
        with patch(
            "google_auth_oauthlib.flow.InstalledAppFlow.from_client_config"
        ) as factory:
            flow = MagicMock()
            factory.return_value = flow
            flow.authorization_url.return_value = (auth_url, "state")

            def run_local_server(**kwargs: object) -> Credentials:
                self.assertEqual(kwargs.get("authorization_prompt_message"), "")
                self.assertEqual(kwargs.get("prompt"), "consent")
                self.assertEqual(kwargs.get("host"), "127.0.0.1")
                self.assertEqual(kwargs.get("bind_addr"), "0.0.0.0")
                self.assertEqual(kwargs.get("timeout_seconds"), 180)
                flow.authorization_url()
                return creds

            flow.run_local_server.side_effect = run_local_server
            code, out, err = _run_cli(
                ["email1", "--no-browser"],
                stdin=client,
                entry=login_main,
            )
        self.assertEqual(code, 0, err)
        self.assertNotIn("login ok", out)
        self.assertEqual(json.loads(out), json.loads(creds.to_json()))
        self.assertIn(auth_url, err)
        self.assertNotIn(_CLIENT_SECRET, err)
        after = _project_files()
        self.assertEqual(before, after)
        self.assertEqual(
            factory.call_args.kwargs["scopes"],
            list(GMAIL_APP_SCOPES),
        )

    def test_access_file_is_created_mode_0600_before_write(self) -> None:
        from emails_assistant.cli import write_access_token_file

        raw = json.dumps(_safe_payload())
        modes: list[int] = []
        real_write = os.write

        def spy_write(fd: int, data: bytes) -> int:
            modes.append(stat.S_IMODE(os.fstat(fd).st_mode))
            return real_write(fd, data)

        with patch("emails_assistant.cli.os.write", side_effect=spy_write):
            path = write_access_token_file("email1", raw)
        self.assertEqual(path, self.access_dir / "access-email1.json")
        self.assertEqual(modes, [0o600])
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(
            json.loads(path.read_text(encoding="utf-8"))["access_token"], _TOKEN
        )
