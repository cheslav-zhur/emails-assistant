"""Gemini summary text. No network, no Keychain."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from emails_assistant.summary import MODEL, gemini_key_path, summarize


class _Part:
    def __init__(self, text: str = "", *, thought: bool = False) -> None:
        self.text = text
        self.thought = thought


class _Reason:
    def __init__(self, value: str) -> None:
        self.value = value


class _Response:
    def __init__(self, finish_reason: object, parts: list[_Part]) -> None:
        content = type("Content", (), {"parts": parts})()
        candidate = type(
            "Candidate", (), {"finish_reason": finish_reason, "content": content}
        )()
        self.candidates = [candidate]


class _Models:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[dict[str, str]] = []

    def generate_content(self, *, model: str, contents: str) -> object:
        self.calls.append({"model": model, "contents": contents})
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class _Client:
    def __init__(self, response: object) -> None:
        self.models = _Models(response)


def test_stop_text_drops_thoughts_and_repeats_the_band() -> None:
    client = _Client(
        _Response(
            _Reason("STOP"),
            [_Part("hidden thought", thought=True), _Part("Visible sentence.")],
        )
    )

    text = summarize("email1\nSubject: hi", client=client)

    contents = client.models.calls[0]["contents"]
    assert text == "Visible sentence."
    assert client.models.calls[0]["model"] == MODEL == "gemini-3.8-flash"
    assert contents.count("about 4 to 10 sentences") == 2
    assert contents.startswith("Summarize what is important")
    assert contents.endswith("Do not list the messages.")
    assert "Subject: hi" in contents
    assert "hidden thought" not in text


def test_thoughts_only_are_a_miss() -> None:
    client = _Client(_Response("STOP", [_Part("chain", thought=True)]))

    assert summarize("mail", client=client) == ""


def test_safety_max_tokens_and_blank_text_are_misses() -> None:
    cases = [
        _Response("SAFETY", [_Part("blocked")]),
        _Response("MAX_TOKENS", [_Part("cut")]),
        _Response("STOP", [_Part("  ")]),
        _Response("STOP", []),
    ]
    for response in cases:
        client = _Client(response)
        assert summarize("mail", client=client) == ""


def test_a_call_error_is_a_miss_without_the_body(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = _Client(RuntimeError("raw error body secret-subject"))

    with caplog.at_level("ERROR"):
        assert summarize("secret-subject", client=client) == ""

    assert "secret-subject" not in caplog.text


def test_key_path_uses_the_single_keys_file(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    keys = root / "keys"
    keys.mkdir(parents=True)

    assert gemini_key_path(root=root) is None
    one = keys / "one.json"
    one.write_text("{}", encoding="utf-8")
    assert gemini_key_path(root=root) == one
    (keys / "two.json").write_text("{}", encoding="utf-8")
    assert gemini_key_path(root=root) is None


def test_enterprise_client_uses_the_service_account_file(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    key = tmp_path / "gemini.json"
    payload = {
        "type": "service_account",
        "project_id": "proj-1",
        "private_key": "not-a-real-key",
        "client_email": "caller@example.com",
    }
    key.write_text(json.dumps(payload), encoding="utf-8")
    seen: dict[str, object] = {}
    creds = object()

    def _info(info: dict[str, object], *, scopes: list[str]) -> object:
        seen["info"] = info
        seen["scopes"] = scopes
        return creds

    def _capture(**kwargs: object) -> object:
        seen.update(kwargs)
        return _Client(_Response("STOP", [_Part("Ok.")]))

    with (
        patch(
            "google.oauth2.service_account.Credentials.from_service_account_info",
            side_effect=_info,
        ),
        patch("google.genai.Client", side_effect=_capture),
        caplog.at_level("ERROR"),
    ):
        text = summarize("hello", key_path=key)

    assert seen["info"] == payload
    assert seen["scopes"] == ["https://www.googleapis.com/auth/cloud-platform"]
    assert seen["enterprise"] is True
    assert seen["project"] == "proj-1"
    assert seen["location"] == "global"
    assert seen["credentials"] is creds
    assert seen["http_options"] == {"timeout": 180_000}
    assert "api_key" not in seen
    assert text == "Ok."
    assert "not-a-real-key" not in caplog.text


def test_a_bad_key_file_is_a_miss_without_the_key(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    key = tmp_path / "gemini.json"
    key.write_text('{"private_key":"not-a-real-key"}', encoding="utf-8")

    with caplog.at_level("ERROR"):
        assert summarize("secret-subject", key_path=key) == ""

    assert "not-a-real-key" not in caplog.text
    assert "secret-subject" not in caplog.text


def test_importing_the_cli_does_not_load_genai() -> None:
    root = Path(__file__).resolve().parents[3]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src")
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys\n"
                "import emails_assistant.auth\n"
                "import emails_assistant.config\n"
                "import emails_assistant.cli\n"
                "raise SystemExit(0 if 'google.genai' not in sys.modules else 1)\n"
            ),
        ],
        cwd=root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
