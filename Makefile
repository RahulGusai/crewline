.PHONY: install db-up db-down db-reset migrate dev shell lint format typecheck test test-integration check

install:
	uv sync

db-up:
	docker compose up -d postgres
	@echo "Waiting for Postgres to be ready..."
	@until docker compose exec -T postgres pg_isready -U crewline -d crewline > /dev/null 2>&1; do \
		sleep 1; \
	done
	@echo "Postgres is ready."

db-down:
	docker compose down

db-reset:
	docker compose down -v
	$(MAKE) db-up
	$(MAKE) migrate

migrate:
	uv run alembic upgrade head

dev: db-up migrate
	uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

shell:
	uv run python

lint:
	uv run ruff check .

format:
	uv run ruff format .

typecheck:
	uv run mypy app

test:
	uv run pytest

test-integration:
	./scripts/test-setup.sh
	DATABASE_URL=postgresql+asyncpg://crewline:crewline@localhost:5432/crewline_test \
	STORAGE_BUCKET=crewline-test-attachments \
	PM_INITIAL_PASSWORD=test_pm_password \
	AGENT_BE_INITIAL_KEY=test_be_key \
	AGENT_FE_INITIAL_KEY=test_fe_key \
	AGENT_ARCHITECT_INITIAL_KEY=test_architect_key \
	AGENT_QA_INITIAL_KEY=test_qa_key \
	GITHUB_APP_ID=12345 \
	GITHUB_APP_CLIENT_ID=github-client-id \
	GITHUB_APP_CLIENT_SECRET=github-client-secret \
	GITHUB_APP_PRIVATE_KEY=test-private-key \
	COOKIE_SECURE=false \
	COOKIE_SAMESITE=lax \
	uv run pytest tests/integration/ -v --tb=short

check: lint typecheck test
