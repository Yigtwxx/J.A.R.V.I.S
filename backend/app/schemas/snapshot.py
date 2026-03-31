from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SnapshotResponse(BaseModel):
    """Serialized snapshot data"""
    id: int
    query_name: str
    github_url: str | None = None
    instagram_url: str | None = None
    twitter_url: str | None = None
    linkedin_url: str | None = None
    spotify_url: str | None = None
    tiktok_url: str | None = None
    description: str | None = None
    additional_info: dict[str, Any] | None = None
    snapshot_data: dict[str, Any] | None = None
    captured_at: datetime

    class Config:
        from_attributes = True


class FieldChange(BaseModel):
    """A single field difference between two snapshots"""
    field: str                        # Field name (e.g. "description", "github_url")
    field_label: str                  # Human-readable label (e.g. "Bio / Profil Açıklaması")
    old_value: str | None = None   # Previous value (None if first appearance)
    new_value: str | None = None   # Current value (None if removed)


class ChangeReport(BaseModel):
    """Full change report comparing two snapshots"""
    query_name: str
    previous_captured_at: datetime | None = None
    current_captured_at: datetime
    changes: list[FieldChange]
    snapshot_count: int               # Total number of snapshots for this person
    has_changes: bool                 # True if any fields actually changed
