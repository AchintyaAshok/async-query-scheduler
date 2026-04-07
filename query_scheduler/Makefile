.PHONY: run test lint format check sync migrate migrate-create seed docker-build docker-run compose-up compose-down compose-logs smoke-test snowflake-test

run:
	uv run uvicorn query_scheduler.app:app --reload --host 0.0.0.0 --port 8000

test:
	uv run pytest -v -s

lint:
	uv run ruff check .

format:
	uv run ruff format .

check: format lint test

sync:
	uv sync

migrate:
	uv run alembic upgrade head

migrate-create:
	@read -p "Migration message: " msg; \
	uv run alembic revision --autogenerate -m "$$msg"

seed:
	uv run python -m query_scheduler.seed

docker-build:
	docker build -t query_scheduler .

docker-run:
	docker run --rm -p 8000:8000 --env-file .env query_scheduler

compose-up:
	docker compose up -d

compose-down:
	docker compose down

compose-logs:
	docker compose logs -f

smoke-test:
	uv run python scripts/smoke_test.py run

snowflake-test:
	uv run python scripts/snowflake_test.py status
	uv run python scripts/snowflake_test.py tables
