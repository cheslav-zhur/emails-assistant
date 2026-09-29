FROM mcr.microsoft.com/devcontainers/python:3.12-bookworm

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

WORKDIR /workspaces/emails-assistant
