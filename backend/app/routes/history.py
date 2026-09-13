from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.security import verify_api_key
from app.schemas.history import HistoryResponse
from app.services.history_service import (
    clear_conversations,
    delete_conversation,
    get_conversation,
    list_conversations,
)
from app.utils.logger import logger

router = APIRouter(prefix="/api/history", tags=["History"])


@router.get("/", response_model=list[HistoryResponse])
def get_history(
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> list[HistoryResponse]:
    """Past conversations, newest first.

    Not deduplicated: two searches for the same person are two conversations.
    """
    return [HistoryResponse.from_session(row) for row in list_conversations(db, limit=limit)]


@router.get("/{session_id}", response_model=HistoryResponse)
def get_history_item(
    session_id: str,
    db: Session = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> HistoryResponse:
    """One conversation.

    The frontend restores a `?s=` link with this: the saved profile carries only
    the resolved name, never the raw text the user typed, so the first message
    cannot be recovered from the result alone.
    """
    row = get_conversation(db, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return HistoryResponse.from_session(row)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_history_item(
    session_id: str,
    db: Session = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> Response:
    """Delete one conversation. Its evidence is detached, not deleted."""
    if not delete_conversation(db, session_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    logger.log_action(f"Deleted conversation {session_id[:8]}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def clear_all_history(
    db: Session = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> Response:
    """Delete every conversation."""
    count = clear_conversations(db)
    logger.log_action(f"Cleared {count} conversation(s)")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
