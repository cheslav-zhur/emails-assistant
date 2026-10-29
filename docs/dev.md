# Development environment

Local/dev setup for **emails-assistant**. Product decisions live in `AGENTS.md`; durable stack rationale in `docs/solutions/`.

## Quick start

1. Open this repo in the Dev Container (details below).
2. `cp .env.example .env` — real addresses only in local `.env` (gitignored).
3. On the Mac, with Docker running, log in each mailbox: `make login ALIAS=email1`, then the same command with `ALIAS=email2`. The command opens the system browser. If it cannot, the authorization URL is printed; open that URL and finish consent.
4. `make inject CONTAINER=<container>`, then inside the container: `emails-assistant digest`.
5. Digest (Mac, logged-in GUI session): `make install-daily-agent`.

## Dev Container

Canonical config: `.devcontainer/devcontainer.json`.

Personal Python Dev Container standard (image, pip cache, ssh-agent): see `~/projects/dev-kb/python-devcontainer.md` when creating or changing the container — do not fork a different Python image without asking.

### What this repo uses

- Image: `Dockerfile` target `dev` for this container. The morning build stays `docker build --target app`. Both start from `mcr.microsoft.com/devcontainers/python:3.12-bookworm`. Target `app` installs the `app` extra with `uv sync --frozen` from `uv.lock` into the system Python. Target `dev` adds the Debian bookworm `shellcheck` package on top of `app`. `postCreateCommand` still installs this package editable from the mounted workspace.
- `TZ`: `Asia/Ho_Chi_Minh` (logs / local scheduling; Gmail API queries usually use relative/`newer_than` or UTC)
- uv cache: named volume → `/home/vscode/.cache/uv`
- `postCreateCommand`: `chown` that cache path, then `uv sync --frozen --inexact --extra app --extra login --extra dev`
- Git: host ssh-agent (`SSH_AUTH_SOCK` → `/ssh-agent`)
- Extensions: `ms-python.python`, `ms-python.vscode-pylance`
- `remoteUser`: `vscode`

Opening the Dev Container is an explicit go-ahead for that `postCreate` install only. Do not otherwise `pip`/`uv`/`npm` install until the user says **ok** / **go ahead**.

### Not in the Dev Container by default

- GitHub CLI / `GH_TOKEN`
- Claude Code mounts/features
- Compose
- Editor formatters or linters beyond Pylance.

### Host vs container (auth)

macOS **Keychain** is the only durable store for the OAuth client secret and each mailbox token. Keychain reads and writes stay on the Mac. Mail commands do not call Google's token endpoint.

`src/host/access-token/access-token.sh` is the host script. Login asks for the App scopes in `src/shared.py`: `gmail.readonly`, `gmail.labels`, and `gmail.settings.basic`. `inject` refreshes with those scopes when the stored expiry is missing or already inside the 3 minute 45 second window, stores that access token in Keychain, and hands off `access_token` and `expiry` only. `one-shot` always mints an access token limited to `gmail.readonly` and does not store it, so a fresh App token is not reused for the morning run.

- **Open Dev Container.** `inject <container>` writes one file per alias at `/dev/shm/emails-assistant/access-<alias>.json` (mode `0600`, owner `vscode`) via `docker exec -i -u vscode`. On success it prints `Injected access tokens for <aliases>.` on stderr and does not print a token. `smoke`, `digest`, `search`, and `show` read those files. They do not refresh.
- **One-shot.** `one-shot` prints one JSON object per mailbox on stdout and does not read or write the Dev Container tmpfs. Keep that stdout in memory. Do not write it to the day file, the repo, shell history, or logs.
- **Login.** `login <alias>` is the only way to store a new refresh token. It uses the image `emails-assistant:login` (built when missing or when `pyproject.toml` or `uv.lock` changed) and starts one container with `docker run --rm`. That container mounts `src/login/` and `src/shared.py` only. It does not build the morning image. The consent port is published on `127.0.0.1`; the owner does not pass a container name or forward a port. The client secret is piped to that container on stdin for the run. The Mac opens the system browser. Google redirects to the published port. The mailbox token comes back on container stdout and is stored in Keychain unchanged. The command does not print the token. The container then exits and keeps neither the secret nor the token. If the browser cannot be opened, the authorization URL is printed and the command still waits. If consent is denied or the wait ends, the command fails with `Login did not complete.` and the previous token for that alias stays.

If an access token is missing, expired, or rejected, the mail command stops with `Access token missing or rejected. Run the host script again.` It does not restart the container. If Google rejects the refresh token, the host script prints `Login is required for <alias>. The refresh token was rejected.` on stderr and does not print a token.

`.creds/client.json` and `.creds/token-*.json` must be gone. The host script removes them and exits non-zero if any remain. Do not recreate that directory for mail or login.

### Daily file on the Mac

`src/host/daily/daily.sh` is a per-user LaunchAgent. `StartCalendarInterval` is 08:00 local time, and `RunAtLoad` covers a login after that. The agent does not wake the Mac. Before 08:00 the script exits with no file and no banner. After 08:00 it retries every 15 minutes until today's file exists, a summary miss is recorded, or the local calendar day ends.

Each try calls `one-shot` only when Docker is running. That stdout stays in memory and is piped to `docker run --rm -i -u vscode` of the image below. The container mounts `src/emails_assistant/` and `src/shared.py` read-only, and `digests/` writable. It does not mount the rest of the repo. The Mac timezone comes from `/etc/localtime`. The container imports the mounted package. The script does not attach to the open Dev Container and does not install packages.

The banner is `terminal-notifier`. A success uses subtitle `D Mon` and message `N message(s) summary`. A mailbox, token, or Docker failure shows `Daily digest did not run.` once per failure streak and retries every 15 minutes. A summary miss is container stdout exactly `Summary did not run.` with no day file. The container writes one reason into `digests/YYYY-MM-DD.summary-miss`: `no-key`, `credentials`, `empty`, `request:` plus an exception class, or `finish:` plus a finish reason. The script keeps that line when it matches and otherwise leaves the file empty. It shows that sentence once. A transport `request:` reason (`RemoteProtocolError`, `ConnectError`, timeouts, `NetworkError`) keeps retrying every 15 minutes the same local day; other summary reasons do not call Gemini again that day. Inside one container run, Gemini also retries those transport errors a few times before the miss. The marker is not a `*.txt` file, so the window stays on the last day file. The next local day ignores the marker. A click opens the day directory in Finder: `digests/`, or `EMAILS_ASSISTANT_DAILY_DIR` when that is set. The day file stays closed. On the Mac, install `terminal-notifier` (`brew install terminal-notifier`) and allow its notifications once. The morning run still writes the file when that program is missing.

On the Mac, in a logged-in GUI session, install the agent. The script builds `emails-assistant:app`, copies the plist into `~/Library/LaunchAgents/`, substitutes this repo for `REPLACE_WITH_REPO` and `$HOME` for `REPLACE_WITH_HOME`, creates `~/Library/Logs/emails-assistant/`, and bootstraps it. LaunchAgent stdout/stderr append to `~/Library/Logs/emails-assistant/daily.log` (container INFO on stderr is included). Run `make install-daily-agent` again after the clone moves.

```bash
make install-daily-agent
```

The digest builds that image only when it is missing or `pyproject.toml` or `uv.lock` has changed. A later run does not rebuild it. The login image has its own stamp of those two files.

Day files land in `digests/` in the repo. That directory is gitignored. `EMAILS_ASSISTANT_DAILY_DIR` still overrides the directory.

When gitignored `keys/` exists, the morning container mounts it read-only. It calls Gemini with `keys/gemini.json` and ignores other JSON files in that directory. This is the current store for that key, instead of a `gemini-caller` Keychain item. The host does not mint the token. Mailbox OAuth stays in Keychain. The private key stays out of git.

**Keychain write `ps` check.** Not observed in this session: the Linux Dev Container cannot run `security`. The script passes the mailbox JSON to `security add-generic-password -w`, so that JSON can show in the process list for the length of the write. The refresh body goes to curl on stdin, not as a curl argument. Do not paste a token into this doc when the Mac check is run.

## Accounts (aliases only in git)

Two mailboxes, referred to only as:

- `email1`
- `email2`

Map alias → real address in **local** `.env` (gitignored) or Keychain item attributes — never commit real addresses, tokens, or message fixtures.

## Commands

Inside the container, after `inject`. Mail commands read `/dev/shm/emails-assistant/access-<alias>.json` and do not refresh tokens.

| Command | What it does |
|---------|----------------|
| `emails-assistant digest [--hours N] [--alias ALIAS]` | Recent mail for configured aliases (default 12h, or `EMAILS_ASSISTANT_SINCE_HOURS`) |
| `emails-assistant search ALIAS QUERY [--max N]` | Gmail query, one mailbox (default 20) |
| `emails-assistant show ALIAS MESSAGE_ID` | Headers and plain body of one message |
| `emails-assistant smoke ALIAS` | List one message as a sanity check |
| `emails-assistant daily` | Write today's file and print two lines: `D Mon` and `N message(s) summary`. Piped JSON lines are the morning handoff. An empty stdin reads the injected access files |

On the Mac (`Makefile` → `src/host/`):

| Command | What it does |
|---------|----------------|
| `make inject CONTAINER=<container>` | Refresh due tokens and write access tokens into the container |
| `make one-shot` | Refresh due tokens and print one access-token JSON object per mailbox |
| `make login ALIAS=<alias>` | Open the system browser, take consent in a one-shot container, store the mailbox token |
| `make daily` | Run the morning digest script once (same as the LaunchAgent) |
| `make install-daily-agent` | Install the digest LaunchAgent |
| `make host-check` | `shellcheck` and host `*.test.sh` |

Schedule, retries, and the Docker image for the daily agent are in the Daily file section above.

Interactive mail stays on stdout. The digest writes the day file and shows a count notification. A click opens the day directory. Telegram is still open; do not add a send channel until that is decided.

## Checks

The `dev` extra pins `pytest`, `ruff`, and `pyright`. Opening the Dev Container installs them through `postCreateCommand`. From the repo root, the same commands CI runs:

```bash
ruff check
ruff format --check
pyright
python -m pytest
make host-check
```

`ruff format` without `--check` rewrites files. Pyright uses `standard` and includes `src` only. `shellcheck` in this container is the Debian bookworm package from the `dev` image target. CI calls the binary already on the Ubuntu runner.

## Env

Copy `.env.example` → `.env` and fill local-only values. Knobs are documented in `.env.example`.
