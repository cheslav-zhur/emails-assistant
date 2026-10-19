# Development environment

Local/dev setup for **emails-assistant**. Product decisions live in `AGENTS.md`; durable stack rationale in `docs/solutions/`.

## Quick start

1. Open this repo in the Dev Container (details below).
2. `cp .env.example .env` — real addresses only in local `.env` (gitignored).
3. On the Mac, with Docker running, log in each mailbox: `scripts/macos-access-token.sh login email1`, then the same command with `email2`. The command opens the system browser. If it cannot, the authorization URL is printed; open that URL and finish consent.
4. `scripts/macos-access-token.sh inject <container>`, then inside the container: `emails-assistant digest`.
5. Morning agent (Mac, logged-in GUI session): `scripts/macos-install-daily-agent.sh`.

## Dev Container

Canonical config: `.devcontainer/devcontainer.json`.

Personal Python Dev Container standard (image, pip cache, ssh-agent): see `~/projects/dev-kb/python-devcontainer.md` when creating or changing the container — do not fork a different Python image without asking.

### What this repo uses

- Image: `Dockerfile`, from `mcr.microsoft.com/devcontainers/python:3.12-bookworm`. It installs `requirements.txt`. `postCreateCommand` still installs this package editable from the mounted workspace.
- `TZ`: `Asia/Ho_Chi_Minh` (logs / local scheduling; Gmail API queries usually use relative/`newer_than` or UTC)
- Pip cache: named volume → `/home/vscode/.cache/pip` (pip default; no `PIP_CACHE_DIR`)
- `postCreateCommand`: `chown` that cache path, then `pip install -r requirements.txt` and `pip install -e .`
- Git: host ssh-agent (`SSH_AUTH_SOCK` → `/ssh-agent`)
- Extensions: `ms-python.python`, `ms-python.vscode-pylance`
- `remoteUser`: `vscode`

Opening the Dev Container is an explicit go-ahead for that `postCreate` install only. Do not otherwise `pip`/`uv`/`npm` install until the user says **ok** / **go ahead**.

### Not in the Dev Container by default

- GitHub CLI / `GH_TOKEN`
- Claude Code mounts/features
- Compose
- Extra formatters/linters unless asked

### Host vs container (auth)

macOS **Keychain** is the only durable store for the OAuth client secret and each mailbox token. Keychain reads and writes stay on the Mac. Mail commands do not call Google's token endpoint.

`scripts/macos-access-token.sh` is the host script. It refreshes a mailbox access token when the stored expiry is missing or already inside the 3 minute 45 second window, then hands off `access_token` and `expiry` only.

- **Open Dev Container.** `inject <container>` writes one file per alias at `/dev/shm/emails-assistant/access-<alias>.json` (mode `0600`, owner `vscode`) via `docker exec -i -u vscode`. `smoke`, `digest`, `search`, and `show` read those files. They do not refresh.
- **One-shot.** `one-shot` prints one JSON object per mailbox on stdout and does not read or write the Dev Container tmpfs. Keep that stdout in memory. Do not write it to the day file, the repo, shell history, or logs.
- **Login.** `login <alias>` is the only way to store a new refresh token. It uses the morning image `emails-assistant:daily` (built when missing or when `requirements.txt` changed) and starts one container with `docker run --rm`. The consent port is published on `127.0.0.1`; the owner does not pass a container name or forward a port. The client secret is piped to that container on stdin for the run. The Mac opens the system browser. Google redirects to the published port. The mailbox token comes back on container stdout and is stored in Keychain unchanged. The command does not print the token. The container then exits and keeps neither the secret nor the token. If the browser cannot be opened, the authorization URL is printed and the command still waits. If consent is denied or the wait ends, the command fails with `Login did not complete.` and the previous token for that alias stays.

If an access token is missing, expired, or rejected, the mail command stops with `Access token missing or rejected. Run the host script again.` It does not restart the container. If Google rejects the refresh token, the host script prints `Login is required for <alias>. The refresh token was rejected.` on stderr and does not print a token.

`.creds/client.json` and `.creds/token-*.json` must be gone. The host script removes them and exits non-zero if any remain. Do not recreate that directory for mail or login.

### Daily file on the Mac

`scripts/macos-daily.sh` is a per-user LaunchAgent. `StartCalendarInterval` is 08:00 local time, and `RunAtLoad` covers a login after that. The agent does not wake the Mac. Before 08:00 the script exits with no file and no banner. After 08:00 it retries every 15 minutes until today's file exists or the local calendar day ends.

Each try calls `one-shot` only when Docker is running. That stdout stays in memory and is piped to `docker run --rm -i -u vscode` of the image below. The repo is mounted at `/workspaces/emails-assistant`. The day file is `digests/` on that mount. The Mac timezone comes from `/etc/localtime`. The container imports the mounted package. The script does not attach to the open Dev Container and does not pip install.

The banner is `osascript` `display notification`. A success shows only the count. A failure shows `Daily digest did not run.` once per failure streak. The notification does not open the file.

On the Mac, in a logged-in GUI session, install the agent. The script builds `emails-assistant:daily`, copies the plist into `~/Library/LaunchAgents/`, substitutes this repo for `REPLACE_WITH_REPO`, and bootstraps it. Run it again after the clone moves.

```bash
scripts/macos-install-daily-agent.sh
```

The 08:00 run builds that image only when it is missing or `requirements.txt` has changed. Other mornings do not rebuild it.

Day files land in `digests/` in the repo. That directory is gitignored. `EMAILS_ASSISTANT_DAILY_DIR` still overrides the directory.

The same repo mount includes gitignored `keys/`. One service-account JSON in that directory is how the morning container calls Gemini. The host does not mint that token. The private key stays out of git.

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
| `emails-assistant daily` | Read both mailboxes from stdin JSON lines, write today's file, print the count |

On the Mac (`scripts/macos-access-token.sh`):

| Command | What it does |
|---------|----------------|
| `inject <container>` | Refresh due tokens and write access tokens into the container |
| `one-shot` | Refresh due tokens and print one access-token JSON object per mailbox |
| `login <alias>` | Open the system browser, take consent in a one-shot container, store the mailbox token |

`scripts/macos-install-daily-agent.sh` installs the 08:00 LaunchAgent. Schedule, retries, and the Docker image are in the Daily file section above.

Interactive mail stays on stdout. The morning run writes the day file and shows a count notification. Telegram is still open; do not add a send channel until that is decided.

## Env

Copy `.env.example` → `.env` and fill local-only values. Knobs are documented in `.env.example`.
