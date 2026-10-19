"""Runtime config from environment (optional local .env)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv as _load_dotenv

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


def load_dotenv(path: Path | None = None) -> None:
    """Load the cwd ``.env`` into ``os.environ`` without overriding existing variables.

    ``$`` stays literal. Values are not expanded from the environment.
    """
    _load_dotenv(path or Path.cwd() / ".env", override=False, interpolate=False)


def known_aliases() -> tuple[str, ...]:
    raw = os.environ.get("EMAILS_ASSISTANT_ACCOUNTS", "email1,email2")
    return tuple(a.strip() for a in raw.split(",") if a.strip())


def since_hours(default: int = 12) -> int:
    raw = os.environ.get("EMAILS_ASSISTANT_SINCE_HOURS", str(default))
    try:
        hours = int(raw)
    except ValueError as exc:
        raise SystemExit(
            f"EMAILS_ASSISTANT_SINCE_HOURS must be an int, got {raw!r}"
        ) from exc
    if hours < 1:
        raise SystemExit("EMAILS_ASSISTANT_SINCE_HOURS must be >= 1")
    return hours


def resolve_alias(alias: str) -> None:
    allowed = known_aliases()
    if alias not in allowed:
        raise SystemExit(
            f"Unknown account alias {alias!r}; expected one of: {', '.join(allowed)}"
        )
