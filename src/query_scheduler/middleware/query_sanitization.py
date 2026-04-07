"""SQL query sanitization middleware — intercepts POST /queries and validates SQL."""

import json
import re

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from query_scheduler.core.config import settings

logger = structlog.get_logger(__name__)

# Patterns that indicate DDL/DML/DCL — case-insensitive, word-boundary matched
_BLOCKED_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(CREATE|ALTER|DROP|TRUNCATE)\b", re.IGNORECASE),
    re.compile(r"\b(INSERT|UPDATE|DELETE|MERGE)\b", re.IGNORECASE),
    re.compile(r"\b(GRANT|REVOKE)\b", re.IGNORECASE),
    re.compile(r"\b(EXEC|EXECUTE)\b", re.IGNORECASE),
    re.compile(r"\b(CALL)\b", re.IGNORECASE),
]

# Block multiple statements (semicolons not inside quotes)
_MULTI_STATEMENT_PATTERN = re.compile(r";(?=(?:[^'\"]*['\"][^'\"]*['\"])*[^'\"]*$)")


def _reject(reason: str) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": f"SQL rejected: {reason}"},
    )


def sanitize_sql(sql: str) -> str | None:
    """Validate SQL. Returns cleaned SQL on success, or None + logs on failure.

    Raises nothing — callers should check the return value.
    This function is also used directly by the middleware.
    """
    stripped = sql.strip()

    if not stripped:
        return None

    if len(stripped) > settings.max_query_length:
        return None

    statements = _MULTI_STATEMENT_PATTERN.split(stripped)
    non_empty = [s.strip() for s in statements if s.strip()]
    if len(non_empty) > 1:
        return None

    for pattern in _BLOCKED_PATTERNS:
        if pattern.search(stripped):
            return None

    return stripped


class QuerySanitizationMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that validates SQL in POST /queries requests."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Only intercept POST to the queries endpoint
        if request.method != "POST" or not request.url.path.rstrip("/").endswith(
            "/queries"
        ):
            return await call_next(request)

        # Read and parse the body
        body_bytes = await request.body()
        try:
            body = json.loads(body_bytes)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return _reject("invalid request body")

        sql = body.get("sql", "")

        # Validate: empty
        if not sql or not sql.strip():
            return _reject("empty query")

        stripped = sql.strip()

        # Validate: length
        if len(stripped) > settings.max_query_length:
            return _reject(
                f"query exceeds max length ({settings.max_query_length} chars)"
            )

        # Validate: multi-statement
        statements = _MULTI_STATEMENT_PATTERN.split(stripped)
        non_empty = [s.strip() for s in statements if s.strip()]
        if len(non_empty) > 1:
            return _reject("multiple statements not allowed")

        # Validate: blocked patterns
        for pattern in _BLOCKED_PATTERNS:
            match = pattern.search(stripped)
            if match:
                keyword = match.group(1).upper()
                logger.warning(
                    "sql_blocked",
                    keyword=keyword,
                    sql_preview=stripped[:100],
                )
                return _reject(
                    f"'{keyword}' statements are not allowed (read-only queries only)"
                )

        logger.info("sql_sanitized", sql_preview=stripped[:80])
        return await call_next(request)
