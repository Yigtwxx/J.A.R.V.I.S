from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import search_router, profiles_router
from app.database import init_db
from app.config import get_settings
import sys

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
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(search_router)
app.include_router(profiles_router)


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    print("\n" + "="*70)
    print("  J.A.R.V.I.S Backend Server")
    print("  Just A Rather Very Intelligent System")
    print("="*70)
    
    print("\n🚀 Starting J.A.R.V.I.S API...")
    print(f"📊 Database: {settings.database_url.split('@')[-1] if '@' in settings.database_url else 'Not configured'}")
    print(f"🤖 AI Model: {settings.ollama_model} (Ollama)")
    print(f"🌐 Server: http://{settings.host}:{settings.port}")
    print(f"📚 API Docs: http://{settings.host}:{settings.port}/docs")
    
    # Initialize database tables
    try:
        init_db()
        print("✅ Database initialized successfully")
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        print("⚠️  Please check your database connection settings")
    
    print("\n" + "="*70)
    print("  Server is ready! Waiting for requests...")
    print("="*70 + "\n")
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
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        log_level="info"
    )
