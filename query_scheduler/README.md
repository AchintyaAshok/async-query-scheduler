# query_scheduler

A REST API built with [FastAPI](https://fastapi.tiangolo.com/), [SQLModel](https://sqlmodel.tiangolo.com/), and [Alembic](https://alembic.sqlalchemy.org/) for database migrations. Includes structured logging via [structlog](https://www.structlog.org/), optional [OpenTelemetry](https://opentelemetry.io/) observability, and Docker support.

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Framework | FastAPI |
| ORM | SQLModel (SQLAlchemy + Pydantic) |
| Migrations | Alembic |
| Database | PostgreSQL (asyncpg) |
| Config | pydantic-settings |
| Logging | structlog (JSON + console) |
| Observability | OpenTelemetry (optional) |
| Server | Uvicorn |
| Package Manager | uv |
| Linter/Formatter | Ruff |
| Tests | pytest + httpx |

## Getting Started

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- PostgreSQL (or use Docker)

### Local Setup

```bash
# Install dependencies
uv sync

# Copy environment config
cp .env.example .env

# Start Postgres (via Docker)
docker compose up -d postgres

# Run database migrations
make migrate

# Start the dev server
make run
```

The API will be available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### Docker Setup

```bash
# Start everything (app + Postgres)
make compose-up

# View logs
make compose-logs

# Shut down
make compose-down
```

### With Observability Stack

```bash
# Start app + Postgres + OTel Collector + Tempo + Prometheus + Grafana
docker compose --profile otel up -d

# Set OTEL_ENABLED=true in .env
# Grafana: http://localhost:3000 (admin/admin)
# Prometheus: http://localhost:9090
```

## Project Layout

```
src/query_scheduler/
├── app.py              # FastAPI app, lifespan hooks
├── models.py           # SQLModel database models
├── schemas.py          # Pydantic request/response schemas
├── core/
│   ├── config.py       # Pydantic BaseSettings (all env vars)
│   ├── database.py     # Async engine, session management
│   ├── logging.py      # structlog configuration
│   └── telemetry.py    # OpenTelemetry bootstrap
└── routes/
    ├── __init__.py     # Router aggregation
    └── health.py       # /health and /ready endpoints
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for system diagrams.

## Environment Variables

All configuration is managed through environment variables via `pydantic-settings`. See `.env.example` for defaults.

### Application

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | `query_scheduler` | Application name used in logs and metadata |
| `APP_ENV` | `development` | Environment: `development`, `staging`, `production` |
| `APP_DEBUG` | `false` | Enable debug mode (SQL echo, detailed errors) |

### Server

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_HOST` | `0.0.0.0` | Uvicorn bind host |
| `APP_PORT` | `8000` | Uvicorn bind port |
| `APP_WORKERS` | `1` | Number of Uvicorn workers |
| `APP_RELOAD` | `true` | Enable hot reload (dev only) |

### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/query_scheduler` | Async database connection string |

### Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `LOG_FORMAT` | `console` | Output format: `console` (human-readable) or `json` (structured) |

### OpenTelemetry

Requires optional dependencies: `uv sync --extra otel`

| Variable | Default | Description |
|----------|---------|-------------|
| `OTEL_ENABLED` | `false` | Enable OpenTelemetry tracing |
| `OTEL_SERVICE_NAME` | `query_scheduler` | Service name in traces |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | OTLP collector gRPC endpoint |
| `OTEL_TRACES_SAMPLER` | `parentbased_always_on` | Trace sampling strategy |
| `OTEL_TRACES_SAMPLER_ARG` | — | Sampler argument (e.g., `0.1` for 10% sampling) |

## Common Tasks

```bash
make run              # Start dev server with hot reload
make test             # Run test suite
make check            # Format + lint + test
make migrate          # Apply pending migrations
make migrate-create   # Generate a new migration from model changes
make compose-up       # Start all services via Docker
```

## Adding a New Endpoint

1. Create `src/query_scheduler/routes/your_route.py` with a `router = APIRouter()`
2. Add endpoints using `@router.get()`, `@router.post()`, etc.
3. Include the router in `src/query_scheduler/routes/__init__.py`
4. Add models in `models.py` and schemas in `schemas.py` as needed
5. Write tests in `tests/test_your_route.py`
6. Run `make check`

## Contributing

See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for development setup, branch conventions, and coding standards.
