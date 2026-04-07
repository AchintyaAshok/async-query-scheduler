FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install dependencies
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --frozen 2>/dev/null || uv sync --no-dev

# Copy application
COPY alembic.ini ./
COPY alembic/ alembic/
COPY src/ src/

# Non-root user
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uv", "run", "uvicorn", "query_scheduler.app:app", "--host", "0.0.0.0", "--port", "8000"]
