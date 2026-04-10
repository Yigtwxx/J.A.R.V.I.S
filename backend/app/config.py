import secrets
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""

    # Database
    database_url: str = "sqlite:///./data/jarvis.db"

    # Ollama
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"

    # Vision (multimodal)
    vision_model: str = "llama3.2-vision"

    # GitHub
    github_token: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:3000"]

    # Security — API Key Authentication (empty = auth disabled, NOT recommended)
    api_key: str = ""

    # Rate Limiting (sliding window per IP)
    rate_limit_requests: int = 30      # max requests per window
    rate_limit_window_seconds: int = 60  # window size in seconds

    # Computer Control (disabled by default for security)
    enable_computer_control: bool = False

    # Cache (in-memory TTL cache for search results)
    search_cache_ttl_seconds: int = 300   # 5 minutes
    search_cache_max_size: int = 50       # max cached queries

    # Debug mode (enables test/debug endpoints)
    debug: bool = False

    # Plugins
    plugins_dir: str = "app/plugins"

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


def generate_api_key() -> str:
    """Generate a cryptographically secure API key."""
    return secrets.token_urlsafe(32)
