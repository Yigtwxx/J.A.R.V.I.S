from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator


class SearchQuery(BaseModel):
    """Search query from user"""
    query: str = Field(..., min_length=2, max_length=200, description="Search query (e.g., person's name)")
    depth: int = Field(default=5, ge=1, le=10, description="Search depth 1-10 (surface/medium/deep)")


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
    medium_url: str | None = None
    threads_url: str | None = None
    steam_url: str | None = None
    tinder_mention: str | None = None
    bumble_mention: str | None = None
    discord_mention: str | None = None
    phone_numbers: list[str] | None = None

    @field_validator(
        'github_url', 'instagram_url', 'twitter_url', 'linkedin_url',
        'spotify_url', 'tiktok_url', 'snapchat_url', 'tumblr_url',
        'youtube_url', 'reddit_url', 'facebook_url', 'pinterest_url',
        'medium_url', 'threads_url', 'steam_url',
        mode='before',
    )
    @classmethod
    def validate_url_fields(cls, v: str | None) -> str | None:
        if v is None:
            return v
        for part in v.split(','):
            part = part.strip()
            if not part:
                continue
            parsed = urlparse(part)
            if parsed.scheme not in ('http', 'https'):
                raise ValueError(
                    f"URL scheme must be http or https, got {parsed.scheme!r}: {part!r}"
                )
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

    @field_validator('email_addresses', mode='before')
    @classmethod
    def validate_email_addresses(cls, v: list | None) -> list | None:
        if v is None:
            return v
        for email in v:
            if not isinstance(email, str) or '@' not in email:
                raise ValueError(f"Invalid email address: {email!r}")
        return v

    @field_validator('phone_numbers', mode='before')
    @classmethod
    def validate_phone_numbers(cls, v: list | None) -> list | None:
        if v is None:
            return v
        for phone in v:
            if not isinstance(phone, str) or len(phone.strip()) < 3:
                raise ValueError(f"Phone number too short or invalid: {phone!r}")
        return v

    @field_validator('network_connections', mode='before')
    @classmethod
    def validate_network_connections(cls, v: list | None) -> list | None:
        if v is None:
            return v
        for item in v:
            if not isinstance(item, dict) or 'name' not in item:
                raise ValueError("Each network_connection entry must have a 'name' key")
        return v

    @field_validator('data_breaches', mode='before')
    @classmethod
    def validate_data_breaches(cls, v: list | None) -> list | None:
        if v is None:
            return v
        for item in v:
            if not isinstance(item, dict) or 'source' not in item:
                raise ValueError("Each data_breach entry must have a 'source' key")
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
    tactical_analysis: dict[str, Any] | None = None
    psychological_analysis: PsychologicalAnalysis | None = None
    prediction_data: PredictiveAnalysis | None = None
    search_depth: int | None = None
    search_tier: str | None = None
