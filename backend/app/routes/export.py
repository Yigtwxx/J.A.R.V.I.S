"""
Export routes — PDF, JSON, CSV dossier generation from saved profiles or search results.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.security import verify_api_key
from app.models.profile import Profile
from app.services.report_service import report_service
from app.utils.logger import logger

router = APIRouter(prefix="/api/export", tags=["export"])

MAX_EXPORT_BODY_BYTES = 1_048_576  # 1 MB


async def _enforce_body_limit(request: Request):
    """Reject export payloads larger than 1 MB."""
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > MAX_EXPORT_BODY_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail="Request body too large (max 1 MB).",
                )
        except ValueError:
            pass  # malformed header — let FastAPI handle it


def _get_profile_dict(profile_id: int, db: Session) -> dict:
    """Load a saved profile and return it as a dict."""
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    # Convert SQLAlchemy model to dict
    data = {c.name: getattr(profile, c.name) for c in profile.__table__.columns}
    # Include JSON fields stored in additional_info
    if data.get("additional_info") and isinstance(data["additional_info"], dict):
        for key in ("ai_response", "sources", "sentiment_analysis", "face_match_results",
                     "social_media_score", "social_media_score_breakdown", "platform_activity",
                     "last_activity_summary", "location_country", "location_city", "weather_info",
                     "company_records"):
            if key in data["additional_info"] and key not in data:
                data[key] = data["additional_info"][key]
    return data


@router.get("/pdf/{profile_id}")
async def export_pdf(
    profile_id: int,
    db: Session = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
):
    """Export a saved profile as a classified PDF dossier."""
    logger.log_action(f"Generating PDF dossier for profile #{profile_id}")
    data = _get_profile_dict(profile_id, db)
    pdf_bytes = report_service.export_pdf(data)
    safe_name = data.get("name", "target").replace(" ", "_")
    logger.log_success(f"PDF dossier generated: {safe_name}")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="JARVIS_Dossier_{safe_name}.pdf"'},
    )


@router.get("/json/{profile_id}")
async def export_json(
    profile_id: int,
    db: Session = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
):
    """Export a saved profile as structured JSON."""
    logger.log_action(f"Generating JSON export for profile #{profile_id}")
    data = _get_profile_dict(profile_id, db)
    json_str = report_service.export_json(data)
    safe_name = data.get("name", "target").replace(" ", "_")
    return Response(
        content=json_str,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="JARVIS_Intel_{safe_name}.json"'},
    )


@router.get("/csv/{profile_id}")
async def export_csv(
    profile_id: int,
    db: Session = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
):
    """Export a saved profile as CSV (Maltego/i2 compatible)."""
    logger.log_action(f"Generating CSV export for profile #{profile_id}")
    data = _get_profile_dict(profile_id, db)
    csv_str = report_service.export_csv(data)
    safe_name = data.get("name", "target").replace(" ", "_")
    return Response(
        content=csv_str,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="JARVIS_Data_{safe_name}.csv"'},
    )


@router.post("/pdf")
async def export_pdf_from_data(
    profile: dict,
    _api_key: str = Depends(verify_api_key),
    _limit: None = Depends(_enforce_body_limit),
):
    """Export a search result (not saved) directly as PDF."""
    logger.log_action("Generating PDF dossier from live search data")
    pdf_bytes = report_service.export_pdf(profile)
    safe_name = profile.get("name", "target").replace(" ", "_")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="JARVIS_Dossier_{safe_name}.pdf"'},
    )


@router.post("/json")
async def export_json_from_data(
    profile: dict,
    _api_key: str = Depends(verify_api_key),
    _limit: None = Depends(_enforce_body_limit),
):
    """Export live search result as JSON."""
    json_str = report_service.export_json(profile)
    safe_name = profile.get("name", "target").replace(" ", "_")
    return Response(
        content=json_str,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="JARVIS_Intel_{safe_name}.json"'},
    )


@router.post("/csv")
async def export_csv_from_data(
    profile: dict,
    _api_key: str = Depends(verify_api_key),
    _limit: None = Depends(_enforce_body_limit),
):
    """Export live search result as CSV."""
    csv_str = report_service.export_csv(profile)
    safe_name = profile.get("name", "target").replace(" ", "_")
    return Response(
        content=csv_str,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="JARVIS_Data_{safe_name}.csv"'},
    )
