"""
Security middleware for J.A.R.V.I.S API.

Provides:
- API key authentication via X-API-Key header (opt-in — disabled when API_KEY is empty)
- Per-IP sliding-window rate limiting (in-memory or SQLite-backed)
"""

import time
from collections import defaultdict

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import get_settings
from app.utils.logger import logger

settings = get_settings()

# ---------------------------------------------------------------------------
# 1. API Key Authentication (FastAPI dependency)
# ---------------------------------------------------------------------------

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str | None = Security(_api_key_header)) -> str | None:
    """
    FastAPI dependency that verifies the X-API-Key header.
    If API_KEY is not configured (empty), authentication is disabled.
    """
    if not settings.api_key:
        return None  # Auth disabled

    if not api_key or api_key != settings.api_key:
        logger.log_warning("Unauthorized API access attempt — invalid or missing API key")
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Provide a valid key via the X-API-Key header.",
        )
    return api_key


# ---------------------------------------------------------------------------
# 2. Rate Limiting Middleware (in-memory sliding window)
# ---------------------------------------------------------------------------

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding-window rate limiter based on client IP address.
    Skips rate limiting for health/docs endpoints.
    """

    # Endpoints exempt from rate limiting
    _EXEMPT_PATHS = frozenset({"/", "/health", "/docs", "/openapi.json", "/redoc"})

    def __init__(self, app, max_requests: int = 30, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # {client_ip: [timestamp, timestamp, ...]}
        self._requests: dict[str, list[float]] = defaultdict(list)

    def _clean_old_entries(self, ip: str, now: float) -> None:
        """Remove timestamps outside the current window."""
        cutoff = now - self.window_seconds
        self._requests[ip] = [t for t in self._requests[ip] if t > cutoff]

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip rate limiting for exempt paths
        if path in self._EXEMPT_PATHS or path.startswith("/docs") or path.startswith("/redoc"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.time()

        self._clean_old_entries(client_ip, now)

        if len(self._requests[client_ip]) >= self.max_requests:
            logger.log_warning(f"Rate limit exceeded for IP {client_ip} — {self.max_requests} req/{self.window_seconds}s")
            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"Rate limit exceeded. Maximum {self.max_requests} requests per {self.window_seconds} seconds.",
                },
                headers={
                    "Retry-After": str(self.window_seconds),
                    "X-RateLimit-Limit": str(self.max_requests),
                    "X-RateLimit-Remaining": "0",
                },
            )

        self._requests[client_ip].append(now)

        response = await call_next(request)

        # Attach rate limit info headers
        remaining = max(0, self.max_requests - len(self._requests[client_ip]))
        response.headers["X-RateLimit-Limit"] = str(self.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)

        return response


# ---------------------------------------------------------------------------
# 3. Persistent Rate Limiting Middleware (SQLite-backed sliding window)
# ---------------------------------------------------------------------------

class PersistentRateLimitMiddleware(BaseHTTPMiddleware):
    """
    SQLite-backed sliding-window rate limiter.
    State survives server restarts — use when rate limit persistence is required.
    """

    _EXEMPT_PATHS = frozenset({"/", "/health", "/docs", "/openapi.json", "/redoc"})

    def __init__(self, app, max_requests: int = 30, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in self._EXEMPT_PATHS or path.startswith("/docs") or path.startswith("/redoc"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        cutoff = now - self.window_seconds
        remaining = self.max_requests

        try:
            from app.database.connection import SessionLocal
            from app.models.rate_limit import RateLimit

            db = SessionLocal()
            try:
                count = db.query(RateLimit).filter(
                    RateLimit.ip_address == client_ip,
                    RateLimit.timestamp > cutoff,
                ).count()

                if count >= self.max_requests:
                    logger.log_warning(
                        f"Rate limit exceeded for IP {client_ip} (persistent) — "
                        f"{self.max_requests} req/{self.window_seconds}s"
                    )
                    return JSONResponse(
                        status_code=429,
                        content={
                            "detail": (
                                f"Rate limit exceeded. Maximum {self.max_requests} "
                                f"requests per {self.window_seconds} seconds."
                            ),
                        },
                        headers={
                            "Retry-After": str(self.window_seconds),
                            "X-RateLimit-Limit": str(self.max_requests),
                            "X-RateLimit-Remaining": "0",
                        },
                    )

                db.add(RateLimit(ip_address=client_ip, timestamp=now))
                db.commit()
                remaining = max(0, self.max_requests - count - 1)
            except Exception as e:
                logger.log_warning(f"Persistent rate limit DB error: {e}")
                db.rollback()
            finally:
                db.close()
        except Exception as e:
            logger.log_warning(f"Persistent rate limit middleware error: {e}")

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
