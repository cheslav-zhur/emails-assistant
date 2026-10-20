# Backlog

What is not done. A plan keeps the decision. This file only lists the leftovers.

Finished work stays in git. Do not copy it back here from an old plan.

## Product

- **Send channel.** Telegram or something else. Not chosen. The digest still writes a local file and a count notification. `docs/plans/2026-09-28-002-feat-local-morning-digest-plan.md` cites `docs/plans/2026-09-26-telegram-digest-send.md`, and that note is not in the repo.
- **Triage.** Not started. `AGENTS.md`.
- **Draft replies.** Not started. `STRATEGY.md` says not now.

## Debt

- **`HOST_PY` is still inside** `src/host/access-token/access-token.sh`. Refresh and `inject` stay on curl. `docs/plans/2026-10-17-feat-mac-login-plan.md`.
- **Keychain write shows the secret in `ps`.** `security add-generic-password -w` takes the mailbox JSON as an argument. `docs/solutions/security-decisions/2026-10-17-host-script-review-before-merge.md`.

## Decide later

- **Publish the Google OAuth client.** A Testing client drops the refresh token about every seven days. Login on the Mac is the recovery. `docs/plans/2026-10-17-feat-mac-login-plan.md`.
- **Gemini key in `keys/`.** One gitignored service-account JSON, mounted read-only into the morning container. Kept for now instead of a Keychain item `gemini-caller` or a bearer minted on the Mac. `AGENTS.md`, `docs/plans/2026-09-28-003-feat-mail-summary-plan.md`.
- **Mac checks for launchd, Docker, and the banner.** `docs/plans/2026-09-28-002-feat-local-morning-digest-plan.md`.
- **Old Application Support digests.** The day file now lives in `digests/`. No import of the old files. `docs/plans/2026-09-28-003-feat-mail-summary-plan.md`.

## Closed

Do not pick these up from an older plan.

- Login no longer runs in the open Dev Container. `docs/plans/2026-10-17-feat-mac-login-plan.md`.
- App and login are separate images. `docs/plans/2026-10-19-split-images-note.md`.
- The morning container mounts the mail package read-only. It does not mount the whole repo.
