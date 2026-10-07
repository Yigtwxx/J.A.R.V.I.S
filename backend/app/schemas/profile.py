from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.discovery import (
    DiscoverySummary,
    EducationRecord,
    EvidenceItem,
    MatchReason,
    NarrativeClaim,
    ProfilePicture,
    RelationshipGraph,
    SearchBriefIn,
    SocialProfile,
    TimelineEvent,
    WorkRecord,
)

# Breach records keep the XposedOrNot / HIBP field names ('Name', 'Title', 'Domain',
# 'BreachDate', 'DataClasses') — that is what BreachService._normalize_breach emits
# and what the frontend LeakRecordSchema consumes. Paste exposures from
# DarkWebService use 'Source' and 'Id' instead. A record only has to be
# identifiable: demanding one specific key would reject the shapes the pipeline
# actually produces and fail the whole search at the final assembly step.
BREACH_IDENTIFIER_KEYS = frozenset(
    {
        "source",
        "Source",
        "name",
        "Name",
        "title",
        "Title",
        "domain",
        "Domain",
        "id",
        "Id",
    }
)


class SearchQuery(BaseModel):
    """Search query from user"""

    query: str = Field(..., min_length=2, max_length=200, description="Search query (e.g., person's name)")
    depth: int = Field(default=5, ge=1, le=10, description="Search depth 1-10 (surface/medium/deep)")
    entity_type: Literal["person", "company", "place"] = Field(
        default="person", description="What is being searched for — drives dorks and which platforms apply"
    )
    interactive: bool = Field(
        default=True,
        description=(
            "Allow the search to pause and ask clarifying questions. Only honoured on the session routes; "
            "the blocking POST /api/search/ endpoint is always non-interactive, because an HTTP request "
            "cannot sensibly wait on a human answer."
        ),
    )
    platforms: list[str] | None = Field(
        default=None,
        description=(
            "CORE platform keys to sweep, from GET /api/search/platforms. None means every CORE platform, "
            "which is the default sweep. Only honoured on the session routes."
        ),
    )
    include_extended_platforms: bool = Field(
        default=True,
        description=(
            "Whether the ~120-site EXTENDED long tail may run. True keeps the existing depth rule; False "
            "forces a CORE-only sweep at any depth. A ceiling, never an override. Session routes only."
        ),
    )

    brief: SearchBriefIn | None = Field(
        default=None,
        description=(
            "What the user already knows: a stated gender, accounts they can name, a reference photo. "
            "Omit it and the backend parses the same structure out of `query` deterministically, so a "
            "plain string behaves identically. Session routes only."
        ),
    )

    @field_validator("platforms")
    @classmethod
    def _validate_platforms(cls, value: list[str] | None) -> list[str] | None:
        """Reject an unknown or empty selection loudly.

        An empty list is not "search everywhere" — it is a search that can find
        nothing, and silently widening it back to all platforms would run the
        very sweep the user just tried to avoid.
        """
        if value is None:
            return None
        # Imported here: the schema layer is imported by the blocking search path
        # too, and the registry pulls in the whole discovery package.
        from app.discovery.platforms.registry import UNSUPPORTED_PLATFORMS, core_keys

        cleaned = [key.strip().lower() for key in value if key and key.strip()]
        if not cleaned:
            raise ValueError("platforms must name at least one platform")
        known = core_keys()
        unknown = sorted({key for key in cleaned if key not in known})
        if unknown:
            raise ValueError(f"unknown platform(s): {', '.join(unknown)}; see GET /api/search/platforms")
        # A platform nothing can check is not a search scope. Dropped rather than
        # rejected: a stored selection made before the platform was retired must
        # not start failing every search the user runs afterwards.
        supported = [key for key in cleaned if key not in UNSUPPORTED_PLATFORMS]
        if not supported:
            raise ValueError(
                "every platform selected is unsupported; see GET /api/search/platforms for which ones can be checked"
            )
        # Deduplicate, keep the caller's order for reproducible logs.
        return list(dict.fromkeys(supported))


class SocialUrlsMixin(BaseModel):
    """Shared social media URL fields — single source of truth for all profile schemas."""

    github_url: str | None = None
    instagram_url: str | None = None
    twitter_url: str | None = None
    linkedin_url: str | None = None
    spotify_url: str | None = None
    tiktok_url: str | None = None
    snapchat_url: str | None = None
    tumblr_url: str | None = None
    youtube_url: str | None = None
    reddit_url: str | None = None
    facebook_url: str | None = None
    pinterest_url: str | None = None
    threads_url: str | None = None
    steam_url: str | None = None
    tinder_mention: str | None = None
    bumble_mention: str | None = None
    discord_mention: str | None = None
    phone_numbers: list[str] | None = None
    contacts: list[dict] | None = None
    """Evidence-backed contact details, each with the page that published it.

    The flat lists above stay for the legacy consumers; this is the auditable
    form. See `app.schemas.discovery.ContactOut`."""

    @field_validator(
        "github_url",
        "instagram_url",
        "twitter_url",
        "linkedin_url",
        "spotify_url",
        "tiktok_url",
        "snapchat_url",
        "tumblr_url",
        "youtube_url",
        "reddit_url",
        "facebook_url",
        "pinterest_url",
        "threads_url",
        "steam_url",
        mode="before",
    )
    @classmethod
    def validate_url_fields(cls, v: str | None) -> str | None:
        if v is None:
            return v
        for part in v.split(","):
            part = part.strip()
            if not part:
                continue
            parsed = urlparse(part)
            if parsed.scheme not in ("http", "https"):
                raise ValueError(f"URL scheme must be http or https, got {parsed.scheme!r}: {part!r}")
            if not parsed.netloc:
                raise ValueError(f"URL is missing a host: {part!r}")
        return v


class ProfileDataMixin(SocialUrlsMixin):
    """Extended profile fields shared across create, response, and search schemas."""

    description: str | None = None
    additional_info: dict[str, Any] | None = None
    similar_profiles: list[str] | None = None
    cross_validation_issues: list[str] | None = None
    network_connections: list[dict[str, str]] | None = None
    email_addresses: list[str] | None = None
    data_breaches: list[dict[str, Any]] | None = None

    @field_validator("email_addresses", mode="before")
    @classmethod
    def validate_email_addresses(cls, v: list | None) -> list | None:
        if v is None:
            return v
        for email in v:
            if not isinstance(email, str) or "@" not in email:
                raise ValueError(f"Invalid email address: {email!r}")
        return v

    @field_validator("phone_numbers", mode="before")
    @classmethod
    def validate_phone_numbers(cls, v: list | None) -> list | None:
        if v is None:
            return v
        for phone in v:
            if not isinstance(phone, str) or len(phone.strip()) < 3:
                raise ValueError(f"Phone number too short or invalid: {phone!r}")
        return v

    @field_validator("network_connections", mode="before")
    @classmethod
    def validate_network_connections(cls, v: list | None) -> list | None:
        if v is None:
            return v
        for item in v:
            if not isinstance(item, dict) or "name" not in item:
                raise ValueError("Each network_connection entry must have a 'name' key")
        return v

    @field_validator("data_breaches", mode="before")
    @classmethod
    def validate_data_breaches(cls, v: list | None) -> list | None:
        """Reject junk entries while accepting every shape the pipeline emits.

        See BREACH_IDENTIFIER_KEYS for why the key set is deliberately wide.
        """
        if v is None:
            return v
        for item in v:
            if not isinstance(item, dict) or not (item.keys() & BREACH_IDENTIFIER_KEYS):
                raise ValueError(
                    "Each data_breach entry must be a dict carrying at least one identifying key "
                    f"({', '.join(sorted(BREACH_IDENTIFIER_KEYS))})"
                )
        return v


class ProfileCreate(ProfileDataMixin):
    """Schema for creating a new profile"""

    name: str = Field(..., min_length=1, max_length=200)


class ProfileResponse(ProfileDataMixin):
    """Schema for profile response"""

    id: int
    name: str
    created_at: datetime
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class Citation(BaseModel):
    """A single public-source citation backing a claim."""

    url: str
    title: str | None = None
    retrieved_at: str | None = None  # ISO8601 UTC
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class Claim(BaseModel):
    """A structured assertion about the subject, backed by public citations."""

    field: str  # e.g. "domain", "location_city"
    value: str
    citations: list[Citation] = []
    corroboration_count: int = 0  # how many independent sources corroborated


class GeoLocationData(BaseModel):
    """A single geographic intelligence point."""

    lat: float
    lng: float
    label: str
    type: str  # primary, company, exif, ip
    source: str
    confidence: float = 0.5
    timestamp: str | None = None


class TimezoneAnalysis(BaseModel):
    """Activity-based timezone and pattern analysis."""

    inferred_timezone: str = "UNKNOWN"
    peak_hours: list[int] = []
    activity_pattern: str = "Insufficient data"
    hourly_distribution: dict[str, int] = {}


class SocialEngineeringVector(BaseModel):
    """A single social engineering attack vector."""

    vector: str
    approach: str
    risk_level: str = "medium"  # low, medium, high


class PsychologicalAnalysis(BaseModel):
    """Psychological warfare and vulnerability analysis output."""

    psychological_profile: str
    strengths: list[str] = []
    weaknesses: list[str] = []
    tactical_recommendations: list[str] = []
    social_engineering_vectors: list[SocialEngineeringVector] = []
    manipulation_resistance_score: int = Field(default=50, ge=1, le=100)
    confidence_level: float = Field(default=0.5, ge=0.0, le=1.0)


class PredictionEntry(BaseModel):
    """A single predictive forecast."""

    category: str  # activity, behavioral, security, financial
    prediction: str
    probability: float = Field(default=0.5, ge=0.0, le=1.0)
    timeframe: str  # 24h, 7d, 30d, 90d
    supporting_evidence: list[str] = []


class PredictiveAnalysis(BaseModel):
    """Predictive analytics and forecasting output."""

    predictions: list[PredictionEntry] = []
    activity_pattern: dict[str, Any] | None = None
    trend_direction: str = "stable"  # increasing, stable, decreasing, erratic
    data_sufficiency: float = Field(default=0.5, ge=0.0, le=1.0)


class SearchResponse(ProfileDataMixin):
    """AI search response with gathered information"""

    # The pipeline enriches the response with post-analysis sections via plain
    # attribute assignment. Without this, a bad value slips through and only
    # blows up later inside FastAPI's response_model serialization — outside the
    # route's try/except, where it surfaces as a bare "Internal server error"
    # with no step attribution. Validating on assignment moves the failure to the
    # line that caused it, where the caller can drop that one section instead.
    model_config = ConfigDict(validate_assignment=True)

    name: str
    location_country: str | None = None
    location_city: str | None = None
    weather_info: dict[str, Any] | None = None
    social_media_score: int | None = None
    social_media_score_breakdown: dict[str, Any] | None = None
    last_activity_summary: str | None = None
    platform_activity: dict[str, Any] | None = None
    sources: list[dict[str, str]] | None = None
    ai_response: str
    version_history: dict[str, Any] | None = None
    face_match_results: dict[str, Any] | None = None
    sentiment_analysis: dict[str, Any] | None = None
    company_records: list[dict[str, Any]] | None = None
    geoint_data: list[GeoLocationData] | None = None
    timezone_analysis: TimezoneAnalysis | None = None
    psychological_analysis: PsychologicalAnalysis | None = None
    prediction_data: PredictiveAnalysis | None = None
    search_depth: int | None = None
    search_tier: str | None = None
    # --- Public-source intelligence depth (additive) ---
    domain_intel: list[dict[str, Any]] | None = None
    claims: list[Claim] | None = None
    timeline: list[dict[str, Any]] | None = None
    subject_confidence: float | None = None
    alternative_candidates: list[dict[str, Any]] | None = None
    archive_snapshots: list[dict[str, Any]] | None = None
    scholarly_records: list[dict[str, Any]] | None = None
    sanctions_hits: list[dict[str, Any]] | None = None
    relationships: list[dict[str, Any]] | None = None

    # --- Discovery pipeline (additive; the legacy *_url fields above stay
    # populated by discovery_bridge.legacy_social_urls so nothing breaks) ---
    entity_type: Literal["person", "company", "place"] = "person"
    social_profiles: list[SocialProfile] = Field(default_factory=list)
    """Structured replacement for the fifteen comma-joined ``*_url`` strings.
    Carries a per-platform status, so "blocked" is finally expressible."""

    profile_pictures: list[ProfilePicture] = Field(default_factory=list)
    primary_profile_picture: str | None = None
    work_history: list[WorkRecord] = Field(default_factory=list)
    education: list[EducationRecord] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    subject_confidence_reasons: list[MatchReason] = Field(default_factory=list)
    narrative_claims: list[NarrativeClaim] = Field(default_factory=list)
    relationship_graph: RelationshipGraph | None = None
    discovery_timeline: list[TimelineEvent] = Field(default_factory=list)
    discovery: DiscoverySummary | None = None
