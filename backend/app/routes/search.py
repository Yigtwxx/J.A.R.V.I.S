from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.history import SearchHistory
from app.schemas import SearchQuery, SearchResponse
from app.services import AIService, SearchService, GitHubService, ScraperService, WeatherService, SocialScoreService
from app.services import version_history_service
from app.services.face_matching_service import FaceMatchingService
from app.services.breach_service import breach_service
from app.utils.logger import logger
import asyncio
import json
import math
import os
import re
import unicodedata
from datetime import datetime, timezone

router = APIRouter(prefix="/api/search", tags=["search"])

# Initialize services
ai_service = AIService()
search_service = SearchService()
github_service = GitHubService()
scraper_service = ScraperService()
weather_service = WeatherService()
social_score_service = SocialScoreService()
face_matching_service = FaceMatchingService()


def _normalize_text(text: str) -> str:
    """Normalize Unicode text: remove diacritics (ğ→g, ü→u, ö→o) for fuzzy comparison."""
    nfkd = unicodedata.normalize('NFKD', text.lower())
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def cross_validate(
    github_data: dict,
    social_profiles: dict,
    web_results: str,
    real_name: str,
    username: str = ""
) -> list[str]:
    """
    Algorithmically cross-validate data from different sources.
    Returns a list of detected inconsistency strings.
    """
    issues = []

    # --- 1. GitHub username vs searched username ---
    if github_data and username:
        gh_login = (github_data.get('login') or '').strip().lower()
        searched_username = username.strip().lower()
        if gh_login and searched_username and gh_login != searched_username:
            # Only flag if the usernames are substantially different
            if searched_username not in gh_login and gh_login not in searched_username:
                issues.append(
                    f"GitHub login '@{github_data.get('login')}' doesn't match searched username '{username}'. Verify this is the correct account."
                )

    # --- 2. GitHub location vs web results (word-level matching) ---
    if github_data:
        gh_location = (github_data.get('location') or '').strip()
        if gh_location and web_results and len(gh_location) > 2:
            location_words = set(_normalize_text(gh_location).split())
            web_normalized = _normalize_text(web_results)
            # Check if ANY significant location word appears in web results
            significant_words = {w for w in location_words if len(w) > 2}
            if significant_words and not any(w in web_normalized for w in significant_words):
                issues.append(
                    f"GitHub states location as '{gh_location}' but none of its keywords appear in web search results."
                )

    # --- 3. GitHub display name vs searched name (with Unicode normalization) ---
    if github_data:
        gh_name = (github_data.get('name') or '').strip()
        if gh_name and real_name:
            gh_words = set(_normalize_text(gh_name).split())
            search_words = set(_normalize_text(real_name).split())
            # Filter out short words (initials, prepositions)
            gh_significant = {w for w in gh_words if len(w) > 1}
            search_significant = {w for w in search_words if len(w) > 1}
            if gh_significant and search_significant and not gh_significant.intersection(search_significant):
                issues.append(
                    f"GitHub profile name '{gh_name}' doesn't share any words with searched name '{real_name}'. Possible identity mismatch."
                )

    # --- 4. No social media profiles but significant web presence ---
    found_platforms = [k for k, v in social_profiles.items() if v]
    if not found_platforms and web_results and len(web_results) > 500:
        issues.append(
            "No social media profiles found despite significant web results. The person may use different usernames across platforms."
        )

    # --- 5. GitHub bio profession vs web results profession ---
    if github_data:
        gh_bio = (github_data.get('bio') or '').strip().lower()
        if gh_bio and len(gh_bio) > 10 and web_results:
            web_lower = web_results.lower()
            # Define mutually exclusive profession clusters
            profession_clusters = [
                ({'developer', 'programmer', 'engineer', 'software', 'coding', 'github'},
                 {'doctor', 'physician', 'medical', 'hospital', 'clinical', 'surgeon'}),
                ({'developer', 'programmer', 'engineer', 'software'},
                 {'lawyer', 'attorney', 'legal', 'law firm', 'court'}),
                ({'student', 'öğrenci', 'university', 'üniversite', 'college'},
                 {'ceo', 'founder', 'director', 'chairman', 'president', 'managing'}),
            ]
            for cluster_a, cluster_b in profession_clusters:
                bio_has_a = any(kw in gh_bio for kw in cluster_a)
                web_has_b = any(kw in web_lower for kw in cluster_b)
                bio_has_b = any(kw in gh_bio for kw in cluster_b)
                web_has_a = any(kw in web_lower for kw in cluster_a)

                if bio_has_a and web_has_b and not bio_has_b and not web_has_a:
                    bio_match = next(kw for kw in cluster_a if kw in gh_bio)
                    web_match = next(kw for kw in cluster_b if kw in web_lower)
                    issues.append(
                        f"GitHub bio mentions '{bio_match}' but web results reference '{web_match}'. Possible identity confusion with another person."
                    )
                    break  # One conflict per search is enough

    # --- 6. GitHub exists but all other sources are empty ---
    if github_data and not found_platforms and (not web_results or len(web_results) < 100):
        issues.append(
            "Only GitHub data is available — no corroborating web or social media sources. Information reliability is limited."
        )

    return issues


def _compute_platform_activity(github_data: dict | None, social_profiles: dict) -> dict:
    """
    Compute a 0-100 activity percentage for each detected platform.
    Returns: { "github": 85, "instagram": 60, ... } (only found platforms)
    """
    activity: dict[str, int] = {}

    # --- GitHub (richest data) ---
    if github_data:
        score = 30  # Base: profile exists
        followers = github_data.get('followers', 0) or 0
        if followers > 0:
            score += min(20, int(math.log10(followers + 1) * 7))
        repos = github_data.get('public_repos', 0) or 0
        if repos > 0:
            score += min(20, int(math.log10(repos + 1) * 12))
        last_active = github_data.get('last_active')
        if last_active:
            try:
                if isinstance(last_active, str):
                    last_dt = datetime.fromisoformat(last_active.replace('Z', '+00:00'))
                else:
                    last_dt = last_active
                days = (datetime.now(timezone.utc) - last_dt).days
                if days <= 7:
                    score += 30
                elif days <= 30:
                    score += 22
                elif days <= 90:
                    score += 15
                elif days <= 365:
                    score += 8
                else:
                    score += 2
            except (ValueError, TypeError):
                pass
        activity['github'] = min(100, score)

    # --- Standard social platforms ---
    standard_platforms = ['instagram', 'twitter', 'linkedin', 'tiktok', 'snapchat', 'tumblr']
    for platform in standard_platforms:
        items = social_profiles.get(platform, [])
        if items:
            score = 60  # Profile found = solid base
            # Bio presence adds confidence
            for item in items:
                if item.get('bio') and len(item['bio'].strip()) > 10:
                    score += 40
                    break
            activity[platform] = min(100, score)

    # --- Passive platforms (Spotify) ---
    if social_profiles.get('spotify'):
        activity['spotify'] = 70  # Spotify is mostly passive

    # --- Mention-only platforms (Tinder, Bumble) ---
    for platform in ['tinder', 'bumble']:
        if social_profiles.get(platform):
            activity[platform] = 30  # Indirect mention = low confidence

    return activity


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
        
        # Save context to disk for RAG Chatbot
        try:
            os.makedirs("data/contexts", exist_ok=True)
            safe_filename = re.sub(r'[^a-zA-Z0-9_\-]', '_', raw_query.lower())
            with open(f"data/contexts/{safe_filename}.json", "w", encoding="utf-8") as f:
                json.dump(context, f, ensure_ascii=False, indent=2)
            logger.log_action("Context synchronized to local RAG knowledge base", target=safe_filename)
        except Exception as e:
            logger.log_warning(f"Failed to synchronize RAG context: {e}")
            
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
            
        for platform in ['instagram', 'twitter', 'linkedin', 'spotify', 'tiktok', 'snapchat', 'tumblr']:
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
        
        # 4.6. Face Matching: Collect labeled images for cross-platform identity verification
        face_images = []
        if wiki_image:
            face_images.append(("Wikipedia", wiki_image))
        if github_data and github_data.get('avatar_url'):
            face_images.append(("GitHub", github_data['avatar_url']))
        for platform in ['instagram', 'twitter', 'linkedin', 'spotify', 'tiktok', 'snapchat', 'tumblr']:
            items = social_profiles.get(platform, [])
            if items:
                first_profile_url = items[0]['url'].split(',')[0].strip()
                social_username = first_profile_url.rstrip('/').split('/')[-1]
                face_images.append((platform.capitalize(), f"https://unavatar.io/{platform}/{social_username}?fallback=false"))
        
        face_match_report = None
        sentiment_report = None
        
        # We will run Face Matching and Sentiment Analysis concurrently to save time
        async def run_face_match():
            if len(face_images) >= 2:
                try:
                    logger.log_action(f"Initiating biometric cross-reference across {len(face_images)} inputs...")
                    return await loop.run_in_executor(
                        None, face_matching_service.analyze_all_images, face_images
                    )
                except Exception as e:
                    logger.log_warning(f"Face matching failed (non-critical): {e}")
            return None
            
        async def run_sentiment():
            if deep_context:
                try:
                    logger.log_action("Initiating socio-psychological sentiment analysis...")
                    return await ai_service.analyze_sentiment(deep_context)
                except Exception as e:
                    logger.log_warning(f"Sentiment analysis failed (non-critical): {e}")
            return None
            
        face_match_report, sentiment_report = await asyncio.gather(run_face_match(), run_sentiment())
        
        # 5. Extract structured data
        structured_data = await ai_service.extract_profile_data(ai_response, real_name)
        
        # 5.0.1 Data Breach Intel
        async def run_breach_check():
            emails = structured_data.get('email_addresses', [])
            if emails:
                try:
                    return await breach_service.check_breaches(emails)
                except Exception as e:
                    logger.log_warning(f"Breach check failed (non-critical): {e}")
            return []
            
        data_breaches = await run_breach_check()
        
        # 5.1 Algorithmic Cross-Validation (merge with AI-detected issues)
        algo_issues = cross_validate(github_data or {}, social_profiles, web_results or '', real_name, username)
        ai_issues = structured_data.get('cross_validation_issues', [])
        # Type safety: AI might return non-list
        if not isinstance(ai_issues, list):
            ai_issues = [str(ai_issues)] if ai_issues else []
        ai_issues = [str(issue) for issue in ai_issues if issue]  # Ensure all items are strings
        # Merge and deduplicate
        all_issues = list(dict.fromkeys(algo_issues + ai_issues))
        logger.log_action(f"Cross-validation complete: {len(all_issues)} issue(s) detected")
        
        # 5.5 Fetch Weather for guessed location
        weather_info = None
        if structured_data.get('capital_city'):
            weather_info = weather_service.get_weather(structured_data['capital_city'])

        # 5.6 Compute Digital Impact Score (algorithmic — replaces AI-guessed score)
        logger.log_action("Computing Digital Impact Score...")
        score_result = social_score_service.calculate_score(
            github_data=github_data,
            social_profiles=social_profiles,
            raw_sources=raw_sources,
            web_results=web_results or '',
        )

        # 5.7 Extract phone numbers from deep context
        phone_numbers = scraper_service.extract_phone_numbers(real_name, deep_context)

        # 5.8 Compute per-platform activity percentage
        platform_activity = _compute_platform_activity(github_data, social_profiles)

        # Build response
        response = SearchResponse(
            name=structured_data.get('name', real_name),
            github_url=github_url,
            instagram_url=", ".join([p['url'] for p in social_profiles.get('instagram', [])]) or None,
            twitter_url=", ".join([p['url'] for p in social_profiles.get('twitter', [])]) or None,
            linkedin_url=", ".join([p['url'] for p in social_profiles.get('linkedin', [])]) or None,
            spotify_url=", ".join([p['url'] for p in social_profiles.get('spotify', [])]) or None,
            tiktok_url=", ".join([p['url'] for p in social_profiles.get('tiktok', [])]) or None,
            snapchat_url=", ".join([p['url'] for p in social_profiles.get('snapchat', [])]) or None,
            tumblr_url=", ".join([p['url'] for p in social_profiles.get('tumblr', [])]) or None,
            tinder_mention=", ".join([p.get('bio', '') for p in social_profiles.get('tinder', [])]) or None,
            bumble_mention=", ".join([p.get('bio', '') for p in social_profiles.get('bumble', [])]) or None,
            phone_numbers=phone_numbers if phone_numbers else None,
            location_country=structured_data.get('estimated_location'),
            location_city=structured_data.get('capital_city'),
            weather_info=weather_info,
            social_media_score=score_result['total_score'],
            social_media_score_breakdown=score_result['breakdown'],
            last_activity_summary=structured_data.get('last_activity_summary'),
            platform_activity=platform_activity,
            description=structured_data.get('description'),
            similar_profiles=structured_data.get('similar_profiles', []),
            cross_validation_issues=all_issues,
            email_addresses=structured_data.get('email_addresses', []),
            data_breaches=data_breaches,
            sources=raw_sources,
            ai_response=ai_response
        )
        
        # 5.7. Attach face match and sentiment results to response
        if face_match_report:
            response.face_match_results = face_match_report
            
        if sentiment_report:
            response.sentiment_analysis = sentiment_report
            logger.log_success(f"Sentiment matrix locked: {sentiment_report.get('dominant_emotion', 'N/A')}")
        
        # 6. Version History: Save snapshot & generate change report
        try:
            version_history_service.save_snapshot(db, raw_query, response)
            change_report = version_history_service.generate_change_report(db, raw_query)
            if change_report and change_report.has_changes:
                response.version_history = change_report.model_dump(mode='json')
                logger.log_success(f"Version history: {len(change_report.changes)} change(s) detected")
            elif change_report:
                response.version_history = change_report.model_dump(mode='json')
                logger.log_action("Version history: No changes detected since last scan")
            else:
                logger.log_action("Version history: First snapshot saved — no previous data to compare")
        except Exception as e:
            logger.log_warning(f"Version history snapshot failed (non-critical): {e}")
        
        # 7. Save to history
        try:
            history_entry = SearchHistory(query_name=raw_query)
            db.add(history_entry)
            db.commit()
        except Exception as e:
            logger.log_warning(f"Failed to record search history: {e}")
            
        logger.log_success(f"SEARCH COMPLETED FOR TARGET: {raw_query}")
        return response
    
    except Exception as e:
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
