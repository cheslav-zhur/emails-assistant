# Refactoring the host shell scripts

Not a decision. Read this before rewriting `src/host/` in Python. The app container stays as it is: an access token and an expiry only.

## Where the lines are

`src/host/access-token/access-token.sh` is 481 lines. About 150 are a Python heredoc, and about 100 call that heredoc through NUL-separated commands (`needs-refresh`, `form-body`, `merge-plan`, and four more). Bash does that so it can run `curl` and `security` between the steps. About 45 lines are test stubs for `security`, `docker`, and `curl`. Login's `docker run` argument list is about 40 lines.

`src/host/daily/daily.sh` is 223 lines. Much of that is the same kind of test stub, plus the morning `docker run` mounts. The 08:00 retry loop is short. `src/host/install-daily-agent/install-daily-agent.sh` is 39 lines. The shell tests are 457, 353, and 56 lines.

Login already runs in `emails-assistant:login` (`python3 -m login`). The host passes the OAuth client JSON on stdin, opens the browser, and stores the mailbox token in Keychain. Refresh for `inject` and `one-shot` still runs on the host, which is why the heredoc exists. `one-shot` asks for `gmail.readonly` only and does not write that access token back over the stored mailbox token. `inject` uses the app scopes and does write back, then `docker exec`s `access_token` and `expiry` into the running app container.

`google-auth` is already a direct dependency. The login image also installs `google-auth-oauthlib`. The host script does not import either. It repeats the expiry check in the heredoc. `requests`, `keyring`, and a Docker SDK each remove a few calls. They do not remove the token rules, the test stubs, or the mount list.

## Python on the Mac

A standing host Python is possible, and it is not the interpreter in the image. `launchd` starts with `PATH=/usr/bin:/bin:/usr/sbin:/sbin` and needs an absolute `ProgramArguments` path. `/usr/bin/python3` is the Command Line Tools interpreter, not the container's 3.12.

If that install is accepted, `access-token.sh` becomes one Python program of about 300 lines: the heredoc and the NUL protocol go away, Keychain and `docker run` stay. `daily.sh` falls to about 150 lines, mostly by collapsing the stubs. The installer does not shrink. The plans of 2026-09-28 kept the host as a shell script so the Mac would not gain a package.

## What follows from a thinner host

The lines the refactor actually removes are the refresh protocol. They leave the shell if the host passes the OAuth client JSON and the mailbox token into the login container, and that container performs consent and refresh. The app container still receives only `access_token` and `expiry`. `daily.sh` still takes one-shot stdout and starts the app image.

That deletes the heredoc and the seven host commands, about 250 lines of `access-token.sh`. `src/login/` gains a shorter refresh path on `google-auth`. The host still reads and writes Keychain, still builds `docker run`, and still `docker exec`s the access payload into the app container. A refresh call needs `client_id` and `client_secret` as well as the refresh token.

The morning job would start the login image. Today that image is built for `login`, and one-shot reaches Google with host `curl`. The one-shot rule stays: readonly scope, and do not store that access token in place of the mailbox token.

Putting refresh in the app container is a different change. The mail process would see the client secret and the refresh token on every `inject` and every morning run. That is the boundary the handoff plan refused. It is not required for the shell refactor.

## Still open

- Whether to refactor the host scripts at all.
- Whether a host Python install is acceptable.
- Whether the morning path may start `emails-assistant:login`, which is the cut that removes the heredoc.
- The Keychain write still passes the mailbox JSON to `security add-generic-password -w`. A later `ctypes` write is already described in `docs/solutions/security-decisions/2026-10-17-host-script-review-before-merge.md`. The refactor does not fix that.
