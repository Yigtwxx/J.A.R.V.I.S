import secrets
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""

    # Database
    database_url: str = "sqlite:///./data/jarvis.db"

    # Ollama (default aligned with backend/.env OLLAMA_MODEL). qwen3.5 supports
    # tool-calling, which the agent loop depends on. It is a hybrid reasoning
    # model, so it emits <think> blocks — AIService strips those from the stream.
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3.5:9b"

    # Ollama transport timeouts (seconds). ollama-python defaults to no timeout at
    # all, so a dead or wedged daemon blocks a request forever. These are httpx
    # read timeouts — i.e. "no new bytes for N seconds" — so they never truncate a
    # healthy long-running generation, they only cut a connection that went silent.
    ollama_connect_timeout_seconds: float = 10.0
    ollama_stream_read_timeout_seconds: float = 300.0
    ollama_request_timeout_seconds: float = 300.0

    # Per-call LLM budgets (seconds). Generous on purpose: local models on CPU are
    # slow and a truncated analysis is worse than a slow one.
    llm_extraction_timeout_seconds: float = 300.0
    llm_side_analysis_timeout_seconds: float = 300.0

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
    rate_limit_requests: int = 30  # max requests per window
    rate_limit_window_seconds: int = 60  # window size in seconds
    rate_limit_persistent: bool = False  # True = SQLite-backed (survives restarts)
    rate_limit_backend: str = (
        "sqlite"  # "memory" | "sqlite" | "redis" — sqlite survives restarts; use redis for multi-instance
    )
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
    search_cache_ttl_seconds: int = 300  # 5 minutes
    search_cache_max_size: int = 50  # max cached queries

    # Debug mode (enables test/debug endpoints)
    debug: bool = False

    # Auto-reload the server on source changes. Off by default: the reloader kills
    # in-flight requests, and a single search can legitimately run for minutes.
    # Kept separate from `debug` so debug logging can be enabled without it.
    uvicorn_reload: bool = False

    # Plugins
    plugins_dir: str = "app/plugins"

    # ------------------------------------------------------------------
    # Discovery pipeline (app/discovery)
    # ------------------------------------------------------------------
    # Master feature flag. The legacy scraper that used to supply social profiles
    # was removed (it read HTTP 403 as "profile exists" and injected placeholder
    # entries), so with this off the search returns no accounts at all. Set it to
    # false only to isolate a discovery problem.
    discovery_enabled: bool = True

    # Stealth tier (Scrapling + Camoufox). Turning this off degrades discovery to
    # the plain HTTP tier instead of failing: Instagram/TikTok/LinkedIn simply
    # report `blocked` rather than crashing the search.
    discovery_stealth_enabled: bool = True
    discovery_max_stealth_pages: int = 3
    discovery_max_concurrent_stealth_sessions: int = 2

    # A single search is allowed to run long (the user explicitly asked for depth
    # over speed); this is the hard ceiling that stops a runaway loop.
    discovery_max_wall_clock_seconds: int = 1800

    # robots.txt is fetched and recorded either way; this only controls whether a
    # disallow actually blocks the fetch.
    discovery_respect_robots: bool = False

    # Human-in-the-loop. A timeout means "unknown", never "no".
    discovery_question_timeout_seconds: int = 120
    discovery_max_questions: int = 6
    discovery_llm_question_phrasing: bool = False

    # At most N accounts per platform in the final answer, all belonging to the
    # elected identity (a person legitimately has a main + a business account).
    discovery_max_profiles_per_platform: int = 5

    # Extra discovery sources
    discovery_reverse_image_enabled: bool = True
    discovery_extended_platforms_min_depth: int = 6
    discovery_max_extended_checks: int = 120
    discovery_archive_recovery_enabled: bool = True
    discovery_website_crawl_max_pages: int = 10

    # Optional outbound proxy. Read from the environment only — never hardcode
    # credentials — and masked in every log line. Empty means "connect directly".
    discovery_proxy_url: str = ""
    discovery_proxy_pool: list[str] = []
    discovery_proxy_platforms: list[str] = []

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
