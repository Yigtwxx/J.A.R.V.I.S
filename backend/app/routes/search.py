import asyncio

from cachetools import TTLCache
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_search_orchestration, get_scraper_service
from app.middleware.security import verify_api_key
from app.schemas import SearchQuery, SearchResponse
from app.services.depth_config import DepthConfig
from app.utils.logger import logger

router = APIRouter(prefix="/api/search", tags=["search"])

_settings = get_settings()

# In-memory cache: normalized query -> SearchResponse
_search_cache: TTLCache = TTLCache(
    maxsize=_settings.search_cache_max_size,
    ttl=_settings.search_cache_ttl_seconds,
)


def _cache_key(query: str, depth: int) -> str:
    """Normalize query into a stable cache key."""
    return f"{' '.join(query.lower().strip().split())}::{depth}"


@router.post("/", response_model=SearchResponse)
async def search_person(
    query: SearchQuery,
    db: Session = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
    orchestration=Depends(get_search_orchestration),
):
    """
    Search for a person and gather all available information.

    Pipeline: parse -> fetch -> process -> analyze -> build -> save -> return.
    """
    current_step = "init"
    try:
        raw_query = query.query.strip()
        if not raw_query:
            raise HTTPException(status_code=400, detail="Query cannot be empty")

        # Check cache before running the full pipeline
        cache_key = _cache_key(raw_query, query.depth)
        cached = _search_cache.get(cache_key)
        if cached is not None:
            logger.log_success(f"Cache hit for: {raw_query}")
            return cached

        depth_config = DepthConfig(query.depth)
        logger.log_thought(f"Incoming connection detected on secure channel: {raw_query}")
        logger.log_action(f"Search depth: {depth_config.depth} ({depth_config.tier})")

        # 1. Parse query
        real_name, username = orchestration.parse_query(raw_query)

        # 2. Parallel data fetching (no orchestration timeout — deep scans sweep
        # many sources; per-source HTTP timeouts still bound each request)
        current_step = "data_fetch"
        orch_result, github_data, search_results = await orchestration.fetch_parallel_data(
            real_name,
            username,
            depth_config=depth_config,
        )
        social_profiles = orch_result.social_profiles
        wiki_image = search_results[0]

        # 3. Process results
        context, deep_context, github_url, raw_sources = orchestration.process_results(
            orch_result, github_data, search_results, real_name
        )

        # 4. Save context (JSON + ChromaDB)
        orchestration.save_context(raw_query, context)

        # 5. Collect images
        images = orchestration.collect_images(social_profiles, github_data, wiki_image, real_name)
        face_images = orchestration.collect_face_images(social_profiles, github_data, wiki_image)

        # 6. AI analysis + face match + sentiment (no timeout — local LLM streams
        # can run long on deep contexts)
        current_step = "ai_analysis"
        ai_response, face_match_report, sentiment_report = await orchestration.run_analysis(
            raw_query, context, deep_context, face_images
        )

        # 7. Post-analysis (structured data, breach, cross-validation, score, psych, prediction)
        current_step = "post_analysis"
        post = await orchestration.run_post_analysis(
            ai_response,
            real_name,
            username,
            github_data,
            social_profiles,
            search_results[1],
            raw_sources,
            orch_result,
            context=context,
            deep_context=deep_context,
            sentiment_report=sentiment_report,
        )

        # 8. Build response
        response = orchestration.build_response(
            ai_response,
            real_name,
            github_url,
            social_profiles,
            images,
            post,
            raw_sources,
            github_data,
            orch_result,
            face_match_report,
            sentiment_report,
            depth_config=depth_config,
        )

        # 9. Save history
        orchestration.save_history(db, raw_query, response)

        # Store in cache
        _search_cache[cache_key] = response

        logger.log_success(f"SEARCH COMPLETED FOR TARGET: {raw_query}")
        return response

    except asyncio.TimeoutError:
        step_messages = {
            "data_fetch": "Data collection timed out. The target may have too many online profiles to scan.",
            "ai_analysis": "AI analysis timed out. The language model is taking too long to respond. Try reducing search depth.",
            "post_analysis": "Post-analysis timed out. Try again with a lower search depth.",
        }
        detail = step_messages.get(current_step, "Search timed out. Try again with lower search depth.")
        logger.log_error(f"Search timed out at step '{current_step}' for: {raw_query}")
        raise HTTPException(status_code=504, detail=detail)
    except HTTPException:
        raise
    except Exception as e:
        # Log the raw error server-side, but do not leak internal exception
        # details (paths, library internals) to the client.
        logger.log_error(f"Error during search: {e}")
        raise HTTPException(
            status_code=500,
            detail="Search failed due to an internal error. Please try again.",
        ) from e


@router.get("/test")
async def test_search(_api_key: str = Depends(verify_api_key)):
    """Test endpoint to verify search API is working (debug mode only)"""
    if not _settings.debug:
        raise HTTPException(status_code=404, detail="Not found")
    return {
        "status": "ok",
        "message": "JARVIS search API is operational",
        "services": {"ai": "Ollama", "search": "Google Scraping", "github": "GitHub API", "social": "Web Scraping"},
    }


@router.get("/test-scraper")
async def test_scraper(
    q: str = "Elon Musk",
    _api_key: str = Depends(verify_api_key),
    scraper_service=Depends(get_scraper_service),
):
    """Debug endpoint — run the scraper and return raw results."""
    if not _settings.debug:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        results = await asyncio.to_thread(scraper_service.find_all_profiles, q)
        return {
            "query": q,
            "found_count": sum(1 for v in results.values() if v),
            "profiles": {k: v for k, v in results.items() if v},
            "empty_platforms": [k for k, v in results.items() if not v],
        }
    except Exception as e:
        return {"error": str(e)}
