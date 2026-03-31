from sqlalchemy import JSON, Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base


class ProfileSnapshot(Base):
    """
    Stores a snapshot of search results for a person at a specific point in time.
    Used for tracking profile changes across repeated searches (Version History).
    """

    __tablename__ = "profile_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    query_name = Column(String(255), nullable=False, index=True)  # Normalized lowercase search key

    # Social media URLs (mirrored from search results)
    github_url = Column(Text, nullable=True)
    instagram_url = Column(Text, nullable=True)
    twitter_url = Column(Text, nullable=True)
    linkedin_url = Column(Text, nullable=True)
    spotify_url = Column(Text, nullable=True)
    tiktok_url = Column(Text, nullable=True)

    # Profile info
    description = Column(Text, nullable=True)
    additional_info = Column(JSON, nullable=True)

    # Flexible snapshot data (follower counts, job title, location, score, etc.)
    snapshot_data = Column(JSON, nullable=True)

    # Timestamp
    captured_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    def __repr__(self):
        return f"<ProfileSnapshot(id={self.id}, query='{self.query_name}', captured_at={self.captured_at})>"
