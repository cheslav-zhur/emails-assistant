# emails-assistant

Personal Gmail assistant. First goal: readonly digest from multiple accounts. Later: triage, drafts, agent tools.

## Stack (decided)

- **Python 3.12+**
- **Gmail API** + OAuth, scope `gmail.readonly` only
- Libs: `google-api-python-client`, `google-auth`, `google-auth-httplib2`, `google-auth-oauthlib`
- **Credentials:** macOS Keychain (no biometrics) — not project token files
- **Accounts in docs/code:** aliases `email1`, `email2` only
- Run: local / Dev Container → later cron + one-shot `docker run --rm` + optional MCP

Not in scope for v1: Apple Mail/AppleScript, IMAP App Passwords, `gws`, Cursor-only MCP as the main runtime, plaintext project token files.

Phase 1 **delivery** (stdout text vs Telegram, etc.) is still open.

## Status

Readonly digest CLI is in place (`emails-assistant digest` / `login` / `smoke`). Delivery channel still open.

## Quick start

1. Dev environment: **[docs/dev.md](docs/dev.md)** (Dev Container, host vs Keychain).
2. `cp .env.example .env` — put real addresses only in local `.env` (gitignored).
3. Google Cloud OAuth (manual) → Keychain items for `email1` / `email2` (`emails-assistant login …`).
4. `emails-assistant digest` — plain-text digest to stdout.

## Layout

Agent rules: **[AGENTS.md](AGENTS.md)**. Dev details: **[docs/dev.md](docs/dev.md)**.

```
src/emails_assistant/
requirements.txt
pyproject.toml
.devcontainer/
docs/dev.md
docs/solutions/
```

## Security

- No personal addresses or tokens in git; Keychain on the host; scope **read mail only**
- Do not upload mailbox contents to third-party APIs unless explicitly asked
