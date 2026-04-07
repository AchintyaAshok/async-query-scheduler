# Contributing

## Development Setup

1. **Install prerequisites:** Python 3.12+, [uv](https://docs.astral.sh/uv/), Docker (for Postgres)
2. **Clone and install:**
   ```bash
   uv sync
   cp .env.example .env
   ```
3. **Start Postgres:**
   ```bash
   docker compose up -d postgres
   ```
4. **Run migrations:**
   ```bash
   make migrate
   ```
5. **Verify everything works:**
   ```bash
   make check
   ```

## Development Workflow

1. Create a feature branch from `main`
2. Make your changes
3. Run `make check` (format + lint + test)
4. Commit with conventional commit messages
5. Open a PR

## Code Style

- **Formatter/Linter:** Ruff with rules `E, F, I, N, UP`, line length 88
- **Imports:** Always fully qualified (`from query_scheduler.core.config import settings`), never relative
- **Config:** Use `settings` from `core/config.py`. Never use `os.getenv` directly.
- **Database:** Use `get_session` dependency or `get_repository()` for data access
- **Types:** Use type hints everywhere. Prefer `str | None` over `Optional[str]`

## Adding Features

### New Endpoint
1. Create route file in `src/query_scheduler/routes/`
2. Register router in `routes/__init__.py`
3. Add tests in `tests/`

### New Model
1. Add SQLModel class in `models.py`
2. Add schemas in `schemas.py`
3. Generate migration: `make migrate-create`
4. Apply migration: `make migrate`
5. Add tests

### New Configuration
1. Add field to `Settings` class in `core/config.py`
2. Add to `.env.example` with default and comment
3. Update the env var table in `README.md`

## Testing

```bash
make test         # Run all tests
uv run pytest -k "test_name"  # Run specific test
```

- Tests use `httpx.AsyncClient` with `ASGITransport` (no real server needed)
- Use `pytest-asyncio` for async tests
- Database tests require a running Postgres instance

## Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
type(scope): imperative description

feat(items): add CRUD endpoints for items
fix(auth): handle expired token refresh
docs(readme): update env var table
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `style`, `chore`, `perf`
