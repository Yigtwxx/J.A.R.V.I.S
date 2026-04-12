import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import get_face_matching_service
from app.middleware.security import verify_api_key
from app.schemas.face_match import FaceMatchReport
from app.utils.logger import logger

router = APIRouter(prefix="/api/face-match", tags=["Face Matching"])

class CompareRequest(BaseModel):
    """Request body for manual face comparison"""
    images: list[dict]  # [{"label": "GitHub", "url": "https://..."}, ...]


@router.post("/compare", response_model=FaceMatchReport)
async def compare_faces(
    request: CompareRequest,
    _api_key: str = Depends(verify_api_key),
    face_service=Depends(get_face_matching_service),
):
    """
    Compare face images from provided URLs.
    Each image should have a 'label' and 'url' field.
    """
    try:
        if len(request.images) < 2:
            raise HTTPException(status_code=400, detail="At least 2 images are required for comparison")

        labeled_images = [(img.get("label", "Unknown"), img.get("url", "")) for img in request.images]
        labeled_images = [(label, url) for label, url in labeled_images if url]

        if len(labeled_images) < 2:
            raise HTTPException(status_code=400, detail="At least 2 valid image URLs are required")

        loop = asyncio.get_running_loop()
        report = await loop.run_in_executor(None, face_service.analyze_all_images, labeled_images)

        if report is None:
            raise HTTPException(status_code=422, detail="Face matching failed — insufficient valid images")

        return report

    except HTTPException:
        raise
    except Exception as e:
        logger.log_error(f"Face match API error: {e}")
        raise HTTPException(status_code=500, detail=f"Face matching failed: {str(e)}") from e
