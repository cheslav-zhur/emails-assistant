"""Bearer access-token loader: no refresh token, no token endpoint."""

from __future__ import annotations

import unittest
from datetime import timedelta

import httplib2
from google.auth import _helpers
from google_auth_httplib2 import AuthorizedHttp

from emails_assistant.auth import load_access_credentials
from emails_assistant.keychain import KeychainError

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
        return httplib2.Response({"status": "200"}), b'{"emailAddress":"alias@example.com"}'


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
        with self.assertRaises(KeychainError):
            load_access_credentials(_safe_payload(expiry=_expiry_z(timedelta(hours=-1))))
        self.assertEqual(http.uris, [])

    def test_expiry_inside_refresh_window_raises_before_http(self) -> None:
        http = _RecordingHttp()
        inside = _helpers.REFRESH_THRESHOLD - timedelta(seconds=30)
        with self.assertRaises(KeychainError):
            load_access_credentials(_safe_payload(expiry=_expiry_z(inside)))
        self.assertEqual(http.uris, [])

    def test_refresh_token_rejected_before_credential(self) -> None:
        with self.assertRaises(KeychainError) as caught:
            load_access_credentials(_safe_payload(refresh_token=_REFRESH))
        self.assertNotIn(_REFRESH, str(caught.exception))
        self.assertNotIn(_TOKEN, str(caught.exception))

    def test_client_secret_rejected_before_credential(self) -> None:
        with self.assertRaises(KeychainError) as caught:
            load_access_credentials(_safe_payload(client_secret=_CLIENT_SECRET))
        self.assertNotIn(_CLIENT_SECRET, str(caught.exception))

    def test_missing_expiry_rejected(self) -> None:
        payload = _safe_payload()
        del payload["expiry"]
        with self.assertRaises(KeychainError) as caught:
            load_access_credentials(payload)
        self.assertNotIn(_TOKEN, str(caught.exception))

    def test_empty_access_token_rejected(self) -> None:
        with self.assertRaises(KeychainError):
            load_access_credentials(_safe_payload(access_token=""))
