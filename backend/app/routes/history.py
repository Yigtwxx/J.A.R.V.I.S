from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.security import verify_api_key
from app.models.history import SearchHistory
from app.schemas.history import HistoryResponse
from app.utils.logger import logger

router = APIRouter(prefix="/api/history", tags=["History"])

def cleanup_old_history(db: Session):
    """Delete history older than 7 days"""
    try:
        one_week_ago = datetime.now(UTC) - timedelta(days=7)
        deleted = db.query(SearchHistory).filter(SearchHistory.searched_at < one_week_ago).delete()
        if deleted > 0:
            logger.log_action(f"Cleaned up {deleted} old history records")
    except Exception as e:
        logger.log_error(f"Failed to cleanup old history: {str(e)}")

@router.get("/", response_model=list[HistoryResponse])
def get_history(db: Session = Depends(get_db), _api_key: str = Depends(verify_api_key)):
    """Get all search history ordered by newest first, removing duplicates."""
    cleanup_old_history(db)

    records = db.query(SearchHistory).order_by(SearchHistory.searched_at.desc()).all()

    # Deduplicate by query name for the UI, keeping the newest one
    seen = set()
    unique_records = []
    for r in records:
        key = r.query_name.lower().strip()
        if key not in seen:
            seen.add(key)
            unique_records.append(r)

    return unique_records

@router.delete("/{history_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_history_item(history_id: int, db: Session = Depends(get_db), _api_key: str = Depends(verify_api_key)):
    """Delete a specific history item"""
    record = db.query(SearchHistory).filter(SearchHistory.id == history_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="History not found")
    db.delete(record)
    logger.log_action(f"Deleted history record {history_id}")
    return {"ok": True}

@router.delete("/", status_code=status.HTTP_204_NO_CONTENT)
def clear_all_history(db: Session = Depends(get_db), _api_key: str = Depends(verify_api_key)):
    """Clear all history"""
    db.query(SearchHistory).delete()
    logger.log_action("Cleared all query history")
    return {"ok": True}
