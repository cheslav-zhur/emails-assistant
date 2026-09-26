"""CLI: login, smoke, digest, search, show."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from emails_assistant import config
from emails_assistant.auth import load_credentials, login
from emails_assistant.digest import format_digest, format_search, format_show
from emails_assistant.gmail_api import (
    get_message,
    list_recent_messages,
    search_messages,
    smoke_list_one,
)
from emails_assistant.keychain import KeychainError


def _token_file_for(
    alias: str,
    *,
    token_file: Path | None,
    token_dir: Path | None,
) -> Path | None:
    if token_file is not None:
        return token_file
    if token_dir is not None:
        return token_dir / f"token-{alias}.json"
    return None


def _add_token_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--token-file",
        type=Path,
        help="Token JSON path (skip Keychain)",
    )
    parser.add_argument(
        "--token-dir",
        type=Path,
        help="Dir with token-<alias>.json files (Dev Container bridge)",
    )


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
        help="Browser OAuth; store refresh token (Keychain or --token-file)",
    )
    login_p.add_argument("alias", help="Account alias (email1 or email2)")
    login_p.add_argument(
        "--client-file",
        type=Path,
        help="OAuth client JSON (skip Keychain read; for Dev Container bridge)",
    )
    login_p.add_argument(
        "--token-file",
        type=Path,
        help="Write token JSON here (skip Keychain write)",
    )
    login_p.add_argument(
        "--oauth-port",
        type=int,
        default=0,
        help="Fixed localhost port for OAuth callback (0 = ephemeral)",
    )
    login_p.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open a browser; print the URL instead",
    )

    smoke_p = sub.add_parser(
        "smoke",
        help="List one message via Gmail API",
    )
    smoke_p.add_argument("alias", help="Account alias (email1 or email2)")
    smoke_p.add_argument(
        "--token-file",
        type=Path,
        help="Read/write token JSON here (skip Keychain)",
    )

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
    digest_p.add_argument(
        "--token-file",
        type=Path,
        help="Token JSON for a single --alias (skip Keychain)",
    )
    digest_p.add_argument(
        "--token-dir",
        type=Path,
        help="Dir with token-<alias>.json files (Dev Container bridge)",
    )

    search_p = sub.add_parser(
        "search",
        help="Search one mailbox with a Gmail query",
    )
    search_p.add_argument("alias", help="Account alias (email1 or email2)")
    search_p.add_argument(
        "query",
        help="Gmail search query (e.g. 'from:heroku newer_than:1d')",
    )
    search_p.add_argument(
        "--max",
        type=int,
        default=20,
        dest="max_results",
        help="Max messages (default 20)",
    )
    _add_token_args(search_p)

    show_p = sub.add_parser(
        "show",
        help="Show one message (headers + plain body)",
    )
    show_p.add_argument("alias", help="Account alias (email1 or email2)")
    show_p.add_argument("message_id", help="Gmail message id")
    _add_token_args(show_p)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    try:
        if args.command == "login":
            login(
                args.alias,
                client_file=args.client_file,
                token_file=args.token_file,
                oauth_port=args.oauth_port,
                open_browser=not args.no_browser,
            )
            dest = (
                str(args.token_file)
                if args.token_file
                else f"Keychain token/{args.alias}"
            )
            print(f"login ok: {args.alias} → {dest}")
        elif args.command == "smoke":
            creds = load_credentials(args.alias, token_file=args.token_file)
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
            if args.token_file is not None and len(aliases) != 1:
                raise SystemExit("--token-file requires exactly one --alias")
            for alias in aliases:
                config.resolve_alias(alias)

            sections: list = []
            for alias in aliases:
                token_path = _token_file_for(
                    alias,
                    token_file=args.token_file,
                    token_dir=args.token_dir,
                )
                creds = load_credentials(alias, token_file=token_path)
                messages = list_recent_messages(creds, hours=hours)
                sections.append((alias, messages))

            print(format_digest(hours=hours, sections=sections), end="")
        elif args.command == "search":
            if args.max_results < 1:
                raise SystemExit("--max must be >= 1")
            config.resolve_alias(args.alias)
            token_path = _token_file_for(
                args.alias,
                token_file=args.token_file,
                token_dir=args.token_dir,
            )
            creds = load_credentials(args.alias, token_file=token_path)
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
            config.resolve_alias(args.alias)
            token_path = _token_file_for(
                args.alias,
                token_file=args.token_file,
                token_dir=args.token_dir,
            )
            creds = load_credentials(args.alias, token_file=token_path)
            detail = get_message(creds, args.message_id)
            print(format_show(args.alias, detail), end="")
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
