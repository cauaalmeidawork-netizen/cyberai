.PHONY: help api web up down test lint typecheck migrate

help:
	@echo "CYBER AI - available commands:"
	@echo "  make api        - run the API locally with uv"
	@echo "  make web        - run the Next.js dev server"
	@echo "  make up         - start Docker Compose"
	@echo "  make down       - stop Docker Compose"
	@echo "  make test       - run backend tests"
	@echo "  make lint       - run backend linting"
	@echo "  make typecheck  - run backend type checks"
	@echo "  make migrate    - run Alembic migrations"

api:
	cd services/api && uv run uvicorn cyberai.main:create_app --factory --reload

web:
	cd apps/web && npm run dev

up:
	cd infra/compose && docker compose up --build

down:
	cd infra/compose && docker compose down

test:
	cd services/api && uv run pytest

lint:
	cd services/api && uv run ruff check . && uv run ruff format --check .

typecheck:
	cd services/api && uv run mypy src tests

migrate:
	cd services/api && uv run alembic upgrade head
