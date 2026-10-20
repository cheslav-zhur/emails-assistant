# AGENTS.md

## Language

- Talk to the user in **Russian** (ты).
- Repo docs (`README.md`, this file, `docs/`) stay in **English**.

## Project

**emails-assistant** — personal helper for Gmail (multiple accounts).

**Phase 1:** readonly mail from two mailboxes (`email1`, `email2`). Interactive commands print plain text. The morning run writes one local day file.  
**Delivery:** stdout for `digest` / `search` / `show`; day file + a count notification for the 08:00 LaunchAgent. Telegram is still open.  
**Later (maybe):** triage, draft replies, MCP for chat agents.

## Stack (do not change without asking)

| Piece | Choice |
|-------|--------|
| Language | Python 3.12+ |
| Mail access | Gmail API + OAuth |
| Scope | Mail: `https://www.googleapis.com/auth/gmail.readonly`. Gemini service account: `https://www.googleapis.com/auth/cloud-platform` |
| Credential store | Mailbox OAuth in macOS Keychain (no biometrics). Gemini service account: one JSON in gitignored `keys/`, for now |
| Account aliases | `email1`, `email2` (real addresses only in local `.env` / Keychain) |
| Deps | pinned in `pyproject.toml` |
| Runtime | Dev Container for interactive use; LaunchAgent runs `docker run --rm` for the morning file |

**Do not introduce** without explicit ask: IMAP/App Passwords, Apple Mail as a mail client, `gws`, more plaintext credential files, new frameworks, DB. The Gemini service account in `keys/` is the current exception. The LaunchAgent banner already uses `osascript` for a notification; do not grow that into a mail path.

## Sources of truth

- Product — [`README.md`](README.md); stack — this file
- Dev environment / Dev Container — [`docs/dev.md`](docs/dev.md)
- Durable rationale — `docs/solutions/`
- Env knobs — `.env.example`
- Dep versions — `pyproject.toml`

Structure below is **canonical**; don’t duplicate long trees in other docs.

```
src/emails_assistant/     # application package
src/host/                 # Mac host: Keychain, inject, LaunchAgent
pyproject.toml
.devcontainer/            # see docs/dev.md
Dockerfile                # `app` and `login` image targets
docs/dev.md
docs/solutions/
```

## Security

- Never commit real email addresses, OAuth tokens, `.env`, or real mail bodies/fixtures
- Credentials: mailbox OAuth in macOS Keychain on the **host** (no biometrics). The Gemini service account is the one JSON in gitignored `keys/`; the morning container mounts that directory read-only when it exists. Linux container gets an ephemeral Gmail token inject only
- Scope: mailbox OAuth stays `https://www.googleapis.com/auth/gmail.readonly`. The Gemini service account requests `https://www.googleapis.com/auth/cloud-platform`. Do not add further scopes unless explicitly expanded
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

Readonly CLI (`smoke`, `digest`, `search`, `show`, `daily`) and the Mac morning day file are in place. A new refresh token comes from `src/host/macos-access-token.sh login <alias>` on the Mac; that command runs consent in a one-shot container. Host scripts live in `src/host/`; behavior is in [`docs/dev.md`](docs/dev.md).  
**Still open:** Telegram (or any other send channel), triage, draft replies.
