from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.middleware.security import verify_api_key
from app.services.vision_service import (
    VisionImageError,
    VisionUnavailableError,
    vision_service,
)
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


def _fail(exc: Exception) -> HTTPException:
    """Turn a vision failure into a status code that says which side broke.

    Until 2026-08-29 these handlers returned the failure text in the success
    body, so a model that could not load answered 200 with prose that read like
    a description. 503 vs 502 keeps "I could not look" separable from "there was
    nothing to look at".
    """
    if isinstance(exc, VisionUnavailableError):
        logger.log_warning(f"Vision model unavailable: {exc}", broadcast=False)
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=502, detail=str(exc))


@router.post("/analyze")
async def analyze_image(request: ImageAnalysisRequest, _api_key: str = Depends(verify_api_key)):
    """General-purpose image analysis using vision model."""
    logger.log_action("Vision analysis requested", target=request.image_url[:80])
    try:
        result = await vision_service.analyze_image(
            request.image_url,
            prompt=request.prompt or "Describe this image in detail.",
        )
    except (VisionUnavailableError, VisionImageError) as exc:
        raise _fail(exc) from exc
    return {"analysis": result, "image_url": request.image_url}


@router.post("/social-photo")
async def analyze_social_photo(request: SocialPhotoRequest, _api_key: str = Depends(verify_api_key)):
    """OSINT-focused social media photo analysis."""
    logger.log_action("Social photo OSINT analysis", target=request.image_url[:80])
    try:
        result = await vision_service.analyze_social_photo(request.image_url)
    except (VisionUnavailableError, VisionImageError) as exc:
        raise _fail(exc) from exc
    return {"analysis": result, "image_url": request.image_url}


@router.post("/screenshot")
async def read_screenshot(request: ScreenshotRequest, _api_key: str = Depends(verify_api_key)):
    """OCR-like text extraction from a screenshot."""
    logger.log_action("Screenshot OCR requested", target=request.image_url[:80])
    try:
        result = await vision_service.read_screenshot(request.image_url)
    except (VisionUnavailableError, VisionImageError) as exc:
        raise _fail(exc) from exc
    return {"text": result, "image_url": request.image_url}


@router.post("/compare-faces")
async def compare_faces_visual(request: FaceCompareRequest, _api_key: str = Depends(verify_api_key)):
    """Visual face comparison using vision model."""
    logger.log_action("Visual face comparison requested")
    try:
        result = await vision_service.compare_faces_visual(
            request.image_url_a,
            request.image_url_b,
        )
    except (VisionUnavailableError, VisionImageError) as exc:
        raise _fail(exc) from exc
    return {"comparison": result}
