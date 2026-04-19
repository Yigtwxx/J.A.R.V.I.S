from sqlalchemy import Column, DateTime, Float, Integer, String
from sqlalchemy.sql import func

from app.database.connection import Base


class AuditLog(Base):
    """Security audit trail — records every non-exempt HTTP request."""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    ip_address = Column(String(45))
    endpoint = Column(String(500))
    method = Column(String(10))
    user_agent = Column(String(500))
    response_status = Column(Integer)
    duration_ms = Column(Float)
    timestamp = Column(DateTime, server_default=func.now(), index=True)
    request_body_size = Column(Integer)
