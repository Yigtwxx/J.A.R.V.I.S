"""Step 7 — breach check, cross-validation, scoring, GEOINT, psych, predictive."""
from __future__ import annotations

from typing import Any

from app.utils.logger import logger

from .base import PipelineStep
from .context import PipelineContext


class PostAnalysisRunnerStep(PipelineStep):
    def __init__(
        self,
        ai_service: Any,
        breach_orchestrator: Any,
        score_service: Any,
        weather_service: Any,
        darkweb_service: Any = None,
        geoint_service: Any = None,
        psychological_service: Any = None,
        predictive_service: Any = None,
    ) -> None:
        self._ai = ai_service
        self._breach_orch = breach_orchestrator
        self._score = score_service
        self._weather = weather_service
        self._darkweb = darkweb_service
        self._geoint = geoint_service
        self._psych = psychological_service
        self._predictor = predictive_service

    @property
    def name(self) -> str:
        return "post_analysis_runner"

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        from app.agents.security_agent import SecurityAgent
        from app.agents.social_media_agent import SocialMediaAgent

        orch_result = ctx.orch_result
        github_data = ctx.github_data
        social_profiles = orch_result.social_profiles
        wiki_image, web_results, deep_context, raw_sources = ctx.search_results  # type: ignore[misc]

        structured_data = await self._ai.extract_profile_data(ctx.ai_response, ctx.real_name)

        # Breach check
        data_breaches = await self._breach_orch.run_breach_check(
            emails=structured_data.get('email_addresses', [])
        )

        # Cross-validation
        algo_issues = SecurityAgent.cross_validate(
            github_data or {}, social_profiles, web_results or '', ctx.real_name, ctx.username
        )
        ai_issues = structured_data.get('cross_validation_issues', [])
        if not isinstance(ai_issues, list):
            ai_issues = [str(ai_issues)] if ai_issues else []
        ai_issues = [str(i) for i in ai_issues if i]
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

        # Dark web intelligence
        darkweb_intel: dict = {}
        if self._darkweb:
            try:
                logger.log_action("Scanning dark web and paste site databases...")
                darkweb_intel = await self._darkweb.aggregate_deep_intel(
                    emails=structured_data.get('email_addresses', []),
                    username=ctx.username,
                    real_name=ctx.real_name,
                )
                paste_count = len(darkweb_intel.get('paste_exposures', []))
                leak_count = len(darkweb_intel.get('leak_results', []))
                if paste_count or leak_count:
                    logger.log_warning(
                        f"DARK WEB INTEL: {paste_count} paste(s), {leak_count} leak(s) detected"
                    )
                else:
                    logger.log_success("Dark web scan: No additional exposures detected")
            except Exception as e:
                logger.log_warning(f"Dark web scan failed (non-critical): {e}")

        for paste in darkweb_intel.get('paste_exposures', []):
            data_breaches.append(paste)

        # GEOINT
        geoint_data: list = []
        timezone_analysis = None
        if self._geoint:
            try:
                logger.log_action("Aggregating geographic intelligence (GEOINT)...")
                geoint_data = await self._geoint.aggregate_locations(
                    location_country=structured_data.get('estimated_location'),
                    location_city=structured_data.get('capital_city'),
                    company_records=orch_result.company_records,
                )
                commit_timestamps = []
                if github_data and github_data.get('recent_commits'):
                    commit_timestamps = [
                        c.get('date', '') for c in github_data['recent_commits'] if c.get('date')
                    ]
                if commit_timestamps:
                    timezone_analysis = self._geoint.analyze_activity_times(commit_timestamps)
                    logger.log_action(
                        f"Timezone analysis: {timezone_analysis.get('inferred_timezone', 'N/A')}"
                    )
                if geoint_data:
                    logger.log_success(f"GEOINT: {len(geoint_data)} location(s) mapped")
            except Exception as e:
                logger.log_warning(f"GEOINT aggregation failed (non-critical): {e}")

        # Phone numbers & platform activity
        phone_numbers = orch_result.phone_numbers
        platform_activity = (
            orch_result.platform_activity
            or SocialMediaAgent._compute_platform_activity(github_data, social_profiles)
        )

        # Psychological warfare analysis
        psychological_analysis = None
        if self._psych and ctx.context:
            try:
                logger.log_action("Initiating psychological warfare analysis...")
                psychological_analysis = await self._psych.analyze(
                    context=ctx.context,
                    deep_context=ctx.deep_context or "",
                    sentiment_report=ctx.sentiment_report,
                    structured_data=structured_data,
                )
            except Exception as e:
                logger.log_warning(f"Psychological analysis failed (non-critical): {e}")

        # Predictive analytics
        prediction_data = None
        if self._predictor:
            try:
                logger.log_action("Running predictive analytics engine...")
                prediction_data = await self._predictor.generate_predictions(
                    github_data=github_data,
                    social_profiles=social_profiles,
                    platform_activity=platform_activity,
                    timezone_analysis=timezone_analysis,
                    structured_data=structured_data,
                    deep_context=ctx.deep_context or "",
                )
            except Exception as e:
                logger.log_warning(f"Predictive analysis failed (non-critical): {e}")

        ctx.post_analysis = {
            'structured_data': structured_data,
            'data_breaches': data_breaches,
            'all_issues': all_issues,
            'weather_info': weather_info,
            'score_result': score_result,
            'phone_numbers': phone_numbers,
            'platform_activity': platform_activity,
            'darkweb_intel': darkweb_intel,
            'geoint_data': geoint_data,
            'timezone_analysis': timezone_analysis,
            'psychological_analysis': psychological_analysis,
            'prediction_data': prediction_data,
        }
        return ctx
