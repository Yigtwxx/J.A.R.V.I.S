from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.history import SearchHistory
from app.schemas import SearchQuery, SearchResponse
from app.services import AIService, SearchService, GitHubService, ScraperService, WeatherService, SocialScoreService
from app.services import version_history_service
from app.services.face_matching_service import FaceMatchingService
from app.services.breach_service import breach_service
from app.services.company_service import company_service
from app.services.vector_store_service import vector_store_service
from app.utils.logger import logger
from app.agents.orchestrator import SearchOrchestrator
from app.agents.security_agent import SecurityAgent
from app.agents.social_media_agent import SocialMediaAgent
import asyncio
import json
import os
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import quote as _url_quote

router = APIRouter(prefix="/api/search", tags=["search"])

def _platform_search_url(platform: str, name: str) -> str | None:
    encoded = _url_quote(name)
    _map = {
        'instagram':  f"https://www.instagram.com/explore/search/keyword/?q={encoded}",
        'twitter':    f"https://x.com/search?q={encoded}&f=user",
        'linkedin':   f"https://www.linkedin.com/search/results/people/?keywords={encoded}",
        'spotify':    f"https://open.spotify.com/search/{encoded}/profiles",
        'tiktok':     f"https://www.tiktok.com/search/user?q={encoded}",
        'snapchat':   f"https://www.snapchat.com/explore/{encoded}",
        'tumblr':     f"https://www.tumblr.com/search/{encoded}",
        'youtube':    f"https://www.youtube.com/results?search_query={encoded}",
        'reddit':     f"https://www.reddit.com/search/?q={encoded}&type=user",
        'facebook':   f"https://www.facebook.com/search/people/?q={encoded}",
        'github':     f"https://github.com/search?q={encoded}&type=users",
        'pinterest':  f"https://www.pinterest.com/search/users/?q={encoded}",
        'medium':     f"https://medium.com/search?q={encoded}",
        'threads':    f"https://www.threads.net/search?q={encoded}&filter=people",
        'steam':      f"https://steamcommunity.com/search/users/#text={encoded}",
    }
    return _map.get(platform)

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


def _parse_snippet_date(snippet: str) -> datetime | None:
    """Extract a datetime from a Yahoo search result snippet (best-effort)."""
    if not snippet:
        return None
    now = datetime.now(timezone.utc)
    s = snippet.lower()

    # Relative: "X hours/days/weeks/months/years ago"
    for pattern, unit in [
        (r'(\d+)\s+hour[s]?\s+ago',  'hours'),
        (r'(\d+)\s+day[s]?\s+ago',   'days'),
        (r'(\d+)\s+week[s]?\s+ago',  'weeks'),
        (r'(\d+)\s+month[s]?\s+ago', 'months'),
        (r'(\d+)\s+year[s]?\s+ago',  'years'),
    ]:
        m = re.search(pattern, s)
        if m:
            n = int(m.group(1))
            delta = {
                'hours': timedelta(hours=n), 'days': timedelta(days=n),
                'weeks': timedelta(weeks=n),  'months': timedelta(days=n*30),
                'years': timedelta(days=n*365),
            }[unit]
            return now - delta

    if 'yesterday' in s:
        return now - timedelta(days=1)

    # Absolute: "Jan 15, 2025"
    month_map = {'jan':1,'feb':2,'mar':3,'apr':4,'may':5,'jun':6,
                 'jul':7,'aug':8,'sep':9,'oct':10,'nov':11,'dec':12}
    m = re.search(r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})', s)
    if m:
        try:
            return datetime(int(m.group(3)), month_map[m.group(1)[:3]], int(m.group(2)), tzinfo=timezone.utc)
        except ValueError:
            pass

    # ISO: "2025-01-15"
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', snippet)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
        except ValueError:
            pass

    return None


def _format_last_activity(
    github_data: dict | None,
    social_profiles: dict | None = None,
) -> str | None:
    """
    Return 'Last Detected Node' label based on the most recent activity signal
    across GitHub and all detected social media platforms.
    """
    candidates: list[datetime] = []

    # GitHub last_active (real API datetime — highest confidence)
    if github_data:
        last_active = github_data.get('last_active')
        if last_active:
            try:
                if isinstance(last_active, str):
                    dt = datetime.fromisoformat(last_active.replace('Z', '+00:00'))
                else:
                    dt = last_active
                candidates.append(dt)
            except (ValueError, TypeError):
                pass

    # Social media snippets (Yahoo search text — lower confidence, but real signals)
    if social_profiles:
        for items in social_profiles.values():
            for item in items:
                dt = _parse_snippet_date(item.get('bio', ''))
                if dt:
                    candidates.append(dt)

    if not candidates:
        return None

    days = (datetime.now(timezone.utc) - max(candidates)).days
    if days == 0:
        return "Active today"
    elif days <= 7:
        return f"Active {days}d ago"
    elif days <= 30:
        return f"Active {days // 7}w ago"
    elif days <= 365:
        return f"Active {days // 30}mo ago"
    else:
        return f"Active {days // 365}yr ago"


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
        search_future = loop.run_in_executor(None, search_service.search_person, real_name)

        orch_result, github_data, search_results = await search_orchestrator.run_parallel(
            username=username,
            real_name=real_name,
            github_future=github_future,
            search_future=search_future,
        )

        social_profiles = orch_result.social_profiles
        company_records = orch_result.company_records

        wiki_image, web_results, deep_context, raw_sources = search_results

        # Append institutional intelligence gathered by LegalRecordsAgent
        if orch_result.academic_context or orch_result.patent_context or orch_result.registry_context:
            deep_context += "\n\n=== VERIFIED INSTITUTIONAL INTELLIGENCE ===\n"
            if orch_result.academic_context:
                deep_context += orch_result.academic_context + "\n"
            if orch_result.patent_context:
                deep_context += orch_result.patent_context + "\n"
            if orch_result.registry_context:
                deep_context += orch_result.registry_context + "\n"
        else:
            deep_context += "\n\n=== VERIFIED INSTITUTIONAL INTELLIGENCE ===\nNo significant academic, corporate, or patent registrations publicly detected.\n"
        
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

        # Log company scan results
        if company_records:
            logger.log_success(f"Company registry scan: {len(company_records)} affiliation(s) detected")
        else:
            logger.log_action("Company registry scan: no corporate affiliations found")
        
        # Save context to disk (JSON — backward compat & profile generation)
        try:
            os.makedirs("data/contexts", exist_ok=True)
            safe_filename = re.sub(r'[^a-zA-Z0-9_\-]', '_', raw_query.lower())
            with open(f"data/contexts/{safe_filename}.json", "w", encoding="utf-8") as f:
                json.dump(context, f, ensure_ascii=False, indent=2)
            logger.log_action("Context synchronized to local RAG knowledge base", target=safe_filename)
        except Exception as e:
            logger.log_warning(f"Failed to synchronize RAG context: {e}")

        # Index context into ChromaDB vector store (background — non-blocking)
        try:
            loop.run_in_executor(
                None,
                vector_store_service.index_context,
                raw_query,
                dict(context),
            )
            logger.log_action("ChromaDB vector indexing initiated (background)", target=raw_query)
        except Exception as e:
            logger.log_warning(f"Vector store indexing başlatılamadı: {e}")
            
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

        # Instagram: try direct og:image scrape, fall back to unavatar.io
        instagram_items = social_profiles.get('instagram', [])
        if instagram_items:
            ig_url = instagram_items[0]['url'].split(',')[0].strip()
            ig_username = ig_url.rstrip('/').split('/')[-1]
            direct_ig = scraper_service.fetch_avatar_from_url(ig_url)
            images.append(direct_ig if direct_ig else f"https://unavatar.io/instagram/{ig_username}?fallback=false")

        # Twitter/X: use 'x' slug (not 'twitter') for unavatar.io
        twitter_items = social_profiles.get('twitter', [])
        if twitter_items:
            tw_url = twitter_items[0]['url'].split(',')[0].strip()
            tw_username = tw_url.rstrip('/').split('/')[-1]
            images.append(f"https://unavatar.io/x/{tw_username}?fallback=false")

        # Other platforms via unavatar.io
        for platform in ['linkedin', 'spotify', 'tiktok', 'snapchat', 'tumblr']:
            items = social_profiles.get(platform, [])
            if items:
                profile_url = items[0]['url'].split(',')[0].strip()
                username = profile_url.rstrip('/').split('/')[-1]
                images.append(f"https://unavatar.io/{platform}/{username}?fallback=false")

        # Deduplicate while preserving order
        unique_images = []
        for img in images:
            if img not in unique_images:
                unique_images.append(img)

        if unique_images:
            logger.log_success(f"Injecting {len(unique_images[:6])} visual identities.")
            images_md = " ".join([f"![{real_name}]({img})" for img in unique_images[:6]])
            ai_response = f"{images_md}\n\n" + ai_response
            
        logger.log_success("Analysis complete")
        
        # 4.6. Face Matching: Collect labeled images for cross-platform identity verification
        face_images = []
        if wiki_image:
            face_images.append(("Wikipedia", wiki_image))
        if github_data and github_data.get('avatar_url'):
            face_images.append(("GitHub", github_data['avatar_url']))
        # Instagram: reuse direct scrape result if available
        if instagram_items:
            ig_url = instagram_items[0]['url'].split(',')[0].strip()
            ig_username = ig_url.rstrip('/').split('/')[-1]
            direct_ig = scraper_service.fetch_avatar_from_url(ig_url)
            face_images.append(("Instagram", direct_ig if direct_ig else f"https://unavatar.io/instagram/{ig_username}?fallback=false"))
        # Twitter/X: use 'x' slug
        if twitter_items:
            tw_url = twitter_items[0]['url'].split(',')[0].strip()
            tw_username = tw_url.rstrip('/').split('/')[-1]
            face_images.append(("Twitter", f"https://unavatar.io/x/{tw_username}?fallback=false"))
        for platform in ['linkedin', 'spotify', 'tiktok', 'snapchat', 'tumblr']:
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
        data_breaches = await search_orchestrator.run_breach_check(
            emails=structured_data.get('email_addresses', [])
        )
        
        # 5.1 Algorithmic Cross-Validation (merge with AI-detected issues)
        algo_issues = SecurityAgent.cross_validate(github_data or {}, social_profiles, web_results or '', real_name, username)
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

        # 5.7 Phone numbers (extracted by orchestrator during parallel phase)
        phone_numbers = orch_result.phone_numbers

        # 5.8 Per-platform activity (computed by orchestrator during parallel phase)
        platform_activity = orch_result.platform_activity or SocialMediaAgent._compute_platform_activity(github_data, social_profiles)

        # Build response
        response = SearchResponse(
            name=structured_data.get('name', real_name),
            github_url=github_url or None,
            instagram_url=", ".join([p['url'] for p in social_profiles.get('instagram', []) if p.get('url')]) or None,
            twitter_url=  ", ".join([p['url'] for p in social_profiles.get('twitter',   []) if p.get('url')]) or None,
            linkedin_url= ", ".join([p['url'] for p in social_profiles.get('linkedin',  []) if p.get('url')]) or None,
            spotify_url=  ", ".join([p['url'] for p in social_profiles.get('spotify',   []) if p.get('url')]) or None,
            tiktok_url=   ", ".join([p['url'] for p in social_profiles.get('tiktok',    []) if p.get('url')]) or None,
            snapchat_url= ", ".join([p['url'] for p in social_profiles.get('snapchat',  []) if p.get('url')]) or None,
            tumblr_url=   ", ".join([p['url'] for p in social_profiles.get('tumblr',    []) if p.get('url')]) or None,
            youtube_url=  ", ".join([p['url'] for p in social_profiles.get('youtube',   []) if p.get('url')]) or None,
            reddit_url=   ", ".join([p['url'] for p in social_profiles.get('reddit',    []) if p.get('url')]) or None,
            facebook_url= ", ".join([p['url'] for p in social_profiles.get('facebook',  []) if p.get('url')]) or None,
            pinterest_url=", ".join([p['url'] for p in social_profiles.get('pinterest', []) if p.get('url')]) or None,
            medium_url=   ", ".join([p['url'] for p in social_profiles.get('medium',    []) if p.get('url')]) or None,
            threads_url=  ", ".join([p['url'] for p in social_profiles.get('threads',   []) if p.get('url')]) or None,
            steam_url=    ", ".join([p['url'] for p in social_profiles.get('steam',     []) if p.get('url')]) or None,
            tinder_mention=", ".join([p.get('bio', '') for p in social_profiles.get('tinder', []) if p.get('url')]) or None,
            bumble_mention=", ".join([p.get('bio', '') for p in social_profiles.get('bumble', []) if p.get('url')]) or None,
            discord_mention=", ".join([p.get('bio', '') for p in social_profiles.get('discord', []) if p.get('url')]) or None,
            phone_numbers=phone_numbers if phone_numbers else None,
            location_country=structured_data.get('estimated_location'),
            location_city=structured_data.get('capital_city'),
            weather_info=weather_info,
            social_media_score=score_result['total_score'],
            social_media_score_breakdown=score_result['breakdown'],
            last_activity_summary=_format_last_activity(github_data, social_profiles),
            platform_activity=platform_activity,
            description=structured_data.get('description'),
            additional_info=structured_data.get('additional_info'),
            network_connections=structured_data.get('network_connections', []),
            similar_profiles=structured_data.get('similar_profiles', []),
            cross_validation_issues=all_issues,
            email_addresses=structured_data.get('email_addresses', []),
            data_breaches=data_breaches,
            sources=raw_sources,
            ai_response=ai_response,
            company_records=company_records if company_records else None,
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
