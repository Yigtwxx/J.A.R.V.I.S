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


def cross_validate(github_data: dict, social_profiles: dict, web_results: str, real_name: str) -> list[str]:
    """
    Algorithmically cross-validate data from different sources.
    Returns a list of detected inconsistency strings.
    """
    issues = []

    # --- 1. GitHub Location vs Web Results Location ---
    if github_data:
        gh_location = (github_data.get('location') or '').strip().lower()
        if gh_location and web_results:
            # Check if GitHub's stated location appears anywhere in web results
            web_lower = web_results.lower()
            if gh_location and len(gh_location) > 2 and gh_location not in web_lower:
                issues.append(
                    f"GitHub location is '{github_data.get('location')}' but web search results don't mention this location."
                )

    # --- 2. GitHub Display Name vs Searched Name ---
    if github_data:
        gh_name = (github_data.get('name') or '').strip().lower()
        search_name_lower = real_name.strip().lower()
        if gh_name and search_name_lower:
            # Check if the names share any common word (at least one word overlap)
            gh_words = set(gh_name.split())
            search_words = set(search_name_lower.split())
            if gh_words and search_words and not gh_words.intersection(search_words):
                issues.append(
                    f"GitHub display name '{github_data.get('name')}' has no common words with searched name '{real_name}'. Possible identity mismatch."
                )

    # --- 3. Social media platform count vs web presence ---
    found_platforms = [k for k, v in social_profiles.items() if v]
    if not found_platforms and web_results and len(web_results) > 500:
        issues.append(
            "No social media profiles were found, but significant web results exist. The person may use different usernames online."
        )

    # --- 4. GitHub bio vs social media bio mismatch ---
    if github_data:
        gh_bio = (github_data.get('bio') or '').strip().lower()
        if gh_bio and len(gh_bio) > 10:
            # Check if LinkedIn profiles exist and if there's a role keyword mismatch
            linkedin_profiles = social_profiles.get('linkedin', [])
            if linkedin_profiles:
                linkedin_url = linkedin_profiles[0].get('url', '').lower()
                # Simple heuristic: if GitHub bio says "student" but LinkedIn suggests professional role
                student_keywords = ['student', 'öğrenci', 'university', 'üniversite']
                pro_keywords = ['ceo', 'founder', 'engineer', 'manager', 'director', 'lead']
                is_student_gh = any(kw in gh_bio for kw in student_keywords)
                is_pro_gh = any(kw in gh_bio for kw in pro_keywords)
                if is_student_gh and is_pro_gh:
                    issues.append(
                        f"GitHub bio contains both student and professional keywords, which may indicate outdated profile information."
                    )

    return issues


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
        
        # === PARALLEL DATA FETCHING ===
        # Run GitHub, social media, and web search concurrently
        loop = asyncio.get_event_loop()
        
        logger.log_action("Launching parallel intelligence gathering...")
        
        github_future = loop.run_in_executor(None, github_service.search_user, username)
        social_future = loop.run_in_executor(None, scraper_service.find_all_profiles, username)
        search_future = loop.run_in_executor(None, search_service.search_person, real_name)
        
        github_data, social_profiles, search_results = await asyncio.gather(
            github_future, social_future, search_future
        )
        
        wiki_image, web_results, deep_context, raw_sources = search_results
        
        # Process GitHub results
        if github_data:
            context['github'] = github_service.format_github_data(github_data)
            github_url = github_data.get('profile_url')
            logger.log_success(f"GitHub profile found: {github_url}")
        else:
            github_url = None
            logger.log_warning("No GitHub profile found")
        
        # Process social media results
        context['social_media'] = scraper_service.format_social_profiles(social_profiles)
        found_count = sum(1 for v in social_profiles.values() if v)
        logger.log_success(f"Found {found_count} social media profiles")
        
        # Process web search results
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
        
        # 5.1 Algorithmic Cross-Validation (merge with AI-detected issues)
        algo_issues = cross_validate(github_data or {}, social_profiles, web_results or '', real_name)
        ai_issues = structured_data.get('cross_validation_issues', [])
        # Merge and deduplicate
        all_issues = list(dict.fromkeys(algo_issues + ai_issues))
        logger.log_action(f"Cross-validation complete: {len(all_issues)} issue(s) detected")
        
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
            social_media_score=structured_data.get('social_media_score'),
            last_activity_summary=structured_data.get('last_activity_summary'),
            description=structured_data.get('description'),
            similar_profiles=structured_data.get('similar_profiles', []),
            cross_validation_issues=all_issues,
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
