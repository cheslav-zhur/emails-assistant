"""Aliases and the Gmail scope shared by the mail process and login."""

from __future__ import annotations

import os

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
# Login and inject. The morning one-shot asks only for GMAIL_READONLY_SCOPE.
GMAIL_APP_SCOPES = (
    GMAIL_READONLY_SCOPE,
    "https://www.googleapis.com/auth/gmail.labels",
    "https://www.googleapis.com/auth/gmail.settings.basic",
)


def known_aliases() -> tuple[str, ...]:
    raw = os.environ.get("EMAILS_ASSISTANT_ACCOUNTS", "email1,email2")
    return tuple(a.strip() for a in raw.split(",") if a.strip())


def resolve_alias(alias: str) -> None:
    allowed = known_aliases()
    if alias not in allowed:
        raise SystemExit(
            f"Unknown account alias {alias!r}; expected one of: {', '.join(allowed)}"
        )
