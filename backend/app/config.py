import secrets
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""

    # Database
    database_url: str = "sqlite:///./data/jarvis.db"

    # Ollama (default aligned with backend/.env OLLAMA_MODEL; tool-calling is
    # supported by qwen2.5 and qwen3 alike)
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5"

    # Vision (multimodal)
    vision_model: str = "llama3.2-vision"

    # GitHub
    github_token: str = ""

    # OpenCorporates (optional API token — the free officer-search API now returns
    # 401 without one; when empty, CompanyService falls back to SEC / Companies
    # House / web search, so this stays optional)
    opencorporates_api_token: str = ""

    # OpenSanctions (optional API key — https://api.opensanctions.org). When set,
    # SanctionsService queries the OpenSanctions search API in addition to the
    # keyless OFAC SDN list; when empty it relies on OFAC SDN alone.
    opensanctions_api_token: str = ""

    # Windy Webcams (optional API key — https://api.windy.com/webcams). When set,
    # WebcamService queries the official public-webcam directory for nearby live
    # cameras with latest frames; when empty it falls back to a keyless web search
    # for public live-cam pages, so this stays optional.
    windy_webcams_api_key: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:3000"]

    # Security — API Key Authentication (empty = auth disabled, NOT recommended)
    api_key: str = ""

    # Rate Limiting (sliding window per IP)
    rate_limit_requests: int = 30      # max requests per window
    rate_limit_window_seconds: int = 60  # window size in seconds
    rate_limit_persistent: bool = False  # True = SQLite-backed (survives restarts)
    rate_limit_backend: str = "sqlite"  # "memory" | "sqlite" | "redis" — sqlite survives restarts; use redis for multi-instance
    redis_url: str = ""  # e.g. redis://localhost:6379 — required when rate_limit_backend=redis
    rate_limit_cleanup_interval: int = 300  # seconds between cleanup runs

    # Audit Trail
    audit_log_enabled: bool = True
    audit_log_retention_days: int = 30

    # CSRF Protection
    csrf_enabled: bool = False
    csrf_secret: str = ""

    # Computer Control (disabled by default for security)
    enable_computer_control: bool = False

    # Inference modules — psychological & predictive analysis run on PUBLIC data.
    # Enabled by default (preserves current behaviour); set False to gate them off.
    # The UI always shows an authorized-use disclaimer before these sections.
    enable_psychological_analysis: bool = True
    enable_predictive_analysis: bool = True

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
