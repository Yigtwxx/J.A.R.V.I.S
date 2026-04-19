"""
CSRF protection middleware (opt-in via csrf_enabled=True in config).
Implements the double-submit cookie pattern.
"""
import hmac
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.utils.logger import logger

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class CSRFMiddleware(BaseHTTPMiddleware):
    """
    Double-submit cookie CSRF protection.

    - On GET/HEAD/OPTIONS: issues a csrf_token cookie if absent.
    - On POST/PUT/DELETE/PATCH: requires X-CSRF-Token header to match
      the csrf_token cookie (constant-time comparison).
    - Only active when settings.csrf_enabled is True.
    """

    def __init__(self, app, secret: str):
        super().__init__(app)
        self.secret = secret

    async def dispatch(self, request: Request, call_next):
        from app.config import get_settings
        settings = get_settings()

        if not settings.csrf_enabled:
            return await call_next(request)

        if request.method in _SAFE_METHODS:
            response = await call_next(request)
            # Issue cookie on safe requests if absent
            if "csrf_token" not in request.cookies:
                token = secrets.token_hex(32)
                response.set_cookie(
                    "csrf_token",
                    token,
                    samesite="strict",
                    secure=False,   # Set True behind TLS in production
                    httponly=False,  # Must be JS-readable for header injection
                )
            return response

        # Validate token for state-changing methods
        csrf_header = request.headers.get("X-CSRF-Token", "")
        csrf_cookie = request.cookies.get("csrf_token", "")

        if not csrf_header or not csrf_cookie:
            logger.log_warning(
                f"CSRF token missing on {request.method} {request.url.path}"
            )
            return JSONResponse(
                status_code=403,
                content={
                    "detail": (
                        "CSRF token missing. Perform a GET request first "
                        "to obtain the token, then include it in X-CSRF-Token header."
                    )
                },
            )

        if not hmac.compare_digest(csrf_header, csrf_cookie):
            logger.log_warning(
                f"CSRF token mismatch on {request.method} {request.url.path}"
            )
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF token invalid."},
            )

        return await call_next(request)
