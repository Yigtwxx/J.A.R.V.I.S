import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agents.orchestrator import SearchOrchestrator
from app.database import get_db
from app.middleware.security import verify_api_key
from app.schemas import SearchQuery, SearchResponse
from app.services.depth_config import DepthConfig
from app.services import (
    AIService,
    GitHubService,
    ScraperService,
    SearchService,
    SocialScoreService,
    WeatherService,
    version_history_service,
)
from app.services.breach_service import breach_service
from app.services.company_service import company_service
from app.services.face_matching_service import FaceMatchingService
from app.services.darkweb_service import darkweb_service
from app.services.geoint_service import geoint_service
from app.services.psychological_analysis_service import psychological_analysis_service
from app.services.predictive_analysis_service import predictive_analysis_service
from app.services.search_orchestration_service import SearchOrchestrationService
from app.utils.logger import logger

router = APIRouter(prefix="/api/search", tags=["search"])

# Initialize services
ai_service = AIService()
search_service = SearchService()
github_service = GitHubService()
scraper_service = ScraperService()
weather_service = WeatherService()
social_score_service = SocialScoreService()
face_matching_service = FaceMatchingService()

search_orchestrator = SearchOrchestrator(
    scraper_service=scraper_service,
    company_service=company_service,
    search_service=search_service,
    breach_service=breach_service,
    status_callback=logger.broadcast,
)

orchestration = SearchOrchestrationService(
    ai_service=ai_service,
    search_service=search_service,
    github_service=github_service,
    scraper_service=scraper_service,
    weather_service=weather_service,
    social_score_service=social_score_service,
    face_matching_service=face_matching_service,
    search_orchestrator=search_orchestrator,
    version_history_service=version_history_service,
    breach_orchestrator=search_orchestrator,
    darkweb_service=darkweb_service,
    geoint_service=geoint_service,
    psychological_service=psychological_analysis_service,
    predictive_service=predictive_analysis_service,
)


@router.post("/", response_model=SearchResponse)
async def search_person(
    query: SearchQuery,
    db: Session = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
):
    """
    Search for a person and gather all available information.

    Pipeline: parse -> fetch -> process -> analyze -> build -> save -> return.
    """
    try:
        raw_query = query.query.strip()
        if not raw_query:
            raise HTTPException(status_code=400, detail="Query cannot be empty")

        depth_config = DepthConfig(query.depth)
        logger.log_thought(f"Incoming connection detected on secure channel: {raw_query}")
        logger.log_action(f"Search depth: {depth_config.depth} ({depth_config.tier})")

        # 1. Parse query
        real_name, username = orchestration.parse_query(raw_query)

        # 2. Parallel data fetching (120s timeout)
        orch_result, github_data, search_results = await asyncio.wait_for(
            orchestration.fetch_parallel_data(
                real_name, username, depth_config=depth_config,
            ),
            timeout=120,
        )
        social_profiles = orch_result.social_profiles
        wiki_image = search_results[0]

        # 3. Process results
        context, deep_context, github_url, raw_sources = orchestration.process_results(
            orch_result, github_data, search_results
        )

        # 4. Save context (JSON + ChromaDB)
        orchestration.save_context(raw_query, context)

        # 5. Collect images
        images = orchestration.collect_images(social_profiles, github_data, wiki_image, real_name)
        face_images = orchestration.collect_face_images(social_profiles, github_data, wiki_image)

        # 6. AI analysis + face match + sentiment (90s timeout)
        ai_response, face_match_report, sentiment_report = await asyncio.wait_for(
            orchestration.run_analysis(
                raw_query, context, deep_context, face_images
            ),
            timeout=90,
        )

        # 7. Post-analysis (structured data, breach, cross-validation, score, psych, prediction) (90s timeout)
        post = await asyncio.wait_for(
            orchestration.run_post_analysis(
                ai_response, real_name, username, github_data,
                social_profiles, search_results[1], raw_sources, orch_result,
                context=context, deep_context=deep_context, sentiment_report=sentiment_report,
            ),
            timeout=90,
        )

        # 8. Build response
        response = orchestration.build_response(
            ai_response, real_name, github_url, social_profiles,
            images, post, raw_sources, github_data, orch_result,
            face_match_report, sentiment_report, depth_config=depth_config,
        )

        # 9. Save history
        orchestration.save_history(db, raw_query, response)

        logger.log_success(f"SEARCH COMPLETED FOR TARGET: {raw_query}")
        return response

    except asyncio.TimeoutError:
        logger.log_error(f"Search timed out for: {raw_query}")
        raise HTTPException(
            status_code=504,
            detail="Search timed out. Try again with lower search depth.",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.log_error(f"Error during search: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}") from e


@router.get("/test")
async def test_search():
    """Test endpoint to verify search API is working"""
    return {
        "status": "ok",
        "message": "JARVIS search API is operational",
        "services": {
            "ai": "Ollama",
            "search": "Google Scraping",
            "github": "GitHub API",
            "social": "Web Scraping"
        }
    }


@router.get("/test-scraper")
async def test_scraper(q: str = "Elon Musk"):
    """Debug endpoint — run the scraper and return raw results."""
    try:
        results = scraper_service.find_all_profiles(q)
        return {
            "query": q,
            "found_count": sum(1 for v in results.values() if v),
            "profiles": {k: v for k, v in results.items() if v},
            "empty_platforms": [k for k, v in results.items() if not v],
        }
    except Exception as e:
        return {"error": str(e)}
