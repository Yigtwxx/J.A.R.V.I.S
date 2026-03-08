from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from sqlalchemy.sql import func
from app.database import Base


class Profile(Base):
    """Profile model for storing person information"""
    
    __tablename__ = "profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    
    # Social media URLs
    github_url = Column(Text, nullable=True)
    instagram_url = Column(Text, nullable=True)
    twitter_url = Column(Text, nullable=True)
    linkedin_url = Column(Text, nullable=True)
    spotify_url = Column(Text, nullable=True)
    tiktok_url = Column(Text, nullable=True)
    snapchat_url = Column(Text, nullable=True)
    tumblr_url = Column(Text, nullable=True)
    tinder_mention = Column(Text, nullable=True)
    bumble_mention = Column(Text, nullable=True)
    phone_numbers = Column(JSON, nullable=True)
    
    # Information
    description = Column(Text, nullable=True)
    additional_info = Column(JSON, nullable=True)  # Flexible JSON field
    similar_profiles = Column(JSON, nullable=True)  # List of similar people
    cross_validation_issues = Column(JSON, nullable=True)  # List of data inconsistencies
    network_connections = Column(JSON, nullable=True)  # Array of related entities
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def __repr__(self):
        return f"<Profile(id={self.id}, name='{self.name}')>"
