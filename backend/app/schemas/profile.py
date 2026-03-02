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
    description: Optional[str] = None
    additional_info: Optional[Dict[str, Any]] = None
    similar_profiles: Optional[List[str]] = None


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
    description: Optional[str] = None
    additional_info: Optional[Dict[str, Any]] = None
    similar_profiles: Optional[List[str]] = None
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
    description: Optional[str] = None
    additional_info: Optional[Dict[str, Any]] = None
    similar_profiles: Optional[List[str]] = None
    sources: Optional[List[Dict[str, str]]] = None  # Raw search results/sources
    ai_response: str  # JARVIS's formatted response
