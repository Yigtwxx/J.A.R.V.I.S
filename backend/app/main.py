import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse

from app.config import generate_api_key, get_settings
from app.database import init_db
from app.middleware.audit import AuditMiddleware
from app.middleware.csrf import CSRFMiddleware
from app.middleware.security import (
    PersistentRateLimitMiddleware,
    RateLimitMiddleware,
    RedisRateLimitMiddleware,
    verify_api_key,
)
from app.plugins import plugin_manager
from app.services.self_healing_service import self_healing_service
from app.routes import (
    agent_router,
    audit_router,
    chat_router,
    export_router,
    face_match_router,
    health_router,
    history_router,
    memory_router,
    plugins_router,
    profiles_router,
    search_router,
    version_history_router,
    system_router,
    vision_router,
    visual_intel_router,
    watch_router,
)
from app.utils.logger import logger

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown logic."""
    # --- Startup ---
    logger.print_header()
    logger.log_action("Initializing J.A.R.V.I.S core systems...")
    logger.log_action("Database Source", target=settings.database_url.split('@')[-1] if '@' in settings.database_url else 'Not configured')
    logger.log_action("AI Neural Net", target=f"{settings.ollama_model} (Ollama)")
    logger.log_action("Server Address", target=f"http://{settings.host}:{settings.port}")

    # Security: auto-generate CSRF secret if enabled but not configured
    if settings.csrf_enabled and not settings.csrf_secret:
        import secrets as _secrets
        csrf_secret = _secrets.token_hex(32)
        object.__setattr__(settings, "csrf_secret", csrf_secret)
        logger.log_warning("CSRF enabled but CSRF_SECRET not set — auto-generated for this session.")
        logger.log_warning("Set CSRF_SECRET in backend/.env for persistent CSRF protection.")

    # Security: API key — auto-generate if not configured so auth is never disabled
    if not settings.api_key:
        generated_key = generate_api_key()
        object.__setattr__(settings, "api_key", generated_key)
        logger.log_warning("=" * 60)
        logger.log_warning("WARNING: API_KEY was not configured in .env!")
        logger.log_warning(f"Auto-generated API key: {generated_key}")
        logger.log_warning("Add this to backend/.env:  API_KEY=" + generated_key)
        logger.log_warning("Also set NEXT_PUBLIC_API_KEY in frontend/.env.local")
        logger.log_warning("=" * 60)
    else:
        logger.log_success("API Key authentication active")

    # Ollama connectivity pre-check
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{settings.ollama_url}/api/tags", timeout=5.0)
            models = [m["name"] for m in resp.json().get("models", [])]
            if any(settings.ollama_model in m for m in models):
                logger.log_success(f"Ollama online — model '{settings.ollama_model}' available")
            else:
                logger.log_warning(
                    f"Ollama online but model '{settings.ollama_model}' not found. "
                    f"Available: {', '.join(models) or 'none'}"
                )
    except Exception as e:
        logger.log_warning("=" * 60)
        logger.log_warning(f"Ollama is unreachable at {settings.ollama_url}")
        logger.log_warning(f"Error: {e}")
        logger.log_warning("AI features will fail until Ollama is available.")
        logger.log_warning("=" * 60)

    try:
        init_db()
        logger.log_success("Memory matrices initialized successfully.")
    except Exception as e:
        logger.log_error(f"Memory matrix initialization failed: {e}")
        logger.log_thought("Check active database connections.")

    plugin_manager.discover()

    # Start self-healing background monitor
    monitor_task = asyncio.create_task(self_healing_service.start_monitoring(interval_seconds=30))

    # Start persistent rate-limit cleanup task (if persistent mode is on)
    rl_cleanup_task = None
    if settings.rate_limit_persistent:
        async def _rate_limit_cleanup():
            while True:
                await asyncio.sleep(settings.rate_limit_cleanup_interval)
                try:
                    import time as _time
                    from app.database.connection import SessionLocal
                    from app.models.rate_limit import RateLimit
                    cutoff = _time.time() - settings.rate_limit_window_seconds
                    db = SessionLocal()
                    try:
                        deleted = db.query(RateLimit).filter(RateLimit.timestamp < cutoff).delete()
                        db.commit()
                        if deleted:
                            logger.log_action(f"Rate limit cleanup: removed {deleted} expired entries")
                    finally:
                        db.close()
                except Exception as e:
                    logger.log_warning(f"Rate limit cleanup error: {e}")
        rl_cleanup_task = asyncio.create_task(_rate_limit_cleanup())

    # Start daily audit log cleanup task
    audit_cleanup_task = None
    if settings.audit_log_enabled:
        async def _audit_cleanup():
            while True:
                await asyncio.sleep(86400)  # daily
                try:
                    from datetime import datetime, timedelta
                    from app.database.connection import SessionLocal
                    from app.models.audit_log import AuditLog
                    cutoff = datetime.utcnow() - timedelta(days=settings.audit_log_retention_days)
                    db = SessionLocal()
                    try:
                        deleted = db.query(AuditLog).filter(AuditLog.timestamp < cutoff).delete()
                        db.commit()
                        logger.log_action(f"Audit cleanup: removed {deleted} entries older than {settings.audit_log_retention_days}d")
                    finally:
                        db.close()
                except Exception as e:
                    logger.log_warning(f"Audit cleanup error: {e}")
        audit_cleanup_task = asyncio.create_task(_audit_cleanup())

    logger.log_success("All systems online. Awaiting coordinates.")
    yield
    # --- Shutdown ---
    self_healing_service.stop()
    monitor_task.cancel()
    if rl_cleanup_task:
        rl_cleanup_task.cancel()
    if audit_cleanup_task:
        audit_cleanup_task.cancel()


# Create FastAPI app
app = FastAPI(
    title="J.A.R.V.I.S API",
    description="AI Assistant API for searching and managing person profiles",
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Global exception handlers — consistent error response format
# ---------------------------------------------------------------------------

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return a consistent error format for validation failures."""
    errors = exc.errors()
    messages = []
    for err in errors:
        loc = " -> ".join(str(part) for part in err.get("loc", []))
        msg = err.get("msg", "Invalid value")
        messages.append(f"{loc}: {msg}" if loc else msg)
    detail = "; ".join(messages) if messages else "Validation error"
    logger.log_warning(f"Validation error on {request.method} {request.url.path}: {detail}")
    return JSONResponse(
        status_code=422,
        content={"detail": detail, "type": "validation_error"},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch-all for unhandled exceptions — log and return a generic error."""
    logger.log_error(f"Unhandled exception on {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": "server_error"},
    )


# Configure CORS (tightened header/method lists)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key", "X-CSRF-Token", "Authorization"],
)

# CSRF protection (opt-in via csrf_enabled=True)
app.add_middleware(CSRFMiddleware, secret=settings.csrf_secret)

# Audit trail
app.add_middleware(AuditMiddleware)

# Rate Limiting: select backend from config (memory / sqlite / redis)
_rl_backend = settings.rate_limit_backend.lower()
if _rl_backend == "redis":
    if not settings.redis_url:
        raise RuntimeError("RATE_LIMIT_BACKEND=redis requires REDIS_URL to be set in .env")
    app.add_middleware(
        RedisRateLimitMiddleware,
        max_requests=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window_seconds,
        redis_url=settings.redis_url,
    )
elif _rl_backend == "sqlite" or settings.rate_limit_persistent:
    app.add_middleware(
        PersistentRateLimitMiddleware,
        max_requests=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window_seconds,
    )
else:
    app.add_middleware(
        RateLimitMiddleware,
        max_requests=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window_seconds,
    )

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log incoming requests as JARVIS network traffic"""
    # Skip SSE streams from spamming the logs continuously
    if request.url.path == "/api/status/stream":
        return await call_next(request)

    start_time = time.time()
    client_ip = request.client.host if request.client else "Unknown"

    # Log incoming request
    logger.log_network_traffic(
        method=request.method,
        path=request.url.path,
        client_ip=client_ip
    )

    response = await call_next(request)

    process_time = (time.time() - start_time) * 1000  # ms

    # Log outgoing response
    logger.log_network_traffic(
        method=request.method,
        path=request.url.path,
        client_ip=client_ip,
        status_code=response.status_code,
        process_time=process_time
    )

    return response

# Include routers
app.include_router(search_router)
app.include_router(profiles_router)
app.include_router(history_router)
app.include_router(version_history_router)
app.include_router(face_match_router)
app.include_router(chat_router)
app.include_router(export_router)
app.include_router(memory_router)
app.include_router(watch_router)
app.include_router(plugins_router)
app.include_router(agent_router)
app.include_router(vision_router)
app.include_router(visual_intel_router)
app.include_router(system_router)
app.include_router(health_router)
app.include_router(audit_router)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Welcome to J.A.R.V.I.S API",
        "version": "1.0.0",
        "status": "operational",
        "endpoints": {
            "search": "/api/search",
            "profiles": "/api/profiles",
            "docs": "/docs"
        }
    }


@app.get("/api/status/stream")
async def stream_status(_api_key: str = Depends(verify_api_key)):
    """Stream live JARVIS activity logs via SSE"""
    async def event_generator():
        queue = asyncio.Queue()
        logger.subscribers.add(queue)
        try:
            # Send initial connection success
            yield "data: [SYS] Virtual Intelligence Link Established\n\n"
            while True:
                message = await queue.get()
                yield f"data: {message}\n\n"
        except asyncio.CancelledError:
            pass  # Normal: client disconnected
        except Exception as e:
            logger.log_warning(f"SSE stream error: {e}")
        finally:
            # Guarantee cleanup on any exit path (disconnect, error, GeneratorExit)
            logger.subscribers.discard(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Prevents Nginx buffering
        }
    )


@app.get("/health")
async def health_check():
    """Comprehensive health check — returns status of all dependent services."""
    return self_healing_service.get_full_health_check()


if __name__ == "__main__":
    import os
    import sys

    import uvicorn

    # Ensure the parent directory is in the path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        log_level="info"
    )

