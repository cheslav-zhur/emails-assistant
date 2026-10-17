# emails-assistant

![CI](https://img.shields.io/github/actions/workflow/status/cheslav-zhur/emails-assistant/tests.yml?branch=main&label=CI)
![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white)
![Gmail API](https://img.shields.io/badge/Gmail_API-EA4335?logo=gmail&logoColor=white)
![macOS](https://img.shields.io/badge/macOS-000000?logo=apple&logoColor=white)

Personal emails assistant.

Reads several Gmail accounts.

At 08:00 the Mac writes today's mail to a text file and shows how many messages arrived. You can also print a recent digest, search one account, or open one message.

[dev.md](docs/dev.md) · [AGENTS.md](AGENTS.md) · [solutions](docs/solutions/) · [plans](docs/plans/)

Logins stay in the Mac Keychain. Real addresses stay in a local `.env`, not in git.
