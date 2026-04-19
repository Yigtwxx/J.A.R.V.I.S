"""
Audit trail middleware — records every non-exempt HTTP request to audit_logs.
Failures are logged but never propagate to the caller.
"""
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.utils.logger import logger

_EXEMPT_PATHS = frozenset({
    "/health", "/docs", "/openapi.json", "/redoc", "/api/status/stream",
})


class AuditMiddleware(BaseHTTPMiddleware):
    """Records request metadata (IP, endpoint, status, duration) into audit_logs."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip exempt and docs paths
        if path in _EXEMPT_PATHS or path.startswith("/docs") or path.startswith("/redoc"):
            return await call_next(request)

        start_time = time.time()
        response = await call_next(request)
        duration_ms = round((time.time() - start_time) * 1000, 2)

        try:
            from app.config import get_settings
            settings = get_settings()

            if not settings.audit_log_enabled:
                return response

            from app.database.connection import SessionLocal
            from app.models.audit_log import AuditLog

            body_size = int(request.headers.get("content-length", 0) or 0)
            client_ip = request.client.host if request.client else "unknown"
            user_agent = (request.headers.get("user-agent", "") or "")[:500]

            db = SessionLocal()
            try:
                entry = AuditLog(
                    ip_address=client_ip,
                    endpoint=str(path)[:500],
                    method=request.method,
                    user_agent=user_agent,
                    response_status=response.status_code,
                    duration_ms=duration_ms,
                    request_body_size=body_size,
                )
                db.add(entry)
                db.commit()
            except Exception as e:
                logger.log_warning(f"Audit log write failed (non-critical): {e}")
                db.rollback()
            finally:
                db.close()
        except Exception as e:
            logger.log_warning(f"Audit middleware error (non-critical): {e}")

        return response
