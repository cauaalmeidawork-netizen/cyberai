# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_COMPILE_BYTECODE=1

WORKDIR /app

# Install build deps and uv.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5.18 /uv /uvx /bin/

FROM base AS builder

COPY pyproject.toml /app/
RUN uv sync --no-install-project --no-dev

FROM base AS runtime

COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY alembic.ini migrations pyproject.toml /app/
COPY src /app/src

EXPOSE 8000

CMD ["uvicorn", "cyberai.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
