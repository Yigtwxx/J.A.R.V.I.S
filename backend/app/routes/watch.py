"""
Watch routes — real-time target monitoring and change detection.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.middleware.security import verify_api_key
from app.services.watch_service import watch_service
from app.utils.logger import logger

router = APIRouter(prefix="/api/watch", tags=["watch"])


class WatchRequest(BaseModel):
    query: str = Field(..., description="Target to monitor (name or name/username)")
    interval_minutes: int = Field(default=60, ge=5, le=1440, description="Check interval in minutes")


@router.post("/start")
async def start_watch(
    request: WatchRequest,
    _api_key: str = Depends(verify_api_key),
):
    """Start monitoring a target for changes."""
    logger.log_action(f"Watch mode requested for: {request.query}")
    result = watch_service.start_watch(
        query=request.query,
        interval_minutes=request.interval_minutes,
    )
    return result


@router.post("/stop")
async def stop_watch(
    request: WatchRequest,
    _api_key: str = Depends(verify_api_key),
):
    """Stop monitoring a target."""
    result = watch_service.stop_watch(request.query)
    return result


@router.post("/stop-all")
async def stop_all_watches(
    _api_key: str = Depends(verify_api_key),
):
    """Stop all active watches."""
    count = watch_service.stop_all()
    return {"status": "all_stopped", "count": count}


@router.get("/")
async def list_watches(
    _api_key: str = Depends(verify_api_key),
):
    """List all active watches with their status."""
    watches = watch_service.active_watches
    return {"watches": watches, "count": len(watches)}


@router.get("/{query}")
async def get_watch_status(
    query: str,
    _api_key: str = Depends(verify_api_key),
):
    """Get status of a specific watch."""
    status = watch_service.get_watch_status(query)
    if not status:
        return {"status": "not_found", "query": query}
    return status
