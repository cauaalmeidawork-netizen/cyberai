# Development Guide

## Setup

1. Copy `.env.example` to `.env` and adjust values.
2. Make sure Docker Desktop is running (or PostgreSQL + Redis locally).
3. Start the stack:

```bash
docker compose -f infra/compose/docker-compose.yml --profile migrate run --rm migrate
docker compose -f infra/compose/docker-compose.yml up --build
```

## Local backend

```bash
cd services/api
uv sync --all-groups
uv run alembic upgrade head
uv run uvicorn cyberai.main:create_app --factory --reload
```

## Local frontend

```bash
cd apps/web
npm install
npm run dev
```

## Running tests

Backend tests require PostgreSQL and Redis. The easiest way is to use the
services started by Docker Compose:

```bash
cd services/api
uv run pytest
```

Skip integration tests if those services are unavailable:

```bash
uv run pytest -m "not integration"
```

## Code style

- Python: `ruff` for lint/format, `mypy` for type checking.
- TypeScript: `next lint` and `tsc --noEmit`.
- Architecture boundaries are enforced by `import-linter`.

## Useful commands

```bash
make api        # run API locally
make web        # run web dev server
make up         # docker compose up --build
make down       # docker compose down
make test       # backend tests
make lint       # backend lint
make typecheck  # backend type check
make migrate    # run Alembic migrations
```

## Adding a new dependency

```bash
cd services/api
uv add package-name
uv add --dev package-name
```

For the frontend:

```bash
cd apps/web
npm install package-name
```

## Architecture decision records

See [`docs/decisions/`](decisions/).
