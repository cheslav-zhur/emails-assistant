"""Runtime config from environment (optional local .env)."""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
DEFAULT_KEYCHAIN_SERVICE = "emails-assistant"
OAUTH_CLIENT_ACCOUNT = "oauth-client"


def load_dotenv(path: Path | None = None) -> None:
    """Load KEY=VALUE lines from .env into os.environ if not already set."""
    env_path = path or Path.cwd() / ".env"
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value
    logger.debug("Loaded env file %s", env_path)


def keychain_service() -> str:
    return os.environ.get(
        "EMAILS_ASSISTANT_KEYCHAIN_SERVICE", DEFAULT_KEYCHAIN_SERVICE
    )


def known_aliases() -> tuple[str, ...]:
    raw = os.environ.get("EMAILS_ASSISTANT_ACCOUNTS", "email1,email2")
    return tuple(a.strip() for a in raw.split(",") if a.strip())


def token_account(alias: str) -> str:
    return f"token/{alias}"


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
