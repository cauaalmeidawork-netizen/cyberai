# syntax=docker/dockerfile:1

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.5.18 /uv /uvx /bin/

FROM base AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock README.md /app/
RUN uv sync --frozen --no-install-project --no-dev

COPY src /app/src
RUN uv sync --frozen --no-dev

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN groupadd --system cyberai \
    && useradd --system --gid cyberai --home-dir /app --shell /usr/sbin/nologin cyberai

COPY --from=builder --chown=cyberai:cyberai /app/.venv /app/.venv
COPY --chown=cyberai:cyberai alembic.ini pyproject.toml README.md /app/
COPY --chown=cyberai:cyberai migrations /app/migrations
COPY --chown=cyberai:cyberai src /app/src

USER cyberai

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/health/live', timeout=2).read()"

CMD ["uvicorn", "cyberai.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
