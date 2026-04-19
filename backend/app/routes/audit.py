"""
Audit log endpoints — query and clean up the security audit trail.
All endpoints require API key authentication.
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database.connection import get_db
from app.middleware.security import verify_api_key
from app.utils.logger import logger

router = APIRouter(prefix="/api/audit", tags=["audit"])

settings = get_settings()


@router.get("/logs")
async def get_audit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    ip: str | None = Query(None, description="Filter by IP address"),
    endpoint: str | None = Query(None, description="Filter by endpoint substring"),
    since: str | None = Query(None, description="ISO 8601 date lower bound"),
    db: Session = Depends(get_db),
    _api_key: str | None = Depends(verify_api_key),
):
    """Return paginated audit log entries with optional filters."""
    if not settings.audit_log_enabled:
        raise HTTPException(status_code=503, detail="Audit logging is disabled.")

    from app.models.audit_log import AuditLog

    query = db.query(AuditLog)

    if ip:
        query = query.filter(AuditLog.ip_address == ip)
    if endpoint:
        query = query.filter(AuditLog.endpoint.contains(endpoint))
    if since:
        try:
            dt = datetime.fromisoformat(since)
            query = query.filter(AuditLog.timestamp >= dt)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid 'since' format. Use ISO 8601 (e.g. 2026-04-18T00:00:00).",
            )

    total = query.count()
    logs = query.order_by(AuditLog.timestamp.desc()).offset(skip).limit(limit).all()

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "logs": [
            {
                "id": log.id,
                "ip_address": log.ip_address,
                "endpoint": log.endpoint,
                "method": log.method,
                "user_agent": log.user_agent,
                "response_status": log.response_status,
                "duration_ms": log.duration_ms,
                "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                "request_body_size": log.request_body_size,
            }
            for log in logs
        ],
    }


@router.delete("/cleanup")
async def cleanup_audit_logs(
    db: Session = Depends(get_db),
    _api_key: str | None = Depends(verify_api_key),
):
    """Delete audit logs older than retention_days. Returns count of deleted rows."""
    if not settings.audit_log_enabled:
        raise HTTPException(status_code=503, detail="Audit logging is disabled.")

    from app.models.audit_log import AuditLog

    cutoff = datetime.utcnow() - timedelta(days=settings.audit_log_retention_days)
    deleted = db.query(AuditLog).filter(AuditLog.timestamp < cutoff).delete()
    db.commit()
    logger.log_action(
        f"Audit cleanup: deleted {deleted} entries older than "
        f"{settings.audit_log_retention_days} days"
    )
    return {"deleted": deleted, "cutoff": cutoff.isoformat()}
