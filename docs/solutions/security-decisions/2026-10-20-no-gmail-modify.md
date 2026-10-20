---
title: "Do not grant gmail.modify"
date: 2026-10-20
last_updated: 2026-10-20
category: security-decisions
module: mail-access
problem_type: security_review
component: tooling
severity: high
applies_when:
  - "Tempted to add gmail.modify so the agent can mark mail read, label existing messages, or archive them"
  - "Tempted to add gmail.send, gmail.compose, or https://mail.google.com/"
  - "Changing GMAIL_APP_SCOPES in src/shared.py"
tags:
  - gmail-api
  - oauth
  - gmail-modify
  - prompt-injection
  - scopes
---

# Do not grant gmail.modify

## Context

On 2026-10-20 the App scopes grew past read-only so login and `inject` could create labels and filters. `gmail.modify` was the scope that would also change labels on mail already in the mailbox, including removing `UNREAD`.

The agent reads message text and holds the same access token it would use to act. A message can contain instructions. With `gmail.modify` the agent can call `users.messages.send`, then move the sent copy to trash with `users.messages.modify`. Google's scope text says `gmail.modify` does not permanently delete mail, bypassing trash. The sent copy still leaves Sent and sits in trash.

## Guidance

`GMAIL_APP_SCOPES` in `src/shared.py` stays:

- `https://www.googleapis.com/auth/gmail.readonly`
- `https://www.googleapis.com/auth/gmail.labels`
- `https://www.googleapis.com/auth/gmail.settings.basic`

Do not add `gmail.modify`, `gmail.send`, `gmail.compose`, or `https://mail.google.com/`.

The morning `one-shot` stays `gmail.readonly` only and does not write that access token back to Keychain.

Label and filter work on mail that is already there happens in the Gmail UI. The owner creates the filter and checks the control that also applies it to matching conversations. `users.settings.filters.create` does not do that pass. A filter can forward only to an address the owner has already verified in Gmail.

There is no Gmail scope that removes `UNREAD` or sets a label on an existing message without also allowing send. `users.messages.modify` accepts `gmail.modify` or `https://mail.google.com/`. A prompt rule does not close this: the token file is in the same container as the agent.

## Why This Matters

- Send and trash are the same grant as mark-read and label-existing.
- The reliable prevention is that the injected token cannot call those methods. Gmail then returns 403.
- Google records API methods, not "this scope was used to send". The Gmail API metrics page often stays empty. The Sent label is not a control, because modify can remove it.

A narrower scope would be a Gmail API feature request, not a vulnerability report. The public tracker component is 191602: `https://issuetracker.google.com/issues/new?component=191602&template=824107`.

## Related

- `src/shared.py` — `GMAIL_APP_SCOPES`
- `docs/dev.md` — login, inject, and one-shot scopes
- `AGENTS.md` — stack table
- `docs/solutions/tooling-decisions/2026-09-25-gmail-api-oauth-readonly-python.md` — original read-only choice
