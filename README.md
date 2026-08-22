# NOMERCY AI

Nomercy AI is a cybersecurity-specialist conversational AI, designed as a
modular monolith that can evolve into a multi-tenant SaaS. This repository
contains the product: a grounded, precise assistant that researches public
sources and answers with citations — inside a single conversation.

## Quick start

```bash
# 1. Clone and enter the repository
cd chatbot

# 2. Ensure Docker and Ollama are running, with qwen2.5:3b installed

# 3. Start the local stack
powershell -ExecutionPolicy Bypass -File scripts/dev-local.ps1
```

After startup:

- Web UI: http://localhost:3000
- API: http://localhost:8001
- API docs (local only): http://localhost:8001/docs
- Liveness: http://localhost:8001/health/live
- Readiness: http://localhost:8001/health/ready

## Development without Docker

### Backend

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
cd services/api
uv sync --all-groups
uv run alembic upgrade head
uv run uvicorn cyberai.main:create_app --factory --host 127.0.0.1 --port 8001 --reload
```

Run tests (requires PostgreSQL + Redis):

```bash
uv run pytest
```

### Frontend

Requires Node.js 24+.

```bash
cd apps/web
npm install
npm run dev
```

## Architecture

The architecture is documented in `docs/`:

- [`docs/architecture.md`](docs/architecture.md) - overall system design
- [`docs/security.md`](docs/security.md) - security controls
- [`docs/development.md`](docs/development.md) - developer workflow
- [`docs/operations.md`](docs/operations.md) - production operations
- [`docs/decisions/`](docs/decisions/) - architecture decision records

## Repository layout

```text
chatbot/
├── apps/web              # Next.js frontend
├── services/api          # FastAPI backend (modular monolith)
│   ├── src/cyberai/
│   │   ├── core          # config, errors, logging, ids, context
│   │   ├── platform      # db, cache adapters
│   │   ├── modules       # domain modules (inference, modelgw, research, ...)
│   │   └── api           # HTTP layer
│   ├── migrations        # Alembic migrations
│   └── tests
├── infra                 # Docker, Compose, CI
└── docs                  # Documentation and ADRs
```

## License

Proprietary - all rights reserved.
