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
        
        print(f"\n{'='*60}")
        print(f"🔍 NEW SEARCH REQUEST: {name}")
        print(f"{'='*60}")
        
        # 1. Search GitHub
        print(f"[1/4] 🐙 Searching GitHub...")
        github_data = github_service.search_user(name)
        if github_data:
            context['github'] = github_service.format_github_data(github_data)
            github_url = github_data.get('profile_url')
            print(f"      ✅ GitHub profile found: {github_url}")
        else:
            github_url = None
            print(f"      ⚠️  No GitHub profile found")
        
        # 2. Scrape social media profiles
        print(f"[2/4] 📱 Searching social media...")
        social_profiles = scraper_service.find_all_profiles(name)
        context['social_media'] = scraper_service.format_social_profiles(social_profiles)
        found_count = sum(1 for v in social_profiles.values() if v)
        print(f"      ✅ Found {found_count} social media profiles")
        
        # 3. Search Google
        print(f"[3/4] 🌐 Searching Google...")
        web_results = search_service.search_person(name)
        context['web_search'] = web_results
        print(f"      ✅ Web search completed")
        
        # 4. Generate AI response
        print(f"[4/4] 🤖 JARVIS analyzing data...")
        ai_response = await ai_service.generate_response(
            prompt=f"Tell me everything you know about {name}",
            context=context
        )
        print(f"      ✅ Analysis complete")
        
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
        
        print(f"\n✅ SEARCH COMPLETED: {name}")
        print(f"{'='*60}\n")
        return response
    
    except Exception as e:
        print(f"❌ Error during search: {e}")
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
