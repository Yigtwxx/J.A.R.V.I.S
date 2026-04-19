"""Step 3 — convert raw fetch results into enriched context dicts."""
from __future__ import annotations

from typing import Any

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

        # Institutional intelligence
        if orch_result.academic_context or orch_result.patent_context or orch_result.registry_context:
            deep_context += "\n\n=== VERIFIED INSTITUTIONAL INTELLIGENCE ===\n"
            if orch_result.academic_context:
                deep_context += orch_result.academic_context + "\n"
            if orch_result.patent_context:
                deep_context += orch_result.patent_context + "\n"
            if orch_result.registry_context:
                deep_context += orch_result.registry_context + "\n"
        else:
            deep_context += (
                "\n\n=== VERIFIED INSTITUTIONAL INTELLIGENCE ===\n"
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

        # Social media
        context['social_media'] = self._scraper.format_social_profiles(social_profiles)
        found_count = sum(1 for v in social_profiles.values() if v)
        logger.log_success(f"Found {found_count} social media profiles")

        # Web search
        context['web_search'] = web_results
        context['deep_context'] = deep_context
        logger.log_success("Web search aggregation and deep-packet inspection completed")

        if company_records:
            logger.log_success(f"Company registry scan: {len(company_records)} affiliation(s) detected")
        else:
            logger.log_action("Company registry scan: no corporate affiliations found")

        ctx.context = context
        ctx.deep_context = deep_context
        ctx.raw_sources = raw_sources
        return ctx
