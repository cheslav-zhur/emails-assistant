FROM mcr.microsoft.com/devcontainers/python:3.12-bookworm AS source

COPY --from=ghcr.io/astral-sh/uv:0.13.3 /uv /uvx /bin/

WORKDIR /workspaces/emails-assistant
ENV UV_PROJECT_ENVIRONMENT=/usr/local \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

FROM source AS login
RUN UV_NO_CACHE=1 uv sync --frozen --no-dev --extra login --no-editable --inexact

FROM source AS app
RUN UV_NO_CACHE=1 uv sync --frozen --no-dev --extra app --no-editable --inexact

FROM app AS dev
USER root
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends shellcheck \
    && rm -rf /var/lib/apt/lists/*
USER vscode
