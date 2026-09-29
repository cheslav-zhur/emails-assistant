"""OAuth login and bearer access-token load."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from typing import Any, Mapping, NoReturn

from google.auth import _helpers
from google.oauth2.credentials import Credentials

from emails_assistant import config

logger = logging.getLogger(__name__)

ACCESS_RERUN_NOTICE = "Access token missing or rejected. Run the host script again."


class CredentialError(RuntimeError):
    """Caller-facing failure while accepting credentials."""


def _reject_access_payload() -> NoReturn:
    raise CredentialError(ACCESS_RERUN_NOTICE)


def _parse_access_expiry(raw: object) -> datetime:
    """Naive UTC expiry in the ``to_json()`` form: isoformat plus ``Z``."""
    if not isinstance(raw, str) or not raw.endswith("Z"):
        _reject_access_payload()
    body = raw[:-1]
    # A numeric offset (``+07:00`` / ``-07:00``) is not the naive UTC form.
    if "+" in body or body.count("-") != 2:
        _reject_access_payload()
    try:
        return datetime.strptime(body.split(".")[0], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        _reject_access_payload()


def access_token_is_due(expiry: datetime) -> bool:
    """True when google-auth would already treat the token as expired."""
    return _helpers.utcnow() >= expiry - _helpers.REFRESH_THRESHOLD


def load_access_credentials(payload: Mapping[str, Any]) -> Credentials:
    """Build a readonly Gmail credential from ``access_token`` and ``expiry`` only.

    Refuses refresh material. An already-due token fails before any HTTP call.
    """
    if not isinstance(payload, Mapping):
        _reject_access_payload()
    if "refresh_token" in payload or "client_secret" in payload:
        _reject_access_payload()
    token = payload.get("access_token")
    if not isinstance(token, str) or not token.strip():
        _reject_access_payload()
    expiry = _parse_access_expiry(payload.get("expiry"))
    if access_token_is_due(expiry):
        _reject_access_payload()
    return Credentials(
        token=token,
        expiry=expiry,
        scopes=[config.GMAIL_READONLY_SCOPE],
    )


def _parse_client_json(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CredentialError(
            "OAuth client JSON is invalid (expected Google Desktop client file)."
        ) from exc
    if "installed" not in data and "web" not in data:
        raise CredentialError(
            "OAuth client JSON must contain 'installed' or 'web'."
        )
    return data


def login(
    alias: str,
    *,
    client_json: str,
    oauth_port: int = 0,
    open_browser: bool = True,
) -> Credentials:
    """Browser OAuth. Returns the mailbox token; the caller stores it.

    The client secret is accepted for this run only. Nothing is written to
    disk or Keychain here. The authorization URL goes to stderr.
    """
    from google_auth_oauthlib.flow import InstalledAppFlow

    config.resolve_alias(alias)
    flow = InstalledAppFlow.from_client_config(
        _parse_client_json(client_json),
        scopes=[config.GMAIL_READONLY_SCOPE],
    )
    original_authorization_url = flow.authorization_url

    def _authorization_url(**kwargs: Any) -> tuple[str, str]:
        url, state = original_authorization_url(**kwargs)
        print(url, file=sys.stderr)
        return url, state

    flow.authorization_url = _authorization_url  # type: ignore[method-assign]
    logger.info("Starting OAuth for alias=%s (port=%s)", alias, oauth_port or "auto")
    return flow.run_local_server(
        port=oauth_port,
        prompt="consent",
        open_browser=open_browser,
        authorization_prompt_message="",
    )
