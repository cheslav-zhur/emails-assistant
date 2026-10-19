FROM mcr.microsoft.com/devcontainers/python:3.12-bookworm AS source

WORKDIR /workspaces/emails-assistant
COPY pyproject.toml README.md ./
COPY src ./src

FROM source AS login
RUN pip install --no-cache-dir ".[login]"

FROM source AS app
RUN pip install --no-cache-dir ".[app]"
