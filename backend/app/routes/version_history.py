
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.security import verify_api_key
from app.schemas.snapshot import ChangeReport, SnapshotResponse
from app.services import version_history_service
from app.utils.logger import logger

router = APIRouter(prefix="/api/version-history", tags=["Version History"])


@router.get("/{query_name}", response_model=list[SnapshotResponse])
def get_snapshots(query_name: str, db: Session = Depends(get_db), _api_key: str = Depends(verify_api_key)):
    """Get all snapshots for a person, ordered oldest → newest."""
    try:
        snapshots = version_history_service.get_snapshots(db, query_name)
        if not snapshots:
            raise HTTPException(status_code=404, detail=f"No snapshots found for '{query_name}'")
        return snapshots
    except HTTPException:
        raise
    except Exception as e:
        logger.log_error(f"Error fetching snapshots for '{query_name}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch snapshots: {str(e)}") from e


@router.get("/{query_name}/report", response_model=ChangeReport)
def get_change_report(query_name: str, db: Session = Depends(get_db), _api_key: str = Depends(verify_api_key)):
    """Get the latest change report comparing the two most recent snapshots."""
    try:
        report = version_history_service.generate_change_report(db, query_name)
        if report is None:
            raise HTTPException(status_code=404, detail=f"No snapshots found for '{query_name}'")
        return report
    except HTTPException:
        raise
    except Exception as e:
        logger.log_error(f"Error generating change report for '{query_name}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate change report: {str(e)}") from e
