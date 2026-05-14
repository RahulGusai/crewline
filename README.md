# Crewline

Crewline is a backend service for coordinating autonomous engineering agents,
human product owners, and the tickets they work on together.

It provides the operational foundation for an agentic software delivery system:
ticket lifecycle management, agent assignment, audit history, mailbox-style
communication, artifact and attachment handling, authentication, GitHub
integration hooks, and runtime logs. The service is built with FastAPI,
SQLAlchemy, Alembic, and Postgres.

## Status

Crewline currently contains the backend foundation and API surface for the
agent coordination platform. It includes core ticket, messaging, auth, storage,
audit, metrics, and GitHub integration capabilities.

## What Crewline Does

- Tracks engineering tickets through an agent-friendly workflow.
- Maintains a state machine and audit log for ticket transitions.
- Registers agents and supports assignment, unassignment, and review requests.
- Provides a mailbox/RPC substrate so humans, agents, and the system can
  exchange task-related messages.
- Stores ticket attachments and artifacts through S3-compatible storage.
- Exposes authentication, authorization, session, and CSRF protections.
- Integrates with GitHub App installation and repository metadata flows.
- Publishes an OpenAPI schema for frontend type generation.

## Prerequisites

- Python 3.12
- [uv](https://github.com/astral-sh/uv) for Python package management
- Docker + Docker Compose for local Postgres

## Setup

```bash
# 1. Install dependencies
make install

# 2. Copy env example
cp .env.example .env

# 3. Bring everything up (starts Postgres, runs migrations, runs uvicorn)
make dev
```

The API will be available at `http://localhost:8000`.

- `GET /healthz` - health + DB connectivity check
- `GET /openapi.json` - OpenAPI spec, used by the frontend's type generator
- `GET /docs` - interactive API docs (Swagger UI)

## Common tasks

| Command | Effect |
|---|---|
| `make install` | Install / update Python dependencies via uv |
| `make db-up` | Start Postgres container |
| `make db-down` | Stop Postgres container (data preserved) |
| `make db-reset` | Wipe Postgres volume and re-run migrations |
| `make migrate` | Apply pending Alembic migrations |
| `make dev` | Full dev startup: Postgres + migrate + uvicorn with hot-reload |
| `make lint` | Run ruff |
| `make format` | Format with ruff |
| `make typecheck` | Run mypy |
| `make check` | lint + typecheck |

## Frontend type generation

The frontend (separate repo) generates TypeScript types from this service's
OpenAPI spec. With the dev server running locally, the frontend runs:

```bash
npx openapi-typescript http://localhost:8000/openapi.json -o src/api/schema.ts
```

When changing Pydantic schemas in this repo, the frontend must regenerate
its types.

## Adding a migration

```bash
uv run alembic revision -m "description of change"
# Edit the generated file in alembic/versions/
make migrate
```
