from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""

    # Database
    database_url: str = "sqlite:///./data/jarvis.db"

    # Ollama
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"

    # Embedding & Vector Store
    embedding_model: str = "nomic-embed-text"
    chroma_db_path: str = "data/chroma_db"

    # GitHub
    github_token: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:3000"]

    # Security — API Key Authentication (empty = auth disabled)
    api_key: str = ""

    # Rate Limiting (sliding window per IP)
    rate_limit_requests: int = 30      # max requests per window
    rate_limit_window_seconds: int = 60  # window size in seconds

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
