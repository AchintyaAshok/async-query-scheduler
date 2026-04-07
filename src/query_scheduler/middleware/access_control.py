"""Access control middleware — env-var-based capability gating for query endpoints."""

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from query_scheduler.core.config import settings

logger = structlog.get_logger(__name__)

# Map (method, path_suffix) to required capability
_CAPABILITY_MAP: dict[tuple[str, str], str] = {
    ("POST", "/queries"): "start_query",
    ("GET", "/queries"): "get_status",
}


def _get_allowed_capabilities() -> set[str]:
    """Parse the comma-separated capabilities from settings."""
    return {
        cap.strip() for cap in settings.allowed_capabilities.split(",") if cap.strip()
    }


class AccessControlMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that gates query endpoints based on env-var capabilities."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path.rstrip("/")
        method = request.method

        # Determine required capability — check exact match first, then prefix
        capability = None
        for (m, suffix), cap in _CAPABILITY_MAP.items():
            if method == m and (path == suffix or path.startswith(suffix)):
                capability = cap
                break

        # No capability required for this endpoint — pass through
        if capability is None:
            return await call_next(request)

        # Global kill switch
        if not settings.query_access_enabled:
            logger.warning("access_denied_disabled", capability=capability)
            return JSONResponse(
                status_code=403,
                content={"detail": "Query access is disabled"},
            )

        # Check capability
        allowed = _get_allowed_capabilities()
        if capability not in allowed:
            logger.warning(
                "access_denied_capability",
                capability=capability,
                allowed=sorted(allowed),
            )
            return JSONResponse(
                status_code=403,
                content={"detail": f"Capability '{capability}' is not enabled"},
            )

        return await call_next(request)
