"""Step 3 — convert raw fetch results into enriched context dicts."""
from __future__ import annotations

from typing import Any

from app.services.identity_resolver import (
    anchor_corroborated_by_web,
    classify_profiles,
    filter_intelligence_sources,
    web_relevance_ratio,
)
from app.utils.logger import logger

from .base import PipelineStep
from .context import PipelineContext


class ResultProcessorStep(PipelineStep):
    def __init__(self, github_service: Any, scraper_service: Any) -> None:
        self._github = github_service
        self._scraper = scraper_service

    @property
    def name(self) -> str:
        return "result_processor"

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        orch_result = ctx.orch_result
        github_data = ctx.github_data
        wiki_image, web_results, deep_context, raw_sources = ctx.search_results  # type: ignore[misc]

        context: dict = {}
        social_profiles = orch_result.social_profiles
        company_records = orch_result.company_records

        # Drop web/deep sources about a different same-name person before analysis.
        web_results, deep_context, dropped = filter_intelligence_sources(
            ctx.real_name, web_results, deep_context, raw_sources
        )
        if dropped:
            logger.log_warning(f"Filtered {dropped} off-target (different-name) web source(s) from analysis context")

        # Institutional intelligence
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

        # GitHub
        ctx.github_url = None
        if github_data:
            context['github'] = self._github.format_github_data(github_data)
            ctx.github_url = github_data.get('profile_url')
            logger.log_success(f"GitHub profile found: {ctx.github_url}")
        else:
            logger.log_warning("No GitHub profile found")

        # Social media — disambiguate same-name namesakes before formatting.
        classification = classify_profiles(social_profiles, github_data, ctx.real_name, web_results or "")
        context['anchor'] = classification.get('anchor')
        context['social_media'] = self._scraper.format_social_profiles(social_profiles, classification)
        found_count = sum(1 for v in social_profiles.values() if v)
        logger.log_success(f"Found {found_count} social media profiles")
        if classification.get('has_others'):
            logger.log_warning("Same-name candidate profiles detected — isolating primary target for analysis")

        # Web search
        context['web_search'] = web_results
        context['deep_context'] = deep_context

        # Low-confidence gate: restrict the briefing to the confirmed anchor when the
        # web corpus is dominated by a different same-name person (GitHub anchor not
        # corroborated by a distinctive login/profile, or low name match without one).
        relevance = web_relevance_ratio(ctx.real_name, raw_sources)
        corroborated = anchor_corroborated_by_web(github_data, raw_sources, deep_context)
        has_anchor = bool(github_data) or found_count > 0
        low_signal = corroborated is False or (
            corroborated is None and relevance is not None and relevance < 0.5
        )
        if has_anchor and low_signal:
            reason = "anchor not corroborated by web" if corroborated is False else f"low web-name match ({relevance})"
            logger.log_warning(
                f"Subject weakly identified ({reason}); restricting briefing to confirmed anchor identity"
            )
            context['web_search'] = (
                "(omitted — web results did not reliably match the subject; "
                "analysis is restricted to the confirmed GitHub/social identity)"
            )
            context['deep_context'] = ""
            deep_context = ""
        logger.log_success("Web search aggregation and deep-packet inspection completed")

        if company_records:
            logger.log_success(f"Company registry scan: {len(company_records)} affiliation(s) detected")
        else:
            logger.log_action("Company registry scan: no corporate affiliations found")

        ctx.context = context
        ctx.deep_context = deep_context
        ctx.raw_sources = raw_sources
        return ctx
