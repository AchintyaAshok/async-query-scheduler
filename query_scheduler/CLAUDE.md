# query_scheduler

REST API built with FastAPI, SQLModel, and Alembic.

## Project structure

```
├── pyproject.toml                    # uv/ruff/pytest config, FastAPI + SQLModel + structlog deps
├── Makefile                          # run, test, lint, format, check, migrate, seed, docker-*, compose-*
├── Dockerfile                        # Multi-stage build, non-root user, health check
├── .env.example                      # All env vars with defaults and comments
├── docker-compose.yml                # Postgres + optional OTel stack (--profile otel)
├── alembic.ini                       # Alembic config pointing to async DB URL
├── alembic/
│   ├── env.py                        # Async migration environment, imports all models
│   ├── script.py.mako                # Migration template
│   └── versions/                     # Auto-generated migration files
├── otel-collector-config.yaml        # OTLP receiver → spanmetrics → Tempo + Prometheus
├── tempo-config.yaml                 # Local trace storage backend
├── prometheus.yml                    # Scrapes OTel Collector metrics
├── grafana/provisioning/             # Auto-provisioned datasources and dashboards
├── .python-version                   # Python 3.12+
├── .gitignore
├── src/query_scheduler/
│   ├── __init__.py
│   ├── app.py                        # FastAPI instance, lifespan (DB + OTel), router wiring
│   ├── models.py                     # SQLModel table models
│   ├── schemas.py                    # Pydantic request/response schemas
│   ├── core/
│   │   ├── config.py                 # Pydantic BaseSettings — all env vars centralized here
│   │   ├── database.py               # Async engine, session dependency, init/close
│   │   ├── logging.py                # structlog setup — JSON or console format
│   │   ├── telemetry.py              # OTel SDK bootstrap, FastAPI auto-instrumentation
│   │   └── storage/
│   │       ├── __init__.py           # Re-exports AbstractRepository, SQLModelRepository, get_repository
│   │       ├── repository.py         # Abstract repository interface
│   │       └── sql_repository.py     # Concrete SQLModel implementation + singleton
│   └── routes/
│       ├── __init__.py               # Router aggregation
│       └── health.py                 # /health (liveness) + /ready (DB connectivity)
├── tests/
│   ├── conftest.py                   # Async fixtures: httpx test client
│   └── test_health.py               # Health endpoint tests
├── docs/
│   ├── ARCHITECTURE.md               # System diagrams (Mermaid): request flow, OTel pipeline, DB
│   └── CONTRIBUTING.md               # Dev setup, branch conventions, coding standards
├── resources/                        # Reference/data files
└── tmp/                              # Scratch folder (gitignored)
```

## Tooling

- **Python 3.12+**, **uv** for deps, **ruff** for formatting/linting, **pytest** for tests.
- Run from this directory: `make check` (format + lint + test).

## Adding routes

1. Create a new file in `src/query_scheduler/routes/` (e.g., `items.py`).
2. Define a `router = APIRouter()` and add your endpoints.
3. Include it in `src/query_scheduler/routes/__init__.py`.
4. Add tests in `tests/`.
5. Run `make check`.

## Adding models

1. Define SQLModel table classes in `src/query_scheduler/models.py`.
2. Create corresponding schemas in `src/query_scheduler/schemas.py`.
3. Run `make migrate-create` to auto-generate an Alembic migration.
4. Run `make migrate` to apply it.

## Configuration

All config is centralized in `src/query_scheduler/core/config.py` using `pydantic-settings`. Import `settings` from `query_scheduler.core.config` — never use `os.getenv` directly (except in `telemetry.py` to avoid import-order coupling).

Copy `.env.example` to `.env` for local dev.

## Module relationships

- **core/config.py** is the leaf dependency — no internal imports, all other modules import from it.
- **core/database.py** creates the async engine and session dependency.
- **core/logging.py** configures structlog with format from settings.
- **core/telemetry.py** reads `OTEL_ENABLED` from `os.environ` directly. Must be called before FastAPI instrumentation.
- **core/storage/repository.py** defines the abstract `AbstractRepository` interface.
- **core/storage/sql_repository.py** implements `SQLModelRepository` and provides `get_repository()` singleton.
- **app.py** creates the FastAPI instance, wires lifespan (DB init + OTel), includes routers.
- **models.py** defines SQLModel tables. **schemas.py** defines API request/response shapes.
- **routes/** contains endpoint modules that use dependencies from `core/`.

## Running

```bash
make run              # uvicorn with reload (development)
make docker-build     # Build Docker image
make docker-run       # Run in Docker
make compose-up       # Postgres + app via docker-compose
```

## Conventions

- Always use fully qualified imports (`from query_scheduler.core.config import settings`), never relative.
- Import `settings` from `query_scheduler.core.config` for all configuration.
- Use `get_repository()` from `core.storage` for data access, or `get_session` dependency for direct DB access.
- Tests use httpx `AsyncClient` with `ASGITransport`.
