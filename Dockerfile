# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    GRADIO_SERVER_NAME=0.0.0.0 \
    GRADIO_SERVER_PORT=7860 \
    GRADIO_ANALYTICS_ENABLED=False

# System deps:
#   - curl/ca-certs for uv installer
#   - git for any uvx tools that fetch from git
#   - nodejs 20 + npm for the npx-based MCP servers (brave-search, memory-libsql)
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        curl ca-certificates git gnupg \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# Hugging Face Spaces expects uid 1000 and a writable home.
RUN useradd -m -u 1000 -s /bin/bash user
USER user
WORKDIR /home/user/app
ENV HOME=/home/user \
    PATH="/home/user/.local/bin:${PATH}"

# Install uv (Astral) into the user's home.
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Resolve and install Python deps before copying the rest of the app, so
# pyproject + uv.lock changes are the only thing that invalidate this layer.
COPY --chown=user:user pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# App source.
COPY --chown=user:user . .

# memory/ holds per-session libsql files; make sure it's writable.
RUN mkdir -p memory && rm -f accounts.db accounts.db-journal

EXPOSE 7860

CMD ["uv", "run", "--no-dev", "python", "app.py"]
