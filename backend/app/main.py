from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from app.routes import search_router, profiles_router, history_router, version_history_router, face_match_router, chat_router
from app.database import init_db
from app.config import get_settings
from app.utils.logger import logger
import asyncio
import time

settings = get_settings()

# Create FastAPI app
app = FastAPI(
    title="J.A.R.V.I.S API",
    description="AI Assistant API for searching and managing person profiles",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    logger.print_header()
    
    logger.log_action("Initializing J.A.R.V.I.S core systems...")
    logger.log_action("Database Source", target=settings.database_url.split('@')[-1] if '@' in settings.database_url else 'Not configured')
    logger.log_action("AI Neural Net", target=f"{settings.ollama_model} (Ollama)")
    logger.log_action("Server Address", target=f"http://{settings.host}:{settings.port}")
    
    # Initialize database tables
    try:
        init_db()
        logger.log_success("Memory matrices initialized successfully.")
    except Exception as e:
        logger.log_error(f"Memory matrix initialization failed: {e}")
        logger.log_thought("Check active database connections.")
    
    logger.log_success("All systems online. Awaiting coordinates.")
    
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
            yield f"data: [SYS] Virtual Intelligence Link Established\n\n"
            while True:
                message = await queue.get()
                yield f"data: {message}\n\n"
        except (asyncio.CancelledError, Exception):
            pass
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
    """Health check endpoint"""
    return {
        "status": "healthy",
        "ai_service": "Ollama",
        "database": "PostgreSQL"
    }


if __name__ == "__main__":
    import sys, os, uvicorn

    # Ensure the parent directory is in the path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        log_level="info"
    )

