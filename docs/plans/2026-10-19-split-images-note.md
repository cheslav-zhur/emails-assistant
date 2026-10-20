# Split the app and login images

Agreed. Behavior of login and the morning file stays as it is. This note is how the images are built.

## Images

One `Dockerfile`, two targets, same base `mcr.microsoft.com/devcontainers/python:3.12-bookworm`.

| Target | Tag | Who starts it |
|---|---|---|
| `app` | `emails-assistant:app` | Dev Container and the digest |
| `login` | `emails-assistant:login` | `src/host/macos-access-token.sh login` |

GitHub CLI and Node stay in `.devcontainer/devcontainer.json`, on the `app` target only. The morning run does not get them.

The old tag `emails-assistant:daily` goes away. `src/host/macos-daily.sh` builds `emails-assistant:app`. The login command builds `emails-assistant:login` and does not build the app image. The LaunchAgent plist does not name an image.

## Dependencies

Pins live once in `pyproject.toml`. `requirements.txt` is removed. This note names the package, not the version.

- In `dependencies`, both images: `google-auth`
- Extra `app`: `google-api-python-client`, `google-auth-httplib2`, `python-dotenv`, `google-genai`
- Extra `login`: `google-auth-oauthlib`
- Extra `dev`: `pytest`

The `app` image installs `.[app]`. The `login` image installs `.[login]` and does not install the Gmail client, `python-dotenv`, or `google-genai`. CI installs `.[app,login,dev]`.

The host starts `python -m login` inside `emails-assistant:login`. That process imports `shared` and does not import `emails_assistant`. The mail process does not import `login`.

## Code on disk

```
src/shared.py
src/emails_assistant/
src/login/
src/host/
```

`src/emails_assistant/` stays the mail package. The terminal command stays `emails-assistant` and points at `emails_assistant.cli:main`. The image target is still `app`; the package is not renamed. `src/login/` is the consent package. `src/shared.py` is one module, not a `shared/` directory. `src/host/` holds the Mac scripts that are in `scripts/` today. There is no `tests/` directory.

A check sits next to the file it covers: `digest.py` and `test_digest.py`, `macos-daily.sh` and `macos-daily.test.sh`. `digest.test.py` is not a module name pytest can import beside `digest.py`. Shell checks stay shell.

## shared.py

Both one-shot containers mount this file and nothing else from the other package. It answers two questions: which aliases exist, and which Gmail scope a token uses.

It keeps:

- the readonly scope string
- `known_aliases()` — the alias list from `EMAILS_ASSISTANT_ACCOUNTS`
- `resolve_alias()` — reject an alias that is not in that list

It does not keep:

- `load_dotenv()` — moves into `src/emails_assistant/`. The dev process reads `.env` through `python-dotenv`, and `$` stays literal. One-shot containers do not mount `.env`; the host passes `EMAILS_ASSISTANT_ACCOUNTS` in the environment.
- `since_hours()` — moves into `src/emails_assistant/`. Only `digest` uses it.

Access-token parsing stays in `emails_assistant`. Consent stays in `login`. The Gemini scope stays in `emails_assistant` with the summary.

## Mounts

The morning container mounts `src/emails_assistant/`, `src/shared.py`, `keys/` read-only, and `digests/` writable. `keys/` is the service-account JSON the summary already reads. `digests/` is the day file and the summary-miss marker. The login container mounts `src/login/` and `src/shared.py`. A `test_*.py` file inside a mounted package comes along and is not run. Login does not mount `src/host/`, `.env`, `keys/`, `digests/`, or the mail package. The morning container does not mount `src/host/`, `.env`, or `src/login/`.

The Dev Container still opens the whole repo. It is the editor.

A Python edit in a mounted file shows up without a rebuild. Rebuild when `pyproject.toml` changes. Each tag keeps its own stamp, and both stamps hash that file. Those stamps follow `pyproject.toml` instead of `requirements.txt`.

`docs/dev.md` and `AGENTS.md` name `emails-assistant:app`, `emails-assistant:login`, and `src/host/`.

## Not this change

- A `uv` lockfile. Direct pins stay in `pyproject.toml`.
- Splitting the Mac token script, and moving the embedded `HOST_PY` to `src/host/host_refresh.py`.
