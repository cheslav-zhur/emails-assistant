"""Local .env loading. No network."""

from __future__ import annotations

import os
from pathlib import Path

from emails_assistant.config import load_dotenv


def test_dotenv_keeps_a_dollar_sign_literal(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("EMAILS_ASSISTANT_ACCOUNTS=email1,$NOT_A_VAR\n", encoding="utf-8")
    monkeypatch.delenv("EMAILS_ASSISTANT_ACCOUNTS", raising=False)
    monkeypatch.delenv("NOT_A_VAR", raising=False)

    load_dotenv(env_file)

    assert os.environ["EMAILS_ASSISTANT_ACCOUNTS"] == "email1,$NOT_A_VAR"
