"""Visual Intelligence routes — public webcams near a place and latest public images."""

import asyncio

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.middleware.security import verify_api_key
from app.services.search_service import SearchService
from app.services.webcam_service import webcam_service
from app.utils.logger import logger

router = APIRouter(prefix="/api/visual-intel", tags=["visual-intel"])

_search = SearchService()


class QueryRequest(BaseModel):
    query: str


@router.post("/cameras")
async def location_cameras(request: QueryRequest, _api_key: str = Depends(verify_api_key)):
    """Find PUBLIC live webcams near a searched place (publisher-streamed cams only)."""
    logger.log_action("Public webcam lookup", target=request.query[:80])
    data = await webcam_service.find_public_webcams(request.query)
    return data


@router.post("/images")
async def latest_images(request: QueryRequest, _api_key: str = Depends(verify_api_key)):
    """Fetch the latest publicly published images for a person or place."""
    logger.log_action("Latest image search", target=request.query[:80])
    loop = asyncio.get_running_loop()
    images = await loop.run_in_executor(None, _search.search_images, request.query)
    return {"images": images, "query": request.query}
