# Development Guide

## Setup

1. Make sure Docker Desktop is running.
2. Make sure Ollama is running and `qwen2.5:3b` is installed.
3. Start the local stack:

```bash
powershell -ExecutionPolicy Bypass -File scripts/dev-local.ps1
```

The script creates ignored local env files when missing:

- `services/api/.env`
- `apps/web/.env.local`

Local traffic is intentionally same-origin from the browser:

```text
Browser -> Next.js localhost:3000 -> /api proxy -> FastAPI localhost:8001 -> Ollama localhost:11434
```

Stop only the CyberAI local processes and containers:

```bash
powershell -ExecutionPolicy Bypass -File scripts/stop-local.ps1
```

## Local backend

```bash
cd services/api
uv sync --all-groups
uv run alembic upgrade head
uv run uvicorn cyberai.main:create_app --factory --host 127.0.0.1 --port 8001 --reload
```

## Local frontend

```bash
cd apps/web
npm install
copy .env.example .env.local
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
