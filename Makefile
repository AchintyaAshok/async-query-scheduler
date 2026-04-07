.PHONY: dev db db-kill run test lint format check sync migrate migrate-create seed docker-build docker-run compose-up compose-down compose-logs smoke-test snowflake-test

db:
	@docker compose up -d postgres
	@echo "Waiting for Postgres..."
	@until docker compose exec postgres pg_isready -U postgres > /dev/null 2>&1; do sleep 1; done
	@echo "Postgres ready."

db-kill:
	@docker ps -q --filter "publish=5432" | xargs -r docker stop | xargs -r docker rm
	@echo "Killed containers on port 5432."

dev: db
	uv sync
	uv run uvicorn query_scheduler.app:app --reload --host 0.0.0.0 --port 8000

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

smoke-test: db
	uv run python scripts/smoke_test.py run

snowflake-test:
	uv run python scripts/snowflake_test.py status
	uv run python scripts/snowflake_test.py tables
