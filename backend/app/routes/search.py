from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.history import SearchHistory
from app.schemas import SearchQuery, SearchResponse
from app.services import AIService, SearchService, GitHubService, ScraperService, WeatherService
import asyncio

router = APIRouter(prefix="/api/search", tags=["search"])

# Initialize services
ai_service = AIService()
search_service = SearchService()
github_service = GitHubService()
scraper_service = ScraperService()
weather_service = WeatherService()


@router.post("/", response_model=SearchResponse)
async def search_person(query: SearchQuery, db: Session = Depends(get_db)):
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
        raw_query = query.query.strip()
        
        if not raw_query:
            raise HTTPException(status_code=400, detail="Query cannot be empty")
            
        # Parse dual input (e.g., "Yiğit Erdoğan / Yigtwx")
        if "/" in raw_query:
            parts = [p.strip() for p in raw_query.split("/")]
            real_name = parts[0]
            username = parts[1] if len(parts) > 1 else real_name
        else:
            real_name = raw_query
            username = raw_query
        
        # Initialize context
        context = {}
        
        from app.jarvis_logger import logger
        logger.log_thought(f"Incoming connection detected on secure channel: {raw_query}")
        
        # 1. Search GitHub (Prioritize Username)
        logger.log_action("Querying GitHub central servers...")
        github_data = github_service.search_user(username)
        if github_data:
            context['github'] = github_service.format_github_data(github_data)
            github_url = github_data.get('profile_url')
            logger.log_success(f"GitHub profile found: {github_url}")
        else:
            github_url = None
            logger.log_warning("No GitHub profile found")
        
        # 2. Scrape social media profiles (Prioritize Username)
        logger.log_action("Initiating social media sweep...")
        social_profiles = scraper_service.find_all_profiles(username)
        context['social_media'] = scraper_service.format_social_profiles(social_profiles)
        found_count = sum(1 for v in social_profiles.values() if v)
        logger.log_success(f"Found {found_count} social media profiles")
        
        # 3. Search Google (Prioritize Real Name)
        logger.log_action("Accessing global data grid...")
        wiki_image, web_results, deep_context, raw_sources = search_service.search_person(real_name)
        context['web_search'] = web_results
        context['deep_context'] = deep_context
        logger.log_success("Web search aggregation and deep-packet inspection completed")
        
        # 4. Generate AI response (Use Full Context Name)
        logger.log_action("Running cognitive analysis...")
        ai_response = await ai_service.generate_response(
            prompt=f"Tell me everything you know about {raw_query}",
            context=context
        )
        
        # 4.5. Force Image Injection (All Available Visuals)
        images = []
        if wiki_image:
            images.append(wiki_image)
            
        if github_data and github_data.get('avatar_url'):
            images.append(github_data['avatar_url'])
            
        for platform in ['instagram', 'twitter', 'linkedin', 'spotify', 'tiktok']:
            items = social_profiles.get(platform, [])
            if items:
                first_profile_url = items[0]['url'].split(",")[0].strip()
                social_username = first_profile_url.rstrip('/').split('/')[-1]
                images.append(f"https://unavatar.io/{platform}/{social_username}?fallback=false")
                
        # Deduplicate while preserving order
        unique_images = []
        for img in images:
            if img not in unique_images:
                unique_images.append(img)
                
        if unique_images:
            logger.log_success(f"Injecting {len(unique_images[:4])} visual identities.")
            images_md = " ".join([f"![{real_name}]({img})" for img in unique_images[:4]])
            ai_response = f"{images_md}\n\n" + ai_response
            
        logger.log_success("Analysis complete")
        
        # 5. Extract structured data
        structured_data = await ai_service.extract_profile_data(ai_response, real_name)
        
        # 5.5 Fetch Weather for guessed location
        weather_info = None
        if structured_data.get('capital_city'):
            weather_info = weather_service.get_weather(structured_data['capital_city'])

        # Build response
        response = SearchResponse(
            name=structured_data.get('name', real_name),
            github_url=github_url,
            instagram_url=", ".join([p['url'] for p in social_profiles.get('instagram', [])]) or None,
            twitter_url=", ".join([p['url'] for p in social_profiles.get('twitter', [])]) or None,
            linkedin_url=", ".join([p['url'] for p in social_profiles.get('linkedin', [])]) or None,
            spotify_url=", ".join([p['url'] for p in social_profiles.get('spotify', [])]) or None,
            tiktok_url=", ".join([p['url'] for p in social_profiles.get('tiktok', [])]) or None,
            location_country=structured_data.get('estimated_location'),
            location_city=structured_data.get('capital_city'),
            weather_info=weather_info,
            description=structured_data.get('description'),
            similar_profiles=structured_data.get('similar_profiles', []),
            sources=raw_sources,
            ai_response=ai_response
        )
        
        # 6. Save to history
        try:
            history_entry = SearchHistory(query_name=raw_query)
            db.add(history_entry)
            db.commit()
        except Exception as e:
            from app.jarvis_logger import logger
            logger.log_warning(f"Failed to record search history: {e}")
            
        logger.log_success(f"SEARCH COMPLETED FOR TARGET: {raw_query}")
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
