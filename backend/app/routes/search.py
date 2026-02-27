from fastapi import APIRouter, HTTPException
from app.schemas import SearchQuery, SearchResponse
from app.services import AIService, SearchService, GitHubService, ScraperService
import asyncio

router = APIRouter(prefix="/api/search", tags=["search"])

# Initialize services
ai_service = AIService()
search_service = SearchService()
github_service = GitHubService()
scraper_service = ScraperService()


@router.post("/", response_model=SearchResponse)
async def search_person(query: SearchQuery):
    """
    Search for a person and gather all available information
    
    This endpoint:
    1. Searches GitHub for the person
    2. Scrapes social media profiles (Instagram, Twitter, LinkedIn)
    3. Searches Google for additional information
    4. Uses AI (JARVIS) to compile and present the information
    
    Returns structured profile data ready for user approval
    """
    try:
        name = query.query.strip()
        
        if not name:
            raise HTTPException(status_code=400, detail="Query cannot be empty")
        
        # Initialize context
        context = {}
        
        from app.jarvis_logger import logger
        logger.log_thought(f"Incoming connection detected on secure channel: {name}")
        
        # 1. Search GitHub
        logger.log_action("Querying GitHub central servers...")
        github_data = github_service.search_user(name)
        if github_data:
            context['github'] = github_service.format_github_data(github_data)
            github_url = github_data.get('profile_url')
            logger.log_success(f"GitHub profile found: {github_url}")
        else:
            github_url = None
            logger.log_warning("No GitHub profile found")
        
        # 2. Scrape social media profiles
        logger.log_action("Initiating social media sweep...")
        social_profiles = scraper_service.find_all_profiles(name)
        context['social_media'] = scraper_service.format_social_profiles(social_profiles)
        found_count = sum(1 for v in social_profiles.values() if v)
        logger.log_success(f"Found {found_count} social media profiles")
        
        # 3. Search Google
        logger.log_action("Accessing global data grid...")
        web_results = search_service.search_person(name)
        context['web_search'] = web_results
        logger.log_success("Web search completed")
        
        # 4. Generate AI response
        logger.log_action("Running cognitive analysis...")
        ai_response = await ai_service.generate_response(
            prompt=f"Tell me everything you know about {name}",
            context=context
        )
        logger.log_success("Analysis complete")
        
        # 5. Extract structured data
        structured_data = await ai_service.extract_profile_data(ai_response, name)
        
        # Build response
        response = SearchResponse(
            name=structured_data.get('name', name),
            github_url=github_url,
            instagram_url=social_profiles.get('instagram'),
            twitter_url=social_profiles.get('twitter'),
            linkedin_url=social_profiles.get('linkedin'),
            description=structured_data.get('description'),
            similar_profiles=structured_data.get('similar_profiles', []),
            ai_response=ai_response
        )
        
        logger.log_success(f"SEARCH COMPLETED FOR TARGET: {name}")
        return response
    
    except Exception as e:
        from app.jarvis_logger import logger
        logger.log_error(f"Error during search: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


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
