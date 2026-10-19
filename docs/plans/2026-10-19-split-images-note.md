# Split the app and login images

Draft. Behavior of login and the morning file stays as it is. This note is only how the images are built.

## Images

One `Dockerfile`, two targets, same base `mcr.microsoft.com/devcontainers/python:3.12-bookworm`.

| Target | Tag | Who starts it |
|---|---|---|
| `app` | `emails-assistant:app` | Dev Container and the 08:00 run |
| `login` | `emails-assistant:login` | `scripts/macos-access-token.sh login` |

GitHub CLI and Node stay in `.devcontainer/devcontainer.json`, on the `app` target only. The morning run does not get them.

The old tag `emails-assistant:daily` goes away. `scripts/macos-daily.sh` and the login command use the new tags. The LaunchAgent plist does not name an image.

## Dependencies

Pins live once in `pyproject.toml`. `requirements.txt` is removed.

- Shared, in `dependencies`: `google-auth==2.40.3`
- Extra `app`: `google-api-python-client==2.179.0`, `google-auth-httplib2==0.2.0`
- Extra `login`: `google-auth-oauthlib==1.2.2`
- Extra `dev`: `pytest==9.1.1`, unchanged

The `app` image installs `.[app]`. The `login` image installs `.[login]` and does not install the Gmail client. CI installs `.[app,login,dev]`.

The login process is a module that imports `auth` and `config` only. It must not import `cli` or `gmail_api`. The host starts that module inside `emails-assistant:login`.

## What stays

The repo stays mounted at `/workspaces/emails-assistant`. A Python edit shows up without a rebuild. Rebuild when `pyproject.toml` changes. The image stamp in `scripts/macos-daily.sh` follows that file instead of `requirements.txt`.

`docs/dev.md` changes in the same edit as the tags. Until then it still says `emails-assistant:daily`.

## Not this change

- A `uv` lockfile. Direct pins stay in `pyproject.toml`.
- Splitting `scripts/macos-access-token.sh`, and moving the embedded `HOST_PY` to `scripts/host_refresh.py`.
