# CYBER AI

CYBER AI is a cybersecurity-focused conversational AI platform, designed as a
modular monolith that can evolve into a multi-tenant SaaS. This repository
contains the first milestone (M0): a runnable foundation.

## Quick start

```bash
# 1. Clone and enter the repository
cd cyberai

# 2. Copy the example environment file and adjust if needed
cp .env.example .env

# 3. Start the full stack with Docker Compose
cd infra/compose && docker compose up --build
```

After startup:

- Web UI: http://localhost:3000
- API: http://localhost:8000
- API docs (local only): http://localhost:8000/docs

## Development without Docker

### Backend

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
cd services/api
uv sync --all-groups
uv run alembic upgrade head
uv run uvicorn cyberai.main:create_app --factory --reload
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
- [`docs/decisions/`](docs/decisions/) - architecture decision records

## Repository layout

```text
cyberai/
├── apps/web              # Next.js frontend
├── services/api          # FastAPI backend (modular monolith)
│   ├── src/cyberai/
│   │   ├── core          # config, errors, logging, ids, context
│   │   ├── platform      # db, cache adapters
│   │   ├── modules       # domain modules (inference, modelgw, ...)
│   │   └── api           # HTTP layer
│   ├── migrations        # Alembic migrations
│   └── tests
├── infra                 # Docker, Compose, CI
└── docs                  # Documentation and ADRs
```

## License

Proprietary - all rights reserved.
