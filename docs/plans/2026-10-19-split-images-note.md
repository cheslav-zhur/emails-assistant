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

- In `dependencies`, both images: `google-auth==2.40.3`
- Extra `app`: `google-api-python-client==2.179.0`, `google-auth-httplib2==0.2.0`, `python-dotenv==1.2.4`
- Extra `login`: `google-auth-oauthlib==1.2.2`
- Extra `dev`: `pytest==9.1.1`, unchanged

The `app` image installs `.[app]`. The `login` image installs `.[login]` and does not install the Gmail client or `python-dotenv`. `python-dotenv` is already pinned. CI installs `.[app,login,dev]`.

The host starts `python -m login` inside `emails-assistant:login`. That process imports `shared` and does not import `emails_assistant`. The mail process does not import `login`.

## Code on disk

```
src/shared.py
src/shared.test.py
src/emails_assistant/
src/login/
src/host/
```

`src/emails_assistant/` stays the mail package. The terminal command stays `emails-assistant` and points at `emails_assistant.cli:main`. The image target is still `app`; the package is not renamed. `src/login/` is the consent package. `src/shared.py` is one module, not a `shared/` directory. `src/host/` holds the Mac scripts. There is no `tests/` directory.

A check sits next to the file it covers: `digest.py` and `digest.test.py`, `macos-daily.sh` and `macos-daily.test.sh`. `pyproject.toml` teaches pytest the `*.test.py` pattern. Shell checks stay shell.

## shared.py

Both one-shot containers mount this file and nothing else from the other package. It answers two questions: which aliases exist, and which Gmail scope a token uses.

It keeps:

- the readonly scope string
- `known_aliases()` — the alias list from `EMAILS_ASSISTANT_ACCOUNTS`
- `resolve_alias()` — reject an alias that is not in that list

It does not keep:

- `load_dotenv()` — moves into `src/emails_assistant/`. The dev process reads `.env` through `python-dotenv`. One-shot containers do not mount `.env`; the host passes `EMAILS_ASSISTANT_ACCOUNTS` in the environment.
- `since_hours()` — moves into `src/emails_assistant/`. Only `digest` uses it.

Access-token parsing stays in `emails_assistant`. Consent stays in `login`.

## Mounts

The morning container mounts `src/emails_assistant/` and `src/shared.py`. The login container mounts `src/login/` and `src/shared.py`. A `*.test.py` file inside a mounted package comes along and is not run. `src/host/`, `.env`, and the other package are not mounted.

The Dev Container still opens the whole repo. It is the editor.

A Python edit in a mounted file shows up without a rebuild. Rebuild when `pyproject.toml` changes. The image stamp in `scripts/macos-daily.sh` follows that file instead of `requirements.txt`.

`docs/dev.md` changes in the same edit as the tags. Until then it still says `emails-assistant:daily`.

## Not this change

- A `uv` lockfile. Direct pins stay in `pyproject.toml`.
- Splitting the Mac token script, and moving the embedded `HOST_PY` to `src/host/host_refresh.py`.
