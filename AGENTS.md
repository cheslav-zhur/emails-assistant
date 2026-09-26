# AGENTS.md

## Language

- Talk to the user in **Russian** (ты).
- Repo docs (`README.md`, this file, `docs/`) stay in **English**.

## Project

**emails-assistant** — personal helper for Gmail (multiple accounts).

**Phase 1:** readonly digest (e.g. last 12h) from two mailboxes (`email1`, `email2`).  
**Delivery:** undecided (plain text first; Telegram possible later).  
**Later (maybe):** triage, draft replies, cron in container, MCP for chat agents.

## Stack (do not change without asking)

| Piece | Choice |
|-------|--------|
| Language | Python 3.12+ |
| Mail access | Gmail API + OAuth |
| Scope | `https://www.googleapis.com/auth/gmail.readonly` |
| Credential store | macOS Keychain (no biometrics; no project token files) |
| Account aliases | `email1`, `email2` (real addresses only in local `.env` / Keychain) |
| Deps | pinned in `requirements.txt` / `pyproject.toml` |
| Runtime | Dev Container first; cron / `docker run --rm` later |

**Do not introduce** without explicit ask: IMAP/App Passwords, Apple Mail/osascript, `gws`, plaintext project token files, new frameworks, DB.

## Sources of truth

- Product/stack — this file + `README.md`
- Dev environment / Dev Container — [`docs/dev.md`](docs/dev.md)
- Durable rationale — `docs/solutions/`
- Env knobs — `.env.example`
- Dep versions — `requirements.txt` (keep in sync with `pyproject.toml`)

Structure below is **canonical**; don’t duplicate long trees in other docs.

```
src/emails_assistant/     # application package
requirements.txt
pyproject.toml
.devcontainer/            # see docs/dev.md
docs/dev.md
docs/solutions/
```

## Security

- Never commit real email addresses, OAuth tokens, `.env`, or real mail bodies/fixtures
- Credentials: macOS Keychain on the **host** (no biometrics); Linux container gets ephemeral inject only
- Scope: read mail only unless explicitly expanded
- Do not `pip`/`uv`/`npm` install until the user says **ok** / **go ahead** (opening Dev Container is an explicit go for `postCreate` only — details in `docs/dev.md`)
- Prefer offline; network for package managers / Google APIs only when needed
- Do not push personal mail content to public remotes or unrelated external APIs

## Workflow for agents

1. **Step by step** — one clear step per turn when building; don’t scaffold the whole app unprompted
2. Small diffs; match existing layout
3. Functions over classes; `dataclasses` for data; type hints on public APIs; `logging` not `print`
4. Propose improvements briefly; don’t implement large refactors without agreement
5. No extra markdown/docs unless asked
6. Keep the public git tree free of personal identifiers (use `email1` / `email2`)

## Current status

Scaffold + stack / credential-store / account-alias decisions documented.  
**Next (human-driven):** Google Cloud OAuth client → Keychain tokens for `email1` / `email2` → digest CLI.
