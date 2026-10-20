# Personal email assistant

![CI](https://img.shields.io/github/actions/workflow/status/cheslav-zhur/emails-assistant/tests.yml?branch=main&label=CI)
![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white)
![Gmail API](https://img.shields.io/badge/Gmail_API-EA4335?logo=gmail&logoColor=white)
![macOS](https://img.shields.io/badge/macOS-000000?logo=apple&logoColor=white)

## What it is

- **assistant for my emails** — help with query, grouping, etc.
- **digest** — daily summary of emails
- **part of my [Personal OS](https://github.com/cheslav-zhur/cheslav-zhur)**

## How it runs

Security matters. Mailbox tokens stay in Keychain, and a container receives only what that run needs.

```mermaid
flowchart LR
  subgraph mac ["Mac"]
    k[Keychain]
  end
  subgraph login ["login container"]
    c[consent]
  end
  subgraph app ["app container"]
    m[mail]
  end
  mac -->|"client secret →<br/>← refresh token"| login
  mac -->|access token| app
  style k fill:transparent,stroke:transparent
  style c fill:transparent,stroke:transparent
  style m fill:transparent,stroke:transparent
```

- **Mac.** Keychain holds the OAuth client secret and one refresh token per mailbox.
- **login container.** One run: browser consent, then the container exits and the refresh token goes back into Keychain.
- **app container.** Mail: search and the daily digest. It receives a short-lived access token only.

## Docs

- [Plans](docs/plans/)
- [Development](docs/dev.md)
