import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse

from app.config import get_settings
from app.database import init_db
from app.middleware.security import RateLimitMiddleware
from app.plugins import plugin_manager
from app.services.self_healing_service import self_healing_service
from app.routes import (
    agent_router,
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

    # Security: API key status
    if not settings.api_key:
        logger.log_warning("=" * 60)
        logger.log_warning("WARNING: API_KEY is not configured!")
        logger.log_warning("All endpoints are UNPROTECTED without an API key.")
        logger.log_warning("Set API_KEY in backend/.env and NEXT_PUBLIC_API_KEY in frontend.")
        logger.log_warning("Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\"")
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

    logger.log_success("All systems online. Awaiting coordinates.")
    yield
    # --- Shutdown ---
    self_healing_service.stop()
    monitor_task.cancel()


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


# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate Limiting (per-IP sliding window)
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
app.include_router(system_router)
app.include_router(health_router)


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
async def stream_status():
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

