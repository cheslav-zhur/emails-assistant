"""macOS Keychain access via the ``security`` CLI (host only)."""

from __future__ import annotations

import logging
import platform
import subprocess

logger = logging.getLogger(__name__)


class KeychainError(RuntimeError):
    """Failed to read or write a Keychain item."""


def require_macos() -> None:
    if platform.system() != "Darwin":
        raise SystemExit(
            "Keychain/OAuth login must run on the Mac host (not Linux Dev Container)."
        )


def get_generic_password(*, service: str, account: str) -> str:
    require_macos()
    result = subprocess.run(
        [
            "security",
            "find-generic-password",
            "-s",
            service,
            "-a",
            account,
            "-w",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise KeychainError(
            f"Keychain item not found or unreadable "
            f"(service={service!r}, account={account!r}): {err}"
        )
    return result.stdout.rstrip("\n")


def set_generic_password(*, service: str, account: str, password: str) -> None:
    require_macos()
    result = subprocess.run(
        [
            "security",
            "add-generic-password",
            "-s",
            service,
            "-a",
            account,
            "-w",
            password,
            "-U",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise KeychainError(
            f"Failed to store Keychain item "
            f"(service={service!r}, account={account!r}): {err}"
        )
    logger.info("Stored Keychain item account=%s", account)
