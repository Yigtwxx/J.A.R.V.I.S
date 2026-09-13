"""
Health routes — biometric telemetry and wellness tracking endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_health_service
from app.middleware.security import verify_api_key

router = APIRouter(prefix="/api/health", tags=["health"])


class HealthRecordCreate(BaseModel):
    category: str = Field(..., description="Health category (e.g. health_sleep, health_energy)")
    key: str = Field(..., description="Data label (e.g. 'sleep_hours', 'headache')")
    value: str = Field(..., description="Data value (e.g. '6 hours', 'moderate pain')")
    context: str | None = Field(default=None, description="Optional additional context")


class HealthReportQuery(BaseModel):
    report: str = Field(..., description="User health report (e.g. 'I feel tired and have a headache')")


@router.get("/categories")
async def get_categories(
    _api_key: str = Depends(verify_api_key),
    health_service=Depends(get_health_service),
):
    """List available health categories."""
    return health_service.get_categories()


@router.post("/record")
async def record_health_data(
    data: HealthRecordCreate,
    db: Session = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
    health_service=Depends(get_health_service),
):
    """Record a health data point."""
    try:
        result = health_service.record(db, data.category, data.key, data.value, data.context)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/history")
async def get_health_history(
    category: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
    health_service=Depends(get_health_service),
):
    """Retrieve health history, optionally filtered by category."""
    try:
        return health_service.get_history(db, category=category, limit=limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/record/{record_id}")
async def delete_health_record(
    record_id: int,
    db: Session = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
    health_service=Depends(get_health_service),
):
    """Delete a single health record."""
    try:
        deleted = health_service.delete(db, record_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Health record {record_id} not found")
    return {"status": "deleted", "id": record_id}


@router.post("/suggestions")
async def get_health_suggestions(
    query: HealthReportQuery,
    db: Session = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
    health_service=Depends(get_health_service),
):
    """Get AI-powered health suggestions based on user report."""
    return await health_service.get_suggestions(db, query.report)


@router.get("/patterns")
async def get_health_patterns(
    db: Session = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
    health_service=Depends(get_health_service),
):
    """Detect patterns in health data."""
    return await health_service.detect_patterns(db)
