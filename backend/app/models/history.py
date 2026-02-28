from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.database import Base

class SearchHistory(Base):
    """Model for storing recent search queries. Deleted after 1 week."""
    
    __tablename__ = "search_history"
    
    id = Column(Integer, primary_key=True, index=True)
    query_name = Column(String(255), nullable=False, index=True)
    searched_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    def __repr__(self):
        return f"<SearchHistory(id={self.id}, query='{self.query_name}')>"
