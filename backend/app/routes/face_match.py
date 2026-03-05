from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List

from app.services.face_matching_service import FaceMatchingService
from app.schemas.face_match import FaceMatchReport
from app.utils.logger import logger

router = APIRouter(prefix="/api/face-match", tags=["Face Matching"])

face_service = FaceMatchingService()


class CompareRequest(BaseModel):
    """Request body for manual face comparison"""
    images: List[dict]  # [{"label": "GitHub", "url": "https://..."}, ...]


@router.post("/compare", response_model=FaceMatchReport)
async def compare_faces(request: CompareRequest):
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

        import asyncio
        loop = asyncio.get_event_loop()
        report = await loop.run_in_executor(None, face_service.analyze_all_images, labeled_images)

        if report is None:
            raise HTTPException(status_code=422, detail="Face matching failed — insufficient valid images")

        return report

    except HTTPException:
        raise
    except Exception as e:
        logger.log_error(f"Face match API error: {e}")
        raise HTTPException(status_code=500, detail=f"Face matching failed: {str(e)}")
