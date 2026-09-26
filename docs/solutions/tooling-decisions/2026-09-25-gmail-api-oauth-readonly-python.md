---
title: "Adopt Gmail API + OAuth gmail.readonly + Python clients"
date: 2026-09-25
last_updated: 2026-09-25
category: tooling-decisions
module: mail-access
problem_type: tooling_decision
component: tooling
severity: high
applies_when:
  - "Choosing how emails-assistant reads Gmail (multi-account, container/cron later)"
  - "Tempted to switch to IMAP App Passwords, Apple Mail, gws, or Cursor MCP as primary"
  - "Tempted to store OAuth tokens as project secrets/ files"
tags:
  - gmail-api
  - oauth
  - gmail-readonly
  - python
  - keychain
  - stack
---

# Adopt Gmail API + OAuth gmail.readonly + Python clients

## Context

For **emails-assistant** (personal multi-account Gmail helper; phase 1 = readonly digest), we needed one stack that fits Dev Container now and cron/MCP later, with least privilege. Alternatives considered: Apple Mail/AppleScript, IMAP + App Password, Google Workspace CLI (`gws`), Cursor Gmail MCP as the main runtime, and plaintext `secrets/` files.

A project-grounded verdict (**Adopt**, tier 3 privacy) confirmed the API stack. Credential storage was then fixed to **macOS Keychain without biometrics**.

## Guidance

**Use:**

- Gmail API + OAuth Desktop client
- Scope only `https://www.googleapis.com/auth/gmail.readonly`
- Official Python libs: `google-api-python-client`, `google-auth`, `google-auth-httplib2`, `google-auth-oauthlib`
- Store OAuth client + one refresh token per mailbox in **macOS Keychain** (generic password items)
- **No biometrics / user-presence ACL** — launchd can read items for morning cron
- **No project `secrets/` directory** as the store
- Linux `docker run --rm`: host helper reads Keychain → ephemeral tmpfs `:ro` into the container (container does not call Keychain)

**Do not use as the primary path:** IMAP App Passwords, Apple Mail/osascript, `gws`, Cursor-only MCP for scheduled runs, or long-lived token JSON in the repo tree.

Short stack table stays in `AGENTS.md` / `README.md`. This file holds the durable rationale.

## Why This Matters

- Matches Google’s documented personal-Gmail Python path and enables true read-only scope.
- App Passwords are coarse account secrets; `gws` is experimental / unsupported; Apple Mail does not run in a container; IDE MCP is not a cron runtime.
- Keychain avoids plaintext tokens in the project folder; skipping biometrics keeps unattended cron workable.
- Catch: OAuth apps in **Testing** expire refresh tokens about every **7 days** for non-basic scopes — plan re-auth or a personal-use / publishing path.

## When to Apply

- Implementing auth or digest CLI
- Anyone proposes switching mail access or credential storage
- Designing Docker/cron around tokens

## Examples

```text
Cloud project → enable Gmail API → OAuth Desktop client
→ browser consent on Mac host
→ Keychain items under service prefix (e.g. client + token/email1 + token/email2)
→ (optional) host export to tmpfs → docker run --rm … digest
→ messages.list q=newer_than:12h → messages.get (readonly)
```

## Related

- `AGENTS.md` — stack table (source of short truth)
- `docs/dev.md` — Dev Container / host Keychain
- `README.md` — stack decided / v1 non-goals
- Verdict date: 2026-09-25 (ce-pov Adopt); Keychain store: 2026-09-25
- Account aliases: `email1`, `email2` (no real addresses in git)
