from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.middleware.security import verify_api_key
from app.services.vision_service import vision_service
from app.utils.logger import logger

router = APIRouter(prefix="/api/vision", tags=["vision"])


class ImageAnalysisRequest(BaseModel):
    image_url: str
    prompt: str | None = None


class SocialPhotoRequest(BaseModel):
    image_url: str


class ScreenshotRequest(BaseModel):
    image_url: str


class FaceCompareRequest(BaseModel):
    image_url_a: str
    image_url_b: str


@router.post("/analyze")
async def analyze_image(request: ImageAnalysisRequest, _api_key: str = Depends(verify_api_key)):
    """General-purpose image analysis using vision model."""
    logger.log_action("Vision analysis requested", target=request.image_url[:80])
    result = await vision_service.analyze_image(
        request.image_url,
        prompt=request.prompt or "Describe this image in detail.",
    )
    return {"analysis": result, "image_url": request.image_url}


@router.post("/social-photo")
async def analyze_social_photo(request: SocialPhotoRequest, _api_key: str = Depends(verify_api_key)):
    """OSINT-focused social media photo analysis."""
    logger.log_action("Social photo OSINT analysis", target=request.image_url[:80])
    result = await vision_service.analyze_social_photo(request.image_url)
    return {"analysis": result, "image_url": request.image_url}


@router.post("/screenshot")
async def read_screenshot(request: ScreenshotRequest, _api_key: str = Depends(verify_api_key)):
    """OCR-like text extraction from a screenshot."""
    logger.log_action("Screenshot OCR requested", target=request.image_url[:80])
    result = await vision_service.read_screenshot(request.image_url)
    return {"text": result, "image_url": request.image_url}


@router.post("/compare-faces")
async def compare_faces_visual(request: FaceCompareRequest, _api_key: str = Depends(verify_api_key)):
    """Visual face comparison using vision model."""
    logger.log_action("Visual face comparison requested")
    result = await vision_service.compare_faces_visual(
        request.image_url_a, request.image_url_b,
    )
    return {"comparison": result}
