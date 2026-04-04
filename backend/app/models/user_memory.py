"""
UserMemory — stores user preferences, past interactions, and behavioral patterns.

Enables J.A.R.V.I.S to recognize and adapt to the user over time.
"""
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.database.connection import Base


class UserMemory(Base):
    """Persistent user memory record."""
    __tablename__ = "user_memories"

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String(50), nullable=False, index=True)  # preference, fact, interaction, personality
    key = Column(String(200), nullable=False, index=True)
    value = Column(Text, nullable=False)
    context = Column(Text, nullable=True)  # optional context about when/how this was learned
    importance = Column(Integer, default=5)  # 1-10 scale, higher = more important
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
