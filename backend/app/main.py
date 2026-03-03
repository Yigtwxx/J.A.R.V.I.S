from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.routes import search_router, profiles_router, history_router
from app.database import init_db
from app.config import get_settings
from app.jarvis_logger import logger
import sys
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
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log incoming requests as JARVIS thoughts"""
    start_time = time.time()
    
    # If it's a search request, let JARVIS think
    if "/api/search" in request.url.path and request.method == "POST":
         logger.log_thought(f"Incoming connection detected on secure channel {request.url.path}")

    response = await call_next(request)
    process_time = time.time() - start_time
    
    if "/api/search" in request.url.path and response.status_code == 200:
        logger.log_action("Analysis complete.", target=f"{process_time:.2f}s elapsed")
        
    return response

# Include routers
app.include_router(search_router)
app.include_router(profiles_router)
app.include_router(history_router)


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
    sys.stdout.flush()


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


from fastapi.responses import StreamingResponse
import asyncio

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

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "ai_service": "Ollama",
        "database": "PostgreSQL"
    }


if __name__ == "__main__":
    import uvicorn
    import sys
    import os
    
    # Ensure the parent directory is in the path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        log_level="info"
    )

