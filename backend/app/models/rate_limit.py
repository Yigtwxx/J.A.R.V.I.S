from sqlalchemy import Column, Float, Integer, String

from app.database.connection import Base


class RateLimit(Base):
    """Persistent per-IP rate limit records for sliding-window enforcement."""

    __tablename__ = "rate_limits"

    id = Column(Integer, primary_key=True, index=True)
    ip_address = Column(String(45), nullable=False, index=True)
    timestamp = Column(Float, nullable=False, index=True)
