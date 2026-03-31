"""
SearchOrchestrationService — orchestrates the full person-search pipeline.

Extracted from the monolithic search_person route to keep the route layer thin.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from app.schemas import SearchResponse
from app.utils.logger import logger

# ---------------------------------------------------------------------------
# Pure-utility helpers (no service dependency)
# ---------------------------------------------------------------------------

def _parse_snippet_date(snippet: str) -> datetime | None:
    """Extract a datetime from a Yahoo search result snippet (best-effort)."""
    if not snippet:
        return None
    now = datetime.now(UTC)
    s = snippet.lower()

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
                'weeks': timedelta(weeks=n), 'months': timedelta(days=n * 30),
                'years': timedelta(days=n * 365),
            }[unit]
            return now - delta

    if 'yesterday' in s:
        return now - timedelta(days=1)

    month_map = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
        'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
    }
    m = re.search(
        r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})', s
    )
    if m:
        try:
            return datetime(int(m.group(3)), month_map[m.group(1)[:3]], int(m.group(2)), tzinfo=UTC)
        except ValueError:
            pass

    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', snippet)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=UTC)
        except ValueError:
            pass

    return None


def _format_last_activity(
    github_data: dict | None,
    social_profiles: dict | None = None,
) -> str | None:
    """Return human-readable 'last seen' label from the most recent signal."""
    candidates: list[datetime] = []

    if github_data:
        last_active = github_data.get('last_active')
        if last_active:
            try:
                dt = (
                    datetime.fromisoformat(last_active.replace('Z', '+00:00'))
                    if isinstance(last_active, str)
                    else last_active
                )
                candidates.append(dt)
            except (ValueError, TypeError):
                pass

    if social_profiles:
        for items in social_profiles.values():
            for item in items:
                dt = _parse_snippet_date(item.get('bio', ''))
                if dt:
                    candidates.append(dt)

    if not candidates:
        return None

    days = (datetime.now(UTC) - max(candidates)).days
    if days == 0:
        return "Active today"
    if days <= 7:
        return f"Active {days}d ago"
    if days <= 30:
        return f"Active {days // 7}w ago"
    if days <= 365:
        return f"Active {days // 30}mo ago"
    return f"Active {days // 365}yr ago"


def _join_urls(profiles: dict, platform: str) -> str | None:
    """Join URLs from social_profiles[platform] into a comma-separated string."""
    items = profiles.get(platform, [])
    result = ", ".join(p['url'] for p in items if p.get('url'))
    return result or None


def _join_bios(profiles: dict, platform: str) -> str | None:
    """Join bios from social_profiles[platform] into a comma-separated string."""
    items = profiles.get(platform, [])
    result = ", ".join(p.get('bio', '') for p in items if p.get('url'))
    return result or None


# ---------------------------------------------------------------------------
# Service class
# ---------------------------------------------------------------------------

class SearchOrchestrationService:
    """Orchestrates the full person-search pipeline."""

    def __init__(
        self,
        ai_service: Any,
        search_service: Any,
        github_service: Any,
        scraper_service: Any,
        weather_service: Any,
        social_score_service: Any,
        face_matching_service: Any,
        search_orchestrator: Any,
        vector_store_service: Any,
        version_history_service: Any,
        breach_orchestrator: Any,
    ) -> None:
        self._ai = ai_service
        self._search = search_service
        self._github = github_service
        self._scraper = scraper_service
        self._weather = weather_service
        self._score = social_score_service
        self._face = face_matching_service
        self._orchestrator = search_orchestrator
        self._vector = vector_store_service
        self._version = version_history_service
        self._breach_orch = breach_orchestrator

    # -- Step 1: Parse query ------------------------------------------------

    @staticmethod
    def parse_query(raw_query: str) -> tuple[str, str]:
        """Split 'Real Name / username' into (real_name, username)."""
        if "/" in raw_query:
            parts = [p.strip() for p in raw_query.split("/")]
            real_name = parts[0]
            username = parts[1] if len(parts) > 1 else real_name
        else:
            real_name = raw_query
            username = raw_query
        return real_name, username

    # -- Step 2: Parallel data fetching -------------------------------------

    async def fetch_parallel_data(self, real_name: str, username: str):
        """Run orchestrator + GitHub + search concurrently. Returns raw tuple."""
        loop = asyncio.get_running_loop()

        logger.log_action("Launching parallel intelligence gathering...")

        github_future = loop.run_in_executor(None, self._github.search_user, username)
        search_future = loop.run_in_executor(None, self._search.search_person, real_name)

        orch_result, github_data, search_results = await self._orchestrator.run_parallel(
            username=username,
            real_name=real_name,
            github_future=github_future,
            search_future=search_future,
        )
        return orch_result, github_data, search_results

    # -- Step 3: Process raw results ----------------------------------------

    def process_results(
        self, orch_result, github_data: dict | None, search_results: tuple
    ) -> tuple[dict, str, str | None, list]:
        """Format raw results into context dict. Returns (context, deep_context, github_url, raw_sources)."""
        context: dict[str, Any] = {}

        social_profiles = orch_result.social_profiles
        company_records = orch_result.company_records
        wiki_image, web_results, deep_context, raw_sources = search_results

        # Append institutional intelligence
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

        # GitHub
        github_url = None
        if github_data:
            context['github'] = self._github.format_github_data(github_data)
            github_url = github_data.get('profile_url')
            logger.log_success(f"GitHub profile found: {github_url}")
        else:
            logger.log_warning("No GitHub profile found")

        # Social media
        context['social_media'] = self._scraper.format_social_profiles(social_profiles)
        found_count = sum(1 for v in social_profiles.values() if v)
        logger.log_success(f"Found {found_count} social media profiles")

        # Web search
        context['web_search'] = web_results
        context['deep_context'] = deep_context
        logger.log_success("Web search aggregation and deep-packet inspection completed")

        # Company records
        if company_records:
            logger.log_success(f"Company registry scan: {len(company_records)} affiliation(s) detected")
        else:
            logger.log_action("Company registry scan: no corporate affiliations found")

        return context, deep_context, github_url, raw_sources

    # -- Step 4: Save context -----------------------------------------------

    def save_context(self, raw_query: str, context: dict) -> None:
        """Persist context to JSON file and index into ChromaDB."""
        try:
            os.makedirs("data/contexts", exist_ok=True)
            safe_filename = re.sub(r'[^a-zA-Z0-9_\-]', '_', raw_query.lower())
            with open(f"data/contexts/{safe_filename}.json", "w", encoding="utf-8") as f:
                json.dump(context, f, ensure_ascii=False, indent=2)
            logger.log_action("Context synchronized to local RAG knowledge base", target=safe_filename)
        except Exception as e:
            logger.log_warning(f"Failed to synchronize RAG context: {e}")

        try:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, self._vector.index_context, raw_query, dict(context))
            logger.log_action("ChromaDB vector indexing initiated (background)", target=raw_query)
        except Exception as e:
            logger.log_warning(f"Vector store indexing could not be started: {e}")

    # -- Step 5: Collect images ---------------------------------------------

    def collect_images(
        self, social_profiles: dict, github_data: dict | None, wiki_image: str | None, real_name: str
    ) -> list[str]:
        """Build a deduplicated list of avatar/profile images."""
        images: list[str] = []
        if wiki_image:
            images.append(wiki_image)
        if github_data and github_data.get('avatar_url'):
            images.append(github_data['avatar_url'])

        # Instagram
        instagram_items = social_profiles.get('instagram', [])
        if instagram_items:
            ig_url = instagram_items[0]['url'].split(',')[0].strip()
            ig_username = ig_url.rstrip('/').split('/')[-1]
            direct_ig = self._scraper.fetch_avatar_from_url(ig_url)
            images.append(direct_ig if direct_ig else f"https://unavatar.io/instagram/{ig_username}?fallback=false")

        # Twitter/X
        twitter_items = social_profiles.get('twitter', [])
        if twitter_items:
            tw_url = twitter_items[0]['url'].split(',')[0].strip()
            tw_username = tw_url.rstrip('/').split('/')[-1]
            images.append(f"https://unavatar.io/x/{tw_username}?fallback=false")

        # Other platforms
        for platform in ['linkedin', 'spotify', 'tiktok', 'snapchat', 'tumblr']:
            items = social_profiles.get(platform, [])
            if items:
                profile_url = items[0]['url'].split(',')[0].strip()
                social_username = profile_url.rstrip('/').split('/')[-1]
                images.append(f"https://unavatar.io/{platform}/{social_username}?fallback=false")

        # Deduplicate while preserving order
        unique: list[str] = []
        for img in images:
            if img not in unique:
                unique.append(img)
        return unique

    # -- Step 6: Collect face images ----------------------------------------

    def collect_face_images(
        self, social_profiles: dict, github_data: dict | None, wiki_image: str | None
    ) -> list[tuple[str, str]]:
        """Build labeled (platform, url) pairs for face matching."""
        face_images: list[tuple[str, str]] = []
        if wiki_image:
            face_images.append(("Wikipedia", wiki_image))
        if github_data and github_data.get('avatar_url'):
            face_images.append(("GitHub", github_data['avatar_url']))

        instagram_items = social_profiles.get('instagram', [])
        if instagram_items:
            ig_url = instagram_items[0]['url'].split(',')[0].strip()
            ig_username = ig_url.rstrip('/').split('/')[-1]
            direct_ig = self._scraper.fetch_avatar_from_url(ig_url)
            face_images.append(("Instagram", direct_ig if direct_ig else f"https://unavatar.io/instagram/{ig_username}?fallback=false"))

        twitter_items = social_profiles.get('twitter', [])
        if twitter_items:
            tw_url = twitter_items[0]['url'].split(',')[0].strip()
            tw_username = tw_url.rstrip('/').split('/')[-1]
            face_images.append(("Twitter", f"https://unavatar.io/x/{tw_username}?fallback=false"))

        for platform in ['linkedin', 'spotify', 'tiktok', 'snapchat', 'tumblr']:
            items = social_profiles.get(platform, [])
            if items:
                first_url = items[0]['url'].split(',')[0].strip()
                social_username = first_url.rstrip('/').split('/')[-1]
                face_images.append((platform.capitalize(), f"https://unavatar.io/{platform}/{social_username}?fallback=false"))

        return face_images

    # -- Step 7: Run AI + face match + sentiment ----------------------------

    async def run_analysis(
        self, raw_query: str, context: dict, deep_context: str, face_images: list[tuple[str, str]]
    ) -> tuple[str, Any, Any]:
        """Generate AI response, run face matching and sentiment concurrently."""
        loop = asyncio.get_running_loop()

        logger.log_action("Running cognitive analysis...")
        ai_response = await self._ai.generate_response(
            prompt=f"Tell me everything you know about {raw_query}",
            context=context,
        )

        async def run_face_match():
            if len(face_images) >= 2:
                try:
                    logger.log_action(f"Initiating biometric cross-reference across {len(face_images)} inputs...")
                    return await loop.run_in_executor(None, self._face.analyze_all_images, face_images)
                except Exception as e:
                    logger.log_warning(f"Face matching failed (non-critical): {e}")
            return None

        async def run_sentiment():
            if deep_context:
                try:
                    logger.log_action("Initiating socio-psychological sentiment analysis...")
                    return await self._ai.analyze_sentiment(deep_context)
                except Exception as e:
                    logger.log_warning(f"Sentiment analysis failed (non-critical): {e}")
            return None

        face_match_report, sentiment_report = await asyncio.gather(run_face_match(), run_sentiment())
        return ai_response, face_match_report, sentiment_report

    # -- Step 8: Post-analysis (breach, cross-validation, weather, score) ---

    async def run_post_analysis(
        self,
        ai_response: str,
        real_name: str,
        username: str,
        github_data: dict | None,
        social_profiles: dict,
        web_results: str | None,
        raw_sources: list,
        orch_result,
    ) -> dict:
        """Extract structured data, check breaches, cross-validate, compute scores."""
        from app.agents.security_agent import SecurityAgent
        from app.agents.social_media_agent import SocialMediaAgent

        structured_data = await self._ai.extract_profile_data(ai_response, real_name)

        # Breach check
        data_breaches = await self._breach_orch.run_breach_check(
            emails=structured_data.get('email_addresses', [])
        )

        # Cross-validation
        algo_issues = SecurityAgent.cross_validate(github_data or {}, social_profiles, web_results or '', real_name, username)
        ai_issues = structured_data.get('cross_validation_issues', [])
        if not isinstance(ai_issues, list):
            ai_issues = [str(ai_issues)] if ai_issues else []
        ai_issues = [str(issue) for issue in ai_issues if issue]
        all_issues = list(dict.fromkeys(algo_issues + ai_issues))
        logger.log_action(f"Cross-validation complete: {len(all_issues)} issue(s) detected")

        # Weather
        weather_info = None
        if structured_data.get('capital_city'):
            weather_info = self._weather.get_weather(structured_data['capital_city'])

        # Digital Impact Score
        logger.log_action("Computing Digital Impact Score...")
        score_result = self._score.calculate_score(
            github_data=github_data,
            social_profiles=social_profiles,
            raw_sources=raw_sources,
            web_results=web_results or '',
        )

        # Phone numbers & platform activity
        phone_numbers = orch_result.phone_numbers
        platform_activity = orch_result.platform_activity or SocialMediaAgent._compute_platform_activity(github_data, social_profiles)

        return {
            'structured_data': structured_data,
            'data_breaches': data_breaches,
            'all_issues': all_issues,
            'weather_info': weather_info,
            'score_result': score_result,
            'phone_numbers': phone_numbers,
            'platform_activity': platform_activity,
        }

    # -- Step 9: Build response ---------------------------------------------

    def build_response(
        self,
        ai_response: str,
        real_name: str,
        github_url: str | None,
        social_profiles: dict,
        images: list[str],
        post: dict,
        raw_sources: list,
        github_data: dict | None,
        orch_result,
        face_match_report,
        sentiment_report,
    ) -> SearchResponse:
        """Assemble the final SearchResponse."""
        structured_data = post['structured_data']

        # Image injection
        if images:
            logger.log_success(f"Injecting {len(images[:6])} visual identities.")
            images_md = " ".join([f"![{real_name}]({img})" for img in images[:6]])
            ai_response = f"{images_md}\n\n" + ai_response

        logger.log_success("Analysis complete")

        sp_keys = [k for k, v in social_profiles.items() if v]
        logger.log_action(f"[DIAG] build_response: {len(sp_keys)} platform(s): {sp_keys[:5]}")

        response = SearchResponse(
            name=structured_data.get('name', real_name),
            github_url=github_url or None,
            instagram_url=_join_urls(social_profiles, 'instagram'),
            twitter_url=_join_urls(social_profiles, 'twitter'),
            linkedin_url=_join_urls(social_profiles, 'linkedin'),
            spotify_url=_join_urls(social_profiles, 'spotify'),
            tiktok_url=_join_urls(social_profiles, 'tiktok'),
            snapchat_url=_join_urls(social_profiles, 'snapchat'),
            tumblr_url=_join_urls(social_profiles, 'tumblr'),
            youtube_url=_join_urls(social_profiles, 'youtube'),
            reddit_url=_join_urls(social_profiles, 'reddit'),
            facebook_url=_join_urls(social_profiles, 'facebook'),
            pinterest_url=_join_urls(social_profiles, 'pinterest'),
            medium_url=_join_urls(social_profiles, 'medium'),
            threads_url=_join_urls(social_profiles, 'threads'),
            steam_url=_join_urls(social_profiles, 'steam'),
            tinder_mention=_join_bios(social_profiles, 'tinder'),
            bumble_mention=_join_bios(social_profiles, 'bumble'),
            discord_mention=_join_bios(social_profiles, 'discord'),
            phone_numbers=post['phone_numbers'] if post['phone_numbers'] else None,
            location_country=structured_data.get('estimated_location'),
            location_city=structured_data.get('capital_city'),
            weather_info=post['weather_info'],
            social_media_score=post['score_result']['total_score'],
            social_media_score_breakdown=post['score_result']['breakdown'],
            last_activity_summary=_format_last_activity(github_data, social_profiles),
            platform_activity=post['platform_activity'],
            description=structured_data.get('description'),
            additional_info=structured_data.get('additional_info'),
            network_connections=structured_data.get('network_connections', []),
            similar_profiles=structured_data.get('similar_profiles', []),
            cross_validation_issues=post['all_issues'],
            email_addresses=structured_data.get('email_addresses', []),
            data_breaches=post['data_breaches'],
            sources=raw_sources,
            ai_response=ai_response,
            company_records=orch_result.company_records if orch_result.company_records else None,
        )

        if face_match_report:
            response.face_match_results = face_match_report
        if sentiment_report:
            response.sentiment_analysis = sentiment_report
            logger.log_success(f"Sentiment matrix locked: {sentiment_report.get('dominant_emotion', 'N/A')}")

        return response

    # -- Step 10: Save history ----------------------------------------------

    def save_history(self, db, raw_query: str, response: SearchResponse) -> None:
        """Save version snapshot and search history record."""
        from app.models.history import SearchHistory

        try:
            self._version.save_snapshot(db, raw_query, response)
            change_report = self._version.generate_change_report(db, raw_query)
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

        try:
            history_entry = SearchHistory(query_name=raw_query)
            db.add(history_entry)
            db.commit()
        except Exception as e:
            logger.log_warning(f"Failed to record search history: {e}")
