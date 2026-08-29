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
    vision_model: str = "qwen2.5vl:7b"
    """Multimodal model for image and screen reading.

    Was ``llama3.2-vision`` until 2026-08-29. Ollama 0.32.13 dropped the
    ``mllama`` architecture, so that model still appears in ``ollama list`` and
    fails to load on every call. Qwen2.5-VL also grounds far better, which is
    what the browse tier's pixel-coordinate fallback depends on."""

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
    # One rendered result page legitimately issues dozens of authenticated
    # requests (session start, stream, history, one per avatar), so a budget
    # tuned for a public API rate-limits this UI against itself.
    rate_limit_requests: int = 120  # max requests per window
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

    # Stealth tier (Scrapling + patchright-driven Chromium). Turning this off
    # degrades discovery to the plain HTTP tier instead of failing:
    # Instagram/TikTok/LinkedIn simply report `blocked` rather than crashing.
    discovery_stealth_enabled: bool = True
    discovery_max_stealth_pages: int = 3
    discovery_max_concurrent_stealth_sessions: int = 2

    # A single search is allowed to run long (the user explicitly asked for depth
    # over speed); this is the hard ceiling that stops a runaway loop.
    discovery_max_wall_clock_seconds: int = 1800

    # robots.txt is fetched and recorded either way; this only controls whether a
    # disallow actually blocks the fetch.
    discovery_respect_robots: bool = False

    # Human-in-the-loop. A question has no deadline — only this cap on how many
    # times one run is allowed to interrupt the user.
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

    # ------------------------------------------------------------------
    # Anti-blocking. With no proxy pool the only levers left are looking like a
    # consistent browser and pacing like a human, so these default to on.
    # ------------------------------------------------------------------
    # Exactly periodic requests are a bot signal in themselves; spread each wait
    # by +/- this fraction. 0 restores the old machine-perfect cadence.
    discovery_rate_jitter: float = 0.3

    # On a refusal that carries no Retry-After, widen that domain's interval for
    # the rest of the process instead of knocking at the same rejected cadence.
    discovery_adaptive_backoff: bool = True

    # Carry cookies across requests, and hand the cookies the browser earned
    # (Cloudflare clearance, consent) down to the cheap HTTP tier.
    discovery_cookie_persistence: bool = True

    # Reuse a browser profile directory between searches so Cloudflare clearance
    # and consent cookies survive. Relative paths resolve against backend/.
    discovery_browser_profile_persist: bool = True
    discovery_browser_profile_dir: str = "data/browser_profiles"

    # Launch the real installed Chrome rather than the bundled Chromium when one
    # is present. Silently ignored where no Chrome exists (e.g. the Docker image).
    discovery_real_chrome: bool = True

    # Canvas noise is randomised per request, which contradicts a persistent
    # profile's otherwise stable fingerprint. Off by default; flip it to compare.
    discovery_hide_canvas: bool = False

    # ------------------------------------------------------------------
    # Interactive browse tier — HTTP -> stealth -> browse, in that order.
    #
    # Every step costs one local vision inference, so each limit here is a
    # ceiling the phase must not be able to talk its way past. The phase runs at
    # most once per search: on an 8 GB card the vision model and the narrative
    # model cannot both be resident, so a per-round browse would make ollama
    # evict and reload one of them every round.
    # ------------------------------------------------------------------
    discovery_browse_enabled: bool = True
    discovery_browse_max_tasks_per_search: int = 2
    discovery_browse_max_steps: int = 12
    discovery_browse_max_seconds: float = 180.0
    discovery_browse_step_timeout_seconds: float = 45.0

    # The phase only starts with this much wall clock still unspent. It must
    # never be what starves the biography at the end of a search.
    discovery_browse_min_time_left_seconds: float = 300.0

    discovery_browse_viewport_width: int = 1280
    discovery_browse_viewport_height: int = 800
    discovery_browse_allow_pixel_clicks: bool = True

    # Empty means `vision_model`. Separate so the agent can be pointed at a
    # stronger VLM without disturbing avatar and photo analysis.
    discovery_browse_model: str = ""

    # Short, so ollama releases the vision model's ~6 GB before the narrative
    # model needs its own.
    discovery_browse_keep_alive: str = "30s"

    # --- Search brief -------------------------------------------------------
    # Structured constraints the user supplies with the query: a stated gender,
    # accounts they already know, a reference photo.
    discovery_brief_max_known_profiles: int = 10
    """How many known accounts one brief may pin. Each one costs a fetch."""

    discovery_brief_llm_parse_enabled: bool = True
    """Kill switch for the opt-in LLM pass over the text the parser could not
    place. The per-request flag still decides whether it runs at all."""

    # --- Avatar gender screen -----------------------------------------------
    # Only ever runs when the user stated a gender. It can remove a candidate, so
    # the budget is tight and the confidence floor is high: a wrong exclusion is
    # far more expensive than a missed one.
    discovery_avatar_gender_enabled: bool = True
    discovery_avatar_gender_max_checks: int = 12
    """Vision calls per search. Each is 4-8 s and evicts the narrative model on
    an 8 GB card, so this is a wall-clock decision, not a quality one."""

    discovery_avatar_gender_min_confidence: float = 0.75
    discovery_avatar_gender_model: str = ""
    """Empty falls back to `discovery_browse_model`, then `vision_model`."""

    # Frames are telemetry, not findings: unlike avatars they are swept.
    discovery_browse_frame_dir: str = "data/browse_frames"
    discovery_browse_frame_max_edge: int = 1024
    discovery_browse_frame_quality: int = 60
    discovery_browse_frame_ttl_seconds: int = 3600
    discovery_browse_frame_max_files: int = 500

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
