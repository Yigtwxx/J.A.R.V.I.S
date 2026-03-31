from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SearchQuery(BaseModel):
    """Search query from user"""
    query: str = Field(..., description="Search query (e.g., person's name)")


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


class ProfileDataMixin(SocialUrlsMixin):
    """Extended profile fields shared across create, response, and search schemas."""
    description: str | None = None
    additional_info: dict[str, Any] | None = None
    similar_profiles: list[str] | None = None
    cross_validation_issues: list[str] | None = None
    network_connections: list[dict[str, str]] | None = None
    email_addresses: list[str] | None = None
    data_breaches: list[dict[str, Any]] | None = None


class ProfileCreate(ProfileDataMixin):
    """Schema for creating a new profile"""
    name: str


class ProfileResponse(ProfileDataMixin):
    """Schema for profile response"""
    id: int
    name: str
    created_at: datetime
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


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
