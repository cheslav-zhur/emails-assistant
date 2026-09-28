"""OAuth login and credential load/store (Keychain or injected files)."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, NoReturn

from google.auth import _helpers
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from emails_assistant import config
from emails_assistant.keychain import (
    KeychainError,
    get_generic_password,
    set_generic_password,
)

logger = logging.getLogger(__name__)

ACCESS_RERUN_NOTICE = "Access token missing or rejected. Run the host script again."


def _reject_access_payload() -> NoReturn:
    raise KeychainError(ACCESS_RERUN_NOTICE)


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
    if "expiry" not in payload or payload.get("expiry") in (None, ""):
        _reject_access_payload()
    expiry = _parse_access_expiry(payload["expiry"])
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
        raise KeychainError(
            "OAuth client JSON is invalid (expected Google Desktop client file)."
        ) from exc
    if "installed" not in data and "web" not in data:
        raise KeychainError(
            "OAuth client JSON must contain 'installed' or 'web'."
        )
    return data


def _client_config(*, client_file: Path | None) -> dict[str, Any]:
    if client_file is not None:
        return _parse_client_json(client_file.read_text(encoding="utf-8"))
    return _parse_client_json(
        get_generic_password(
            service=config.keychain_service(),
            account=config.OAUTH_CLIENT_ACCOUNT,
        )
    )


def login(
    alias: str,
    *,
    client_file: Path | None = None,
    token_file: Path | None = None,
    oauth_port: int = 0,
    open_browser: bool = True,
) -> Credentials:
    """Browser OAuth; store credentials in Keychain or ``token_file``."""
    config.resolve_alias(alias)
    flow = InstalledAppFlow.from_client_config(
        _client_config(client_file=client_file),
        scopes=[config.GMAIL_READONLY_SCOPE],
    )
    logger.info("Starting OAuth for alias=%s (port=%s)", alias, oauth_port or "auto")
    creds = flow.run_local_server(
        port=oauth_port,
        prompt="consent",
        open_browser=open_browser,
    )
    _store_credentials(alias, creds, token_file=token_file)
    return creds


def load_credentials(
    alias: str,
    *,
    token_file: Path | None = None,
) -> Credentials:
    """Load credentials; refresh and re-store when needed."""
    config.resolve_alias(alias)
    if token_file is not None:
        raw = token_file.read_text(encoding="utf-8")
    else:
        raw = get_generic_password(
            service=config.keychain_service(),
            account=config.token_account(alias),
        )
    creds = Credentials.from_authorized_user_info(
        json.loads(raw),
        scopes=[config.GMAIL_READONLY_SCOPE],
    )
    if creds.valid:
        return creds
    if creds.expired and creds.refresh_token:
        logger.info("Refreshing access token for alias=%s", alias)
        creds.refresh(Request())
        _store_credentials(alias, creds, token_file=token_file)
        return creds
    raise KeychainError(
        f"Credentials for {alias!r} are invalid; run login for that alias again."
    )


def _store_credentials(
    alias: str,
    creds: Credentials,
    *,
    token_file: Path | None,
) -> None:
    payload = creds.to_json()
    if token_file is not None:
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(payload, encoding="utf-8")
        token_file.chmod(0o600)
        logger.info("Wrote token file %s", token_file)
        return
    set_generic_password(
        service=config.keychain_service(),
        account=config.token_account(alias),
        password=payload,
    )
