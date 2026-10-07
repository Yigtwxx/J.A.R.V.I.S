from datetime import datetime

from pydantic import BaseModel

from app.models.discovery import SearchSession


class HistoryResponse(BaseModel):
    """One past conversation, as the Logs panel lists it.

    ``raw_query`` is the first message the user actually typed - the search's own
    ``name`` is the resolved identity and is not what the user would recognise in
    a list.
    """

    session_id: str
    raw_query: str
    started_at: datetime
    status: str
    has_result: bool

    @classmethod
    def from_session(cls, row: SearchSession) -> "HistoryResponse":
        return cls(
            session_id=row.id,
            raw_query=row.raw_query or "",
            started_at=row.started_at,
            status=row.status or "running",
            # bool(), not `is not None`: a failed serialisation stores {} and the
            # result route answers `ready: false` for it.
            has_result=bool(row.result_json),
        )
