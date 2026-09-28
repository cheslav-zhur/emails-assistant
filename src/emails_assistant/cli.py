"""CLI: login, smoke, digest, search, show."""

from __future__ import annotations

import argparse
import json
import logging
import os
import stat
import sys
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials

from emails_assistant import config
from emails_assistant.auth import (
    ACCESS_RERUN_NOTICE,
    load_access_credentials,
    login,
)
from emails_assistant.digest import format_digest, format_search, format_show
from emails_assistant.gmail_api import (
    get_message,
    list_recent_messages,
    search_messages,
    smoke_list_one,
)
from emails_assistant.keychain import KeychainError

ACCESS_TOKEN_DIR = Path("/dev/shm/emails-assistant")
_QUIET_LOGGERS = (
    "google",
    "googleapiclient",
    "google_auth_httplib2",
    "httplib2",
    "urllib3",
)


def access_token_path(alias: str) -> Path:
    config.resolve_alias(alias)
    return ACCESS_TOKEN_DIR / f"access-{alias}.json"


def _under_workspace(path: Path) -> bool:
    workspace = Path.cwd().resolve()
    resolved = path.resolve()
    return resolved == workspace or workspace in resolved.parents


def load_access_token_file(path: Path) -> Credentials:
    """Load a bearer credential. Rejects workspace paths and refresh material."""
    if _under_workspace(path):
        raise KeychainError(ACCESS_RERUN_NOTICE)
    if not path.is_file():
        raise KeychainError(ACCESS_RERUN_NOTICE)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise KeychainError(ACCESS_RERUN_NOTICE) from None
    if not isinstance(payload, dict):
        raise KeychainError(ACCESS_RERUN_NOTICE)
    return load_access_credentials(payload)


def write_access_token_file(alias: str, raw: str) -> Path:
    """Create the tmpfs access file at mode 0600, then write the payload."""
    path = access_token_path(alias)
    if _under_workspace(path):
        raise KeychainError(ACCESS_RERUN_NOTICE)
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_CREAT | os.O_WRONLY | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
        if stat.S_IMODE(os.fstat(fd).st_mode) != 0o600:
            raise KeychainError(ACCESS_RERUN_NOTICE)
        os.write(fd, raw.encode("utf-8"))
    finally:
        os.close(fd)
    return path


def _mail_credentials(alias: str) -> Credentials:
    try:
        return load_access_token_file(access_token_path(alias))
    except KeychainError:
        raise SystemExit(ACCESS_RERUN_NOTICE) from None


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    if verbose:
        for name in _QUIET_LOGGERS:
            logging.getLogger(name).setLevel(logging.WARNING)


def main(argv: list[str] | None = None) -> None:
    config.load_dotenv()
    parser = argparse.ArgumentParser(
        prog="emails-assistant",
        description="Gmail assistant (readonly)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Debug logging",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    login_p = sub.add_parser(
        "login",
        help="Browser OAuth; mailbox token JSON on stdout",
    )
    login_p.add_argument("alias", help="Account alias (email1 or email2)")
    login_p.add_argument(
        "--oauth-port",
        type=int,
        default=0,
        help="Fixed localhost port for OAuth callback (0 = ephemeral)",
    )
    login_p.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open a browser; print the URL on stderr",
    )

    smoke_p = sub.add_parser(
        "smoke",
        help="List one message via Gmail API",
    )
    smoke_p.add_argument("alias", help="Account alias (email1 or email2)")

    digest_p = sub.add_parser(
        "digest",
        help="Plain-text digest of recent mail for configured aliases",
    )
    digest_p.add_argument(
        "--alias",
        action="append",
        dest="aliases",
        help="Alias to include (repeatable; default: all from env)",
    )
    digest_p.add_argument(
        "--hours",
        type=int,
        default=None,
        help="Lookback hours (default: EMAILS_ASSISTANT_SINCE_HOURS or 12)",
    )

    search_p = sub.add_parser(
        "search",
        help="Search one mailbox with a Gmail query",
    )
    search_p.add_argument("alias", help="Account alias (email1 or email2)")
    search_p.add_argument(
        "query",
        help="Gmail search query (e.g. 'from: heroku newer_than:1d')",
    )
    search_p.add_argument(
        "--max",
        type=int,
        default=20,
        dest="max_results",
        help="Max messages (default 20)",
    )

    show_p = sub.add_parser(
        "show",
        help="Show one message (headers + plain body)",
    )
    show_p.add_argument("alias", help="Account alias (email1 or email2)")
    show_p.add_argument("message_id", help="Gmail message id")

    args = parser.parse_args(argv)
    _configure_logging(args.verbose)

    try:
        if args.command == "login":
            creds = login(
                args.alias,
                client_json=sys.stdin.read(),
                oauth_port=args.oauth_port,
                open_browser=not args.no_browser,
            )
            sys.stdout.write(creds.to_json())
        elif args.command == "smoke":
            creds = _mail_credentials(args.alias)
            info = smoke_list_one(creds)
            if not info["id"]:
                print(f"smoke ok: {args.alias} (no messages)")
            else:
                print(
                    f"smoke ok: {args.alias} "
                    f"id={info['id']} from={info['from']!r} "
                    f"subject={info['subject']!r}"
                )
        elif args.command == "digest":
            hours = args.hours if args.hours is not None else config.since_hours()
            if hours < 1:
                raise SystemExit("--hours must be >= 1")
            aliases = tuple(args.aliases) if args.aliases else config.known_aliases()
            for alias in aliases:
                config.resolve_alias(alias)

            sections: list = []
            for alias in aliases:
                creds = _mail_credentials(alias)
                messages = list_recent_messages(creds, hours=hours)
                sections.append((alias, messages))

            print(format_digest(hours=hours, sections=sections), end="")
        elif args.command == "search":
            if args.max_results < 1:
                raise SystemExit("--max must be >= 1")
            creds = _mail_credentials(args.alias)
            messages = search_messages(
                creds,
                query=args.query,
                max_results=args.max_results,
            )
            print(
                format_search(args.alias, query=args.query, messages=messages),
                end="",
            )
        elif args.command == "show":
            creds = _mail_credentials(args.alias)
            detail = get_message(creds, args.message_id)
            print(format_show(args.alias, detail), end="")
    except RefreshError:
        raise SystemExit(ACCESS_RERUN_NOTICE) from None
    except KeychainError as exc:
        logging.error("%s", exc)
        sys.exit(1)
    except SystemExit:
        raise
    except Exception:
        logging.exception("Command failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
