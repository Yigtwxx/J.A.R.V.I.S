"""
Centralized dependency-injection providers for FastAPI routes.

Usage in route files:
    from app.dependencies import get_ai_service, get_memory_service

    @router.post("/")
    async def endpoint(ai: AIService = Depends(get_ai_service)):
        ...

Each provider uses @lru_cache(maxsize=1) to ensure singleton behavior —
the service is created once on first request, not at import time.
"""

from functools import lru_cache


@lru_cache(maxsize=1)
def get_ai_service():
    from app.services.ai_service import AIService

    return AIService()


@lru_cache(maxsize=1)
def get_memory_service():
    from app.services.user_memory_service import UserMemoryService

    return UserMemoryService()


@lru_cache(maxsize=1)
def get_search_service():
    from app.services.search_service import SearchService

    return SearchService()


@lru_cache(maxsize=1)
def get_github_service():
    from app.services.github_service import GitHubService

    return GitHubService()


@lru_cache(maxsize=1)
def get_scraper_service():
    from app.services.scraper_service import ScraperService

    return ScraperService()


@lru_cache(maxsize=1)
def get_weather_service():
    from app.services.weather_service import WeatherService

    return WeatherService()


@lru_cache(maxsize=1)
def get_social_score_service():
    from app.services.social_score_service import SocialScoreService

    return SocialScoreService()


@lru_cache(maxsize=1)
def get_face_matching_service():
    from app.services.face_matching_service import FaceMatchingService

    return FaceMatchingService()


@lru_cache(maxsize=1)
def get_health_service():
    from app.services.health_service import HealthService

    return HealthService(memory_service=get_memory_service())


@lru_cache(maxsize=1)
def get_agent_loop():
    from app.agents.agent_loop import AgentLoop
    from app.agents.tools.osint_tools import build_osint_registry

    registry = build_osint_registry()
    return AgentLoop(registry=registry)


@lru_cache(maxsize=1)
def get_search_orchestration():
    from app.agents.orchestrator import SearchOrchestrator
    from app.services.search_orchestration_service import SearchOrchestrationService
    from app.services.breach_service import breach_service
    from app.services.company_service import company_service
    from app.services.darkweb_service import darkweb_service
    from app.services.geoint_service import geoint_service
    from app.services.psychological_analysis_service import psychological_analysis_service
    from app.services.predictive_analysis_service import predictive_analysis_service
    from app.services import version_history_service
    from app.utils.logger import logger

    ai = get_ai_service()
    search = get_search_service()
    github = get_github_service()
    scraper = get_scraper_service()
    weather = get_weather_service()
    social_score = get_social_score_service()
    face_matching = get_face_matching_service()

    search_orchestrator = SearchOrchestrator(
        scraper_service=scraper,
        company_service=company_service,
        search_service=search,
        breach_service=breach_service,
        status_callback=logger.broadcast,
    )

    return SearchOrchestrationService(
        ai_service=ai,
        search_service=search,
        github_service=github,
        scraper_service=scraper,
        weather_service=weather,
        social_score_service=social_score,
        face_matching_service=face_matching,
        search_orchestrator=search_orchestrator,
        version_history_service=version_history_service,
        breach_orchestrator=search_orchestrator,
        darkweb_service=darkweb_service,
        geoint_service=geoint_service,
        psychological_service=psychological_analysis_service,
        predictive_service=predictive_analysis_service,
    )
