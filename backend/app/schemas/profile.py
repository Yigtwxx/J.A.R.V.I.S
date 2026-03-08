from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any
from datetime import datetime


class SearchQuery(BaseModel):
    """Search query from user"""
    query: str = Field(..., description="Search query (e.g., person's name)")


class ProfileCreate(BaseModel):
    """Schema for creating a new profile"""
    name: str
    github_url: Optional[str] = None
    instagram_url: Optional[str] = None
    twitter_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    spotify_url: Optional[str] = None
    tiktok_url: Optional[str] = None
    snapchat_url: Optional[str] = None
    tumblr_url: Optional[str] = None
    tinder_mention: Optional[str] = None
    bumble_mention: Optional[str] = None
    phone_numbers: Optional[List[str]] = None
    description: Optional[str] = None
    additional_info: Optional[Dict[str, Any]] = None
    similar_profiles: Optional[List[str]] = None
    cross_validation_issues: Optional[List[str]] = None
    network_connections: Optional[List[Dict[str, str]]] = None


class ProfileResponse(BaseModel):
    """Schema for profile response"""
    id: int
    name: str
    github_url: Optional[str] = None
    instagram_url: Optional[str] = None
    twitter_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    spotify_url: Optional[str] = None
    tiktok_url: Optional[str] = None
    snapchat_url: Optional[str] = None
    tumblr_url: Optional[str] = None
    tinder_mention: Optional[str] = None
    bumble_mention: Optional[str] = None
    phone_numbers: Optional[List[str]] = None
    description: Optional[str] = None
    additional_info: Optional[Dict[str, Any]] = None
    similar_profiles: Optional[List[str]] = None
    cross_validation_issues: Optional[List[str]] = None
    network_connections: Optional[List[Dict[str, str]]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class SearchResponse(BaseModel):
    """AI search response with gathered information"""
    name: str
    github_url: Optional[str] = None
    instagram_url: Optional[str] = None
    twitter_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    spotify_url: Optional[str] = None
    tiktok_url: Optional[str] = None
    snapchat_url: Optional[str] = None
    tumblr_url: Optional[str] = None
    tinder_mention: Optional[str] = None
    bumble_mention: Optional[str] = None
    phone_numbers: Optional[List[str]] = None
    description: Optional[str] = None
    additional_info: Optional[Dict[str, Any]] = None
    similar_profiles: Optional[List[str]] = None
    cross_validation_issues: Optional[List[str]] = None
    network_connections: Optional[List[Dict[str, str]]] = None
    location_country: Optional[str] = None
    location_city: Optional[str] = None
    weather_info: Optional[Dict[str, Any]] = None
    social_media_score: Optional[int] = None
    social_media_score_breakdown: Optional[Dict[str, Any]] = None
    last_activity_summary: Optional[str] = None
    platform_activity: Optional[Dict[str, Any]] = None
    sources: Optional[List[Dict[str, str]]] = None
    ai_response: str
    version_history: Optional[Dict[str, Any]] = None
    face_match_results: Optional[Dict[str, Any]] = None
    sentiment_analysis: Optional[Dict[str, Any]] = None
