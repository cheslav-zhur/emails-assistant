---
title: "Host script review before merging the daily digest"
date: 2026-10-17
last_updated: 2026-10-17
category: security-decisions
module: host-scripts
problem_type: security_review
component: tooling
severity: medium
applies_when:
  - "Merging or changing scripts/macos-daily.sh, scripts/macos-access-token.sh, or the LaunchAgent installer"
  - "Tempted to hide the Keychain password by passing -w last, or via security -i"
  - "Tempted to rewrite the Keychain write before a Mac check"
tags:
  - keychain
  - security-cli
  - launchagent
  - docker
  - host-scripts
---

# Host script review before merging the daily digest

## Context

Reviewed `scripts/macos-daily.sh`, `scripts/macos-access-token.sh`, `scripts/macos-install-daily-agent.sh`, and `scripts/com.emails-assistant.daily.plist` on 2026-10-17, before merging `feat/local-daily-digest`.

Threat model: one person's Mac, Gmail read-only, the container receives an access token only. The same user can already read these Keychain items with no prompt. That is the no-biometrics choice in the tooling decision, so an unattended morning run can read them.

## Guidance

None of the three findings below has to be fixed before that merge.

If one thing is changed, mount the repo read-only in `macos-daily.sh`:

```bash
-v "$ROOT:$CONTAINER_ROOT:ro"
```

The digest writes the day file under `/daily` and the access token under `/dev/shm`. It does not write into the repo tree. A read-only mount stops a container that already holds the access token and has network from rewriting the host scripts.

Do not switch the Keychain write to `ctypes` and `Security.framework` on the way to this merge. The Linux Dev Container cannot run `security`, so the new write cannot be checked here, and a broken write stops the morning run.

Do not XML-escape the repo path in the installed plist for a normal home-directory path. A path with `<`, `&`, or quotes can break the plist or add a second program argument. A path under `$HOME` does not.

## Findings

**Keychain write shows the secret in `ps`.** `macos-access-token.sh` passes the mailbox JSON to `security add-generic-password -w` when it stores a refreshed token and when `login` stores the container stdout. While that command runs, the same user can see the refresh token and client secret in the process list. `docs/dev.md` already records this. It has not been observed on a Mac from this container. `find-generic-password -w` is a different flag: it prints the password to stdout and does not put the secret in argv. Leave those reads as they are.

**Repo bind mount is read-write.** `macos-daily.sh` mounts the repo at `/workspaces/emails-assistant` without `:ro`. The container also gets the access token on stdin and default network. The image is built locally and the process runs as `vscode`. There is no Docker socket mount.

**Plist path is substituted raw.** `macos-install-daily-agent.sh` replaces `REPLACE_WITH_REPO` with the repo path and does not escape XML.

The rest of the scripts match the handoff plan: refresh body and access token go on stdin, the container payload is `access_token` and `expiry` only, a refresh response that contains `refresh_token` is not written, the `osascript` text is limited to letters, digits, spaces, and dots, `docker run` uses `--rm` and `-u vscode`, and leftover `.creds` files are removed by name.

`EMAILS_ASSISTANT_DOCKER`, `EMAILS_ASSISTANT_SECURITY`, `EMAILS_ASSISTANT_CURL`, and the other command overrides exist so tests can stub binaries. The LaunchAgent does not set them. Do not export them into the GUI session with `launchctl setenv`.

## If the Keychain write is fixed later

Apple's own man page says that `-w` with a value is insecure and that `-w` as the last option prompts instead. That prompt calls `getpass`. In Terminal it reads `/dev/tty`, not the pipe. It keeps at most `_PASSWORD_LEN` (128) characters and discards the rest. The mailbox JSON is longer than that, so the prompt would store a truncated token.

`security -i` is also a poor fit. Interactive input is capped (`MAX_LINE_LEN` 4096). Past that, the remainder is treated as another command. Quoting the JSON makes the line longer.

The write that fits this payload is a host Python `ctypes` call into `Security.framework`, with the JSON on stdin, so `ps` shows `python3` and not the secret. No new package. When the item is created, its access list has to include `/usr/bin/security` and `sys.executable`. Otherwise Keychain trusts only the process that created the item, and the morning `security find-generic-password` starts prompting. Check on the Mac with `ps` during a write. Do not paste a token into this doc.

## Related

- `docs/dev.md` — Keychain write `ps` check
- `docs/plans/2026-09-28-001-feat-access-token-handoff-plan.md` — stdin handoff, `-w` called out as visible in `ps`
- `docs/solutions/tooling-decisions/2026-09-25-gmail-api-oauth-readonly-python.md` — Keychain without biometrics
