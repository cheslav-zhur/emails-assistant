"""Browser consent for one mailbox. The mail package is not imported."""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

from google.oauth2.credentials import Credentials

from shared import GMAIL_READONLY_SCOPE, resolve_alias

logger = logging.getLogger(__name__)

LOGIN_FAILED_NOTICE = "Login did not complete."


class LoginError(Exception):
    """Consent did not finish."""


def _parse_client_json(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LoginError(
            "OAuth client JSON is invalid (expected Google Desktop client file)."
        ) from exc
    if "installed" not in data and "web" not in data:
        raise LoginError("OAuth client JSON must contain 'installed' or 'web'.")
    return data


def _login_timeout_seconds() -> float:
    raw = os.environ.get("EMAILS_ASSISTANT_LOGIN_TIMEOUT", "180")
    try:
        timeout = float(raw)
    except ValueError:
        raise LoginError(LOGIN_FAILED_NOTICE) from None
    if timeout <= 0:
        raise LoginError(LOGIN_FAILED_NOTICE)
    return timeout


def login(
    alias: str,
    *,
    client_json: str,
    oauth_port: int = 0,
    open_browser: bool = True,
) -> Credentials:
    """Browser OAuth. Returns the mailbox token; the caller stores it.

    The client secret is accepted for this run only. Nothing is written to
    disk or Keychain here. The authorization URL goes to stderr. The redirect
    host is the Mac loopback; the server listens on every interface so a
    published container port can reach it.
    """
    from google_auth_oauthlib.flow import InstalledAppFlow

    resolve_alias(alias)
    flow = InstalledAppFlow.from_client_config(
        _parse_client_json(client_json),
        scopes=[GMAIL_READONLY_SCOPE],
    )
    original_authorization_url = flow.authorization_url

    def _authorization_url(**kwargs: Any) -> tuple[str, str]:
        url, state = original_authorization_url(**kwargs)
        print(url, file=sys.stderr)
        return url, state

    flow.authorization_url = _authorization_url  # type: ignore[method-assign]
    logger.info("Starting OAuth for alias=%s (port=%s)", alias, oauth_port or "auto")
    timeout_seconds = _login_timeout_seconds()
    try:
        return flow.run_local_server(
            host="127.0.0.1",
            bind_addr="0.0.0.0",
            port=oauth_port,
            prompt="consent",
            open_browser=open_browser,
            authorization_prompt_message="",
            timeout_seconds=timeout_seconds,
        )
    except LoginError:
        raise
    except Exception:
        raise LoginError(LOGIN_FAILED_NOTICE) from None
