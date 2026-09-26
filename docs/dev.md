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

macOS **Keychain** is only on the host. OAuth login and Keychain read/write run **on the Mac host**.

The Linux Dev Container is for packaging and non-Keychain work. For a one-shot digest in Docker later: host helper reads Keychain → ephemeral tmpfs → `docker run --rm` with `:ro` mount (container never calls Keychain).

## Accounts (aliases only in git)

Two mailboxes, referred to only as:

- `email1`
- `email2`

Map alias → real address in **local** `.env` (gitignored) or Keychain item attributes — never commit real addresses, tokens, or message fixtures.

## Phase 1 output (open)

Digest delivery is **not finalized**. Likely plain text first; Telegram send is a candidate later. Do not hard-wire a delivery channel until decided.

## Env

Copy `.env.example` → `.env` and fill local-only values. Knobs are documented in `.env.example`.
