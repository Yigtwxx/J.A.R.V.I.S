from datetime import datetime

from pydantic import BaseModel


class HistoryResponse(BaseModel):
    """Schema for returning search history"""
    id: int
    query_name: str
    searched_at: datetime

    class Config:
        from_attributes = True
