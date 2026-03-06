from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


class SnapshotResponse(BaseModel):
    """Serialized snapshot data"""
    id: int
    query_name: str
    github_url: Optional[str] = None
    instagram_url: Optional[str] = None
    twitter_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    spotify_url: Optional[str] = None
    tiktok_url: Optional[str] = None
    description: Optional[str] = None
    additional_info: Optional[Dict[str, Any]] = None
    snapshot_data: Optional[Dict[str, Any]] = None
    captured_at: datetime

    class Config:
        from_attributes = True


class FieldChange(BaseModel):
    """A single field difference between two snapshots"""
    field: str                        # Field name (e.g. "description", "github_url")
    field_label: str                  # Human-readable label (e.g. "Bio / Profil Açıklaması")
    old_value: Optional[str] = None   # Previous value (None if first appearance)
    new_value: Optional[str] = None   # Current value (None if removed)


class ChangeReport(BaseModel):
    """Full change report comparing two snapshots"""
    query_name: str
    previous_captured_at: Optional[datetime] = None
    current_captured_at: datetime
    changes: List[FieldChange]
    snapshot_count: int               # Total number of snapshots for this person
    has_changes: bool                 # True if any fields actually changed
