"""
SearchOrchestrationService — slim coordinator for the person-search pipeline.

The heavy logic now lives in individual pipeline step files under
`app/services/pipeline/`. Async methods delegate to steps. Sync methods
retain their original logic so callers (search.py) require zero changes.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from app.discovery.loop.runner import target_key_for
from app.discovery.types import EntityType
from app.models.discovery import SearchSession
from app.schemas import SearchResponse
from app.services.identity_resolver import (
    anchor_corroborated_by_web,
    classify_profiles,
    filter_intelligence_sources,
    web_relevance_ratio,
)
from app.services.pipeline.analysis_runner import AnalysisRunnerStep
from app.services.pipeline.context import PipelineContext
from app.services.pipeline.data_fetcher import DataFetcherStep
from app.services.pipeline.image_collector import ImageCollectorStep
from app.services.pipeline.post_analysis_runner import PostAnalysisRunnerStep

# Re-export utility helpers so any existing imports still work
from app.services.pipeline.utils import (  # noqa: F401
    _format_last_activity,
    _join_bios,
    _join_urls,
    _parse_snippet_date,
    sanitize_breach_list,
    sanitize_email_list,
    sanitize_network_connections,
    sanitize_phone_list,
    sanitize_str_list,
)
from app.utils.logger import logger


def _assign_optional(response: SearchResponse, field: str, value: Any) -> None:
    """Assign an optional enrichment section, dropping it if it fails validation.

    SearchResponse validates on assignment, so a malformed section raises here
    rather than deep inside FastAPI's response serialization. Losing one section
    degrades the report; letting it raise would discard the entire search.
    """
    try:
        setattr(response, field, value)
    except ValidationError as exc:
        logger.log_warning(f"Dropping invalid '{field}' from response: {exc.error_count()} validation error(s)")


class SearchOrchestrationService:
    """
    Orchestrates the full person-search pipeline.

    The public API is unchanged — search.py does not require any modifications.
    Async steps (data fetch, AI analysis, post-analysis) delegate to pipeline
    step classes. Sync steps retain their original inline logic.
    """

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
        version_history_service: Any,
        breach_orchestrator: Any,
        darkweb_service: Any = None,
        geoint_service: Any = None,
        psychological_service: Any = None,
        predictive_service: Any = None,
    ) -> None:
        self._ai = ai_service
        self._search = search_service
        self._github = github_service
        self._scraper = scraper_service
        self._weather = weather_service
        self._score = social_score_service
        self._face = face_matching_service
        self._orchestrator = search_orchestrator
        self._version = version_history_service
        self._breach_orch = breach_orchestrator
        self._darkweb = darkweb_service
        self._geoint = geoint_service
        self._psych = psychological_service
        self._predictor = predictive_service

        # Pipeline step instances (reused across requests)
        self._data_fetcher = DataFetcherStep(github_service, search_service, search_orchestrator)
        self._image_collector = ImageCollectorStep()
        self._analysis_runner = AnalysisRunnerStep(ai_service, face_matching_service)
        self._post_analysis_runner = PostAnalysisRunnerStep(
            ai_service,
            breach_orchestrator,
            social_score_service,
            weather_service,
            darkweb_service,
            geoint_service,
            psychological_service,
            predictive_service,
        )

    # -----------------------------------------------------------------------
    # Step 1: Parse query
    # -----------------------------------------------------------------------

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

    # -----------------------------------------------------------------------
    # Step 2: Parallel data fetching (async — delegates to DataFetcherStep)
    # -----------------------------------------------------------------------

    async def fetch_parallel_data(self, real_name: str, username: str, depth_config=None):
        """Run orchestrator + GitHub + search concurrently. Returns raw tuple."""
        ctx = PipelineContext(real_name=real_name, username=username, depth_config=depth_config)
        ctx = await self._data_fetcher.execute(ctx)
        # Returned rather than stashed on `self`: this service is a process-wide
        # singleton, so an attribute would be clobbered by any concurrent search.
        return ctx.orch_result, ctx.github_data, ctx.search_results, ctx.discovery_result

    # -----------------------------------------------------------------------
    # Step 3: Process raw results
    # -----------------------------------------------------------------------

    def process_results(
        self, orch_result, github_data: dict | None, search_results: tuple, real_name: str = ""
    ) -> tuple[dict, str, str | None, list]:
        """Format raw results into context dict."""
        context: dict[str, Any] = {}

        social_profiles = orch_result.social_profiles
        company_records = orch_result.company_records
        wiki_image, web_results, deep_context, raw_sources = search_results

        # Deterministically drop web/deep sources about a different same-name person
        # before they reach the AI briefing (filter the scraped content, then append
        # institutional records below).
        web_results, deep_context, dropped = filter_intelligence_sources(
            real_name, web_results, deep_context, raw_sources
        )
        if dropped:
            logger.log_warning(f"Filtered {dropped} off-target (different-name) web source(s) from analysis context")

        if orch_result.academic_context or orch_result.patent_context or orch_result.registry_context:
            deep_context += "\n\n=== NAME-MATCHED INSTITUTIONAL RECORDS (unverified — may belong to a different person with the same name; attribute to the subject only if corroborated by the confirmed anchor) ===\n"
            if orch_result.academic_context:
                deep_context += orch_result.academic_context + "\n"
            if orch_result.patent_context:
                deep_context += orch_result.patent_context + "\n"
            if orch_result.registry_context:
                deep_context += orch_result.registry_context + "\n"
        else:
            deep_context += (
                "\n\n=== NAME-MATCHED INSTITUTIONAL RECORDS (unverified — may belong to a different person with the same name; attribute to the subject only if corroborated by the confirmed anchor) ===\n"
                "No significant academic, corporate, or patent registrations publicly detected.\n"
            )

        github_url = None
        if github_data:
            context["github"] = self._github.format_github_data(github_data)
            github_url = github_data.get("profile_url")
            logger.log_success(f"GitHub profile found: {github_url}")
        else:
            logger.log_warning("No GitHub profile found")

        # Identity disambiguation: label same-name namesakes so the AI does not
        # merge different people into one description.
        classification = classify_profiles(social_profiles, github_data, real_name, web_results or "")
        context["anchor"] = classification.get("anchor")
        context["social_media"] = self._scraper.format_social_profiles(social_profiles, classification)
        found_count = sum(1 for v in social_profiles.values() if v)
        logger.log_success(f"Found {found_count} social media profiles")
        if classification.get("has_others"):
            logger.log_warning("Same-name candidate profiles detected — isolating primary target for analysis")

        context["web_search"] = web_results
        context["deep_context"] = deep_context

        # Low-confidence gate: when the web corpus is dominated by a different
        # same-name person, restrict the briefing to the confirmed GitHub/social
        # anchor rather than letting web/deep prose hijack it. Two triggers:
        #  - GitHub anchor exists but web/deep never corroborates its distinctive
        #    login/profile (a same-name namesake sharing only the name), or
        #  - no GitHub anchor and fewer than half the web sources match the name.
        relevance = web_relevance_ratio(real_name, raw_sources)
        corroborated = anchor_corroborated_by_web(github_data, raw_sources, deep_context)
        has_anchor = bool(github_data) or found_count > 0
        low_signal = corroborated is False or (corroborated is None and relevance is not None and relevance < 0.5)
        if has_anchor and low_signal:
            reason = "anchor not corroborated by web" if corroborated is False else f"low web-name match ({relevance})"
            logger.log_warning(
                f"Subject weakly identified ({reason}); restricting briefing to confirmed anchor identity"
            )
            context["web_search"] = (
                "(omitted — web results did not reliably match the subject; "
                "analysis is restricted to the confirmed GitHub/social identity)"
            )
            context["deep_context"] = ""
            deep_context = ""
        logger.log_success("Web search aggregation and deep-packet inspection completed")

        if company_records:
            logger.log_success(f"Company registry scan: {len(company_records)} affiliation(s) detected")
        else:
            logger.log_action("Company registry scan: no corporate affiliations found")

        return context, deep_context, github_url, raw_sources

    # -----------------------------------------------------------------------
    # Step 4: Save context
    # -----------------------------------------------------------------------

    def save_context(self, raw_query: str, context: dict) -> None:
        """Persist the assembled context to a JSON file under ``data/contexts``.

        Nothing is indexed into a vector store here — there is no ChromaDB (or
        any other embedding index) anywhere in this path, despite what the log
        line says. It is a plain file write, and a failure is non-fatal.
        """
        try:
            os.makedirs("data/contexts", exist_ok=True)
            safe_filename = re.sub(r"[^a-zA-Z0-9_\-]", "_", raw_query.lower())
            with open(f"data/contexts/{safe_filename}.json", "w", encoding="utf-8") as f:
                json.dump(context, f, ensure_ascii=False, indent=2)
            logger.log_action("Context synchronized to local RAG knowledge base", target=safe_filename)
        except Exception as e:
            logger.log_warning(f"Failed to synchronize RAG context: {e}")

    # -----------------------------------------------------------------------
    # Step 5: Collect images (delegates to ImageCollectorStep helpers)
    # -----------------------------------------------------------------------

    def collect_images(
        self,
        social_profiles: Any,
        github_data: dict | None,
        wiki_image: str | None,
        real_name: str,
        profile_pictures: list[Any] | None = None,
    ) -> list[str]:
        """Build a deduplicated list of avatar/profile images."""
        return self._image_collector.collect_images(
            social_profiles, github_data, wiki_image, real_name, profile_pictures
        )

    def collect_face_images(
        self,
        social_profiles: Any,
        github_data: dict | None,
        wiki_image: str | None,
        profile_pictures: list[Any] | None = None,
    ) -> list[tuple[str, str]]:
        """Build labeled (platform, image) pairs for face matching."""
        return self._image_collector.collect_face_images(social_profiles, github_data, wiki_image, profile_pictures)

    # -----------------------------------------------------------------------
    # Step 6: Run AI + face match + sentiment (async — delegates to step)
    # -----------------------------------------------------------------------

    async def run_analysis(
        self, raw_query: str, context: dict, deep_context: str, face_images: list[tuple[str, str]]
    ) -> tuple[str, Any, Any]:
        """Generate AI response, run face matching and sentiment concurrently."""
        ctx = PipelineContext(
            raw_query=raw_query,
            context=context,
            deep_context=deep_context,
            face_images=face_images,
        )
        ctx = await self._analysis_runner.execute(ctx)
        return ctx.ai_response, ctx.face_match_report, ctx.sentiment_report

    # -----------------------------------------------------------------------
    # Step 7: Post-analysis (async — delegates to step)
    # -----------------------------------------------------------------------

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
        context: dict | None = None,
        deep_context: str | None = None,
        sentiment_report: dict | None = None,
        depth_config=None,
    ) -> dict:
        """Extract structured data, check breaches, cross-validate, compute scores."""
        # Reconstruct search_results tuple as PostAnalysisRunnerStep expects it
        search_results = (None, web_results, deep_context, raw_sources)

        ctx = PipelineContext(
            depth_config=depth_config,
            real_name=real_name,
            username=username,
            github_data=github_data,
            orch_result=orch_result,
            search_results=search_results,
            context=context,
            deep_context=deep_context,
            ai_response=ai_response,
            sentiment_report=sentiment_report,
        )
        ctx = await self._post_analysis_runner.execute(ctx)
        return ctx.post_analysis  # type: ignore[return-value]

    # -----------------------------------------------------------------------
    # Step 8: Build response
    # -----------------------------------------------------------------------

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
        depth_config=None,
    ) -> SearchResponse:
        """Assemble the final SearchResponse."""
        structured_data = post["structured_data"]

        # Pictures are NOT prefixed into `ai_response` as markdown any more. They
        # travel in the typed `profile_pictures` field (populated by
        # `discovery_bridge.to_api`), so a URL that stops resolving no longer
        # renders as a broken image in the middle of the biography.
        if images:
            logger.log_success(f"{len(images)} visual identity source(s) collected.")

        logger.log_success("Analysis complete")
        sp_keys = [k for k, v in social_profiles.items() if v]
        logger.log_action(f"[DIAG] build_response: {len(sp_keys)} platform(s): {sp_keys[:5]}")

        response = SearchResponse(
            name=structured_data.get("name", real_name),
            github_url=github_url or None,
            instagram_url=_join_urls(social_profiles, "instagram"),
            twitter_url=_join_urls(social_profiles, "twitter"),
            linkedin_url=_join_urls(social_profiles, "linkedin"),
            spotify_url=_join_urls(social_profiles, "spotify"),
            tiktok_url=_join_urls(social_profiles, "tiktok"),
            snapchat_url=_join_urls(social_profiles, "snapchat"),
            tumblr_url=_join_urls(social_profiles, "tumblr"),
            youtube_url=_join_urls(social_profiles, "youtube"),
            reddit_url=_join_urls(social_profiles, "reddit"),
            facebook_url=_join_urls(social_profiles, "facebook"),
            pinterest_url=_join_urls(social_profiles, "pinterest"),
            threads_url=_join_urls(social_profiles, "threads"),
            steam_url=_join_urls(social_profiles, "steam"),
            tinder_mention=_join_bios(social_profiles, "tinder"),
            bumble_mention=_join_bios(social_profiles, "bumble"),
            discord_mention=_join_bios(social_profiles, "discord"),
            phone_numbers=sanitize_phone_list(post["phone_numbers"]) or None,
            location_country=structured_data.get("estimated_location"),
            location_city=structured_data.get("capital_city"),
            weather_info=post["weather_info"],
            social_media_score=post["score_result"]["total_score"],
            social_media_score_breakdown=post["score_result"]["breakdown"],
            last_activity_summary=_format_last_activity(github_data, social_profiles),
            platform_activity=post["platform_activity"],
            description=structured_data.get("description"),
            additional_info=structured_data.get("additional_info"),
            # Sanitized because these come straight from LLM-extracted JSON and the
            # schema validators reject a single malformed item outright.
            network_connections=sanitize_network_connections(structured_data.get("network_connections")),
            similar_profiles=sanitize_str_list(structured_data.get("similar_profiles")),
            cross_validation_issues=sanitize_str_list(post["all_issues"]),
            email_addresses=sanitize_email_list(structured_data.get("email_addresses")),
            data_breaches=sanitize_breach_list(post["data_breaches"]),
            sources=raw_sources,
            ai_response=ai_response,
            company_records=orch_result.company_records if orch_result.company_records else None,
            geoint_data=post.get("geoint_data") or None,
            timezone_analysis=post.get("timezone_analysis") or None,
        )

        if face_match_report:
            _assign_optional(response, "face_match_results", face_match_report)
        if sentiment_report:
            _assign_optional(response, "sentiment_analysis", sentiment_report)
            logger.log_success(f"Sentiment matrix locked: {sentiment_report.get('dominant_emotion', 'N/A')}")

        if depth_config:
            _assign_optional(response, "search_depth", depth_config.depth)
            _assign_optional(response, "search_tier", depth_config.tier)

        # Optional enrichment sections. Several are LLM-generated and can violate
        # their schema (out-of-range scores, unexpected shapes); dropping one is
        # the right trade against discarding a search that ran for minutes.
        for field in (
            "psychological_analysis",
            "prediction_data",
            "domain_intel",
            "claims",
            "archive_snapshots",
            "scholarly_records",
            "sanctions_hits",
            "timeline",
            "alternative_candidates",
            "relationships",
        ):
            if post.get(field):
                _assign_optional(response, field, post[field])

        if post.get("subject_confidence") is not None:
            _assign_optional(response, "subject_confidence", post["subject_confidence"])

        return response

    # -----------------------------------------------------------------------
    # Step 9: Save history
    # -----------------------------------------------------------------------

    def save_history(self, db, raw_query: str, response: SearchResponse) -> None:
        """Save version snapshot and the conversation row the Logs panel lists."""
        try:
            self._version.save_snapshot(db, raw_query, response)
            change_report = self._version.generate_change_report(db, raw_query)
            if change_report and change_report.has_changes:
                response.version_history = change_report.model_dump(mode="json")
                logger.log_success(f"Version history: {len(change_report.changes)} change(s) detected")
            elif change_report:
                response.version_history = change_report.model_dump(mode="json")
                logger.log_action("Version history: No changes detected since last scan")
            else:
                logger.log_action("Version history: First snapshot saved — no previous data to compare")
        except Exception as e:
            logger.log_warning(f"Version history snapshot failed (non-critical): {e}")

        # A conversation row, not a `search_history` row: the Logs panel reads
        # `search_sessions` so that this path and the interactive one produce the
        # same list. `interactive=False` is what distinguishes them.
        try:
            now = datetime.now(UTC)
            db.add(
                SearchSession(
                    id=str(uuid.uuid4()),
                    target_key=target_key_for(raw_query, EntityType.PERSON),
                    raw_query=raw_query,
                    entity_type=EntityType.PERSON.value,
                    interactive=False,
                    status="completed",
                    termination_reason="blocking_fallback",
                    result_json=response.model_dump(mode="json"),
                    started_at=now,
                    finished_at=now,
                )
            )
            db.flush()
        except Exception as e:
            logger.log_warning(f"Failed to record the conversation: {e}")
