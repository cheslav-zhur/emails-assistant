"""Consent entry: ``python -m login <alias>``."""

from __future__ import annotations

import argparse
import logging
import sys

from login import LoginError, login

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="login",
        description="Browser OAuth; mailbox token JSON on stdout",
    )
    parser.add_argument("alias", help="Account alias (email1 or email2)")
    parser.add_argument(
        "--oauth-port",
        type=int,
        default=0,
        help="Fixed localhost port for OAuth callback (0 = ephemeral)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open a browser; print the URL on stderr",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    try:
        creds = login(
            args.alias,
            client_json=sys.stdin.read(),
            oauth_port=args.oauth_port,
            open_browser=not args.no_browser,
        )
    except LoginError as exc:
        logger.error("%s", exc)
        sys.exit(1)
    sys.stdout.write(creds.to_json())


if __name__ == "__main__":
    main()
