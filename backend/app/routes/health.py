"""
Health routes — biometric telemetry and wellness tracking endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.security import verify_api_key
from app.services.health_service import HealthService, HEALTH_CATEGORIES
from app.services.user_memory_service import UserMemoryService

router = APIRouter(prefix="/api/health", tags=["health"])

memory_service = UserMemoryService()
health_service = HealthService(memory_service=memory_service)


class HealthRecordCreate(BaseModel):
    category: str = Field(..., description="Health category (e.g. health_sleep, health_energy)")
    key: str = Field(..., description="Data label (e.g. 'sleep_hours', 'headache')")
    value: str = Field(..., description="Data value (e.g. '6 hours', 'moderate pain')")
    context: str | None = Field(default=None, description="Optional additional context")


class HealthReportQuery(BaseModel):
    report: str = Field(..., description="User health report (e.g. 'I feel tired and have a headache')")


@router.get("/categories")
async def get_categories(_api_key: str = Depends(verify_api_key)):
    """List available health categories."""
    return health_service.get_categories()


@router.post("/record")
async def record_health_data(
    data: HealthRecordCreate,
    db: Session = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
):
    """Record a health data point."""
    try:
        result = health_service.record(db, data.category, data.key, data.value, data.context)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/history")
async def get_health_history(
    category: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
):
    """Retrieve health history, optionally filtered by category."""
    try:
        return health_service.get_history(db, category=category, limit=limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/suggestions")
async def get_health_suggestions(
    query: HealthReportQuery,
    db: Session = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
):
    """Get AI-powered health suggestions based on user report."""
    return await health_service.get_suggestions(db, query.report)


@router.get("/patterns")
async def get_health_patterns(
    db: Session = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
):
    """Detect patterns in health data."""
    return await health_service.detect_patterns(db)
