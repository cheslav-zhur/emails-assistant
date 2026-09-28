# Development environment

Local/dev setup for **emails-assistant**. Product decisions live in `AGENTS.md`; durable stack rationale in `docs/solutions/`.

## Dev Container

Canonical config: `.devcontainer/devcontainer.json`.

Personal Python Dev Container standard (image, pip cache, ssh-agent): see `~/projects/dev-kb/python-devcontainer.md` when creating or changing the container — do not fork a different Python image without asking.

### What this repo uses

- Image: `mcr.microsoft.com/devcontainers/python:3.12-bookworm`
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
- Custom Dockerfile / compose
- Extra formatters/linters unless asked

### Host vs container (auth)

macOS **Keychain** is the only durable store for the OAuth client secret and each mailbox token. Login and every Keychain read/write stay on the Mac. The container never calls Keychain and never calls Google's token endpoint.

`scripts/macos-access-token.sh` is the host script. It refreshes a mailbox access token when the stored expiry is missing or already inside the 3 minute 45 second window, then hands off `access_token` and `expiry` only.

- **Open Dev Container.** `inject <container>` writes one file per alias at `/dev/shm/emails-assistant/access-<alias>.json` (mode `0600`, owner `vscode`) via `docker exec -i -u vscode`. `smoke`, `digest`, `search`, and `show` read those files. They do not refresh.
- **One-shot.** `one-shot` prints one JSON object per mailbox on stdout and does not read or write the Dev Container tmpfs. Keep that stdout in memory. Do not write it to the day file, the repo, shell history, or logs.
- **Login.** `login <container> <alias>` reads the client secret from Keychain and pipes it to the container stdin. The authorization URL is on stderr. The mailbox-token JSON comes back on container stdout and is stored in Keychain unchanged. The container does not keep a credential file.

If an access token is missing, expired, or rejected, the mail command stops with `Access token missing or rejected. Run the host script again.` It does not restart the container. If Google rejects the refresh token, the host script prints `Login is required. The refresh token was rejected.` on stderr and does not print a token.

`.creds/client.json` and `.creds/token-*.json` must be gone. The host script removes them and exits non-zero if any remain. Do not recreate that directory for mail or login.

**Keychain write `ps` check.** Not observed in this session: the Linux Dev Container cannot run `security`. The script passes the mailbox JSON to `security add-generic-password -w`, so that JSON can show in the process list for the length of the write. The refresh body goes to curl on stdin, not as a curl argument. Do not paste a token into this doc when the Mac check is run.

## Accounts (aliases only in git)

Two mailboxes, referred to only as:

- `email1`
- `email2`

Map alias → real address in **local** `.env` (gitignored) or Keychain item attributes — never commit real addresses, tokens, or message fixtures.

## Phase 1 output (open)

Digest delivery is **not finalized**. Likely plain text first; Telegram send is a candidate later. Do not hard-wire a delivery channel until decided.

## Env

Copy `.env.example` → `.env` and fill local-only values. Knobs are documented in `.env.example`.
