"""Step 7 — breach check, cross-validation, scoring, GEOINT, psych, predictive."""
from __future__ import annotations

import asyncio
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

        # Step 1: Extract structured profile data — everything else depends on this
        structured_data = await self._ai.extract_profile_data(ctx.ai_response, ctx.real_name)

        # Step 2: Fast synchronous work (no I/O)
        algo_issues = SecurityAgent.cross_validate(
            github_data or {}, social_profiles, web_results or '', ctx.real_name, ctx.username
        )
        ai_issues = structured_data.get('cross_validation_issues', [])
        if not isinstance(ai_issues, list):
            ai_issues = [str(ai_issues)] if ai_issues else []
        ai_issues = [str(i) for i in ai_issues if i]
        all_issues = list(dict.fromkeys(algo_issues + ai_issues))
        logger.log_action(f"Cross-validation complete: {len(all_issues)} issue(s) detected")

        weather_info = None
        if structured_data.get('capital_city'):
            weather_info = self._weather.get_weather(structured_data['capital_city'])

        logger.log_action("Computing Digital Impact Score...")
        score_result = self._score.calculate_score(
            github_data=github_data,
            social_profiles=social_profiles,
            raw_sources=raw_sources,
            web_results=web_results or '',
        )

        platform_activity = (
            orch_result.platform_activity
            or SocialMediaAgent._compute_platform_activity(github_data, social_profiles)
        )

        # Step 3: Fan-out all slow async I/O concurrently
        async def _run_breach() -> list:
            return await self._breach_orch.run_breach_check(
                emails=structured_data.get('email_addresses', [])
            )

        async def _run_darkweb() -> dict:
            if not self._darkweb:
                return {}
            return await self._darkweb.aggregate_deep_intel(
                emails=structured_data.get('email_addresses', []),
                username=ctx.username,
                real_name=ctx.real_name,
            )

        async def _run_geoint() -> tuple:
            if not self._geoint:
                return [], None
            g_data = await self._geoint.aggregate_locations(
                location_country=structured_data.get('estimated_location'),
                location_city=structured_data.get('capital_city'),
                company_records=orch_result.company_records,
            )
            commit_timestamps = []
            if github_data and github_data.get('recent_commits'):
                commit_timestamps = [
                    c.get('date', '') for c in github_data['recent_commits'] if c.get('date')
                ]
            tz = None
            if commit_timestamps:
                tz = self._geoint.analyze_activity_times(commit_timestamps)
                logger.log_action(
                    f"Timezone analysis: {tz.get('inferred_timezone', 'N/A')}"
                )
            return g_data, tz

        async def _run_psychological() -> Any:
            if not (self._psych and ctx.context):
                return None
            return await self._psych.analyze(
                context=ctx.context,
                deep_context=ctx.deep_context or "",
                sentiment_report=ctx.sentiment_report,
                structured_data=structured_data,
            )

        async def _run_predictive() -> Any:
            if not self._predictor:
                return None
            return await self._predictor.generate_predictions(
                github_data=github_data,
                social_profiles=social_profiles,
                platform_activity=platform_activity,
                timezone_analysis=None,
                structured_data=structured_data,
                deep_context=ctx.deep_context or "",
            )

        breach_result, darkweb_result, geoint_result, psych_result, pred_result = (
            await asyncio.gather(
                _run_breach(),
                _run_darkweb(),
                _run_geoint(),
                _run_psychological(),
                _run_predictive(),
                return_exceptions=True,
            )
        )

        # Unpack breach
        data_breaches: list = []
        if isinstance(breach_result, Exception):
            logger.log_warning(f"Breach check failed (non-critical): {breach_result}")
        elif breach_result:
            data_breaches = breach_result

        # Unpack darkweb
        darkweb_intel: dict = {}
        if isinstance(darkweb_result, Exception):
            logger.log_warning(f"Dark web scan failed (non-critical): {darkweb_result}")
        elif darkweb_result:
            darkweb_intel = darkweb_result
            paste_count = len(darkweb_intel.get('paste_exposures', []))
            leak_count = len(darkweb_intel.get('leak_results', []))
            if paste_count or leak_count:
                logger.log_warning(
                    f"DARK WEB INTEL: {paste_count} paste(s), {leak_count} leak(s) detected"
                )
            else:
                logger.log_success("Dark web scan: No additional exposures detected")

        for paste in darkweb_intel.get('paste_exposures', []):
            data_breaches.append(paste)

        # Unpack geoint
        geoint_data: list = []
        timezone_analysis = None
        if isinstance(geoint_result, Exception):
            logger.log_warning(f"GEOINT aggregation failed (non-critical): {geoint_result}")
        elif geoint_result:
            geoint_data, timezone_analysis = geoint_result
            if geoint_data:
                logger.log_success(f"GEOINT: {len(geoint_data)} location(s) mapped")

        phone_numbers = orch_result.phone_numbers

        # Unpack psychological
        psychological_analysis = None
        if isinstance(psych_result, Exception):
            logger.log_warning(f"Psychological analysis failed (non-critical): {psych_result}")
        else:
            psychological_analysis = psych_result

        # Unpack predictive
        prediction_data = None
        if isinstance(pred_result, Exception):
            logger.log_warning(f"Predictive analysis failed (non-critical): {pred_result}")
        else:
            prediction_data = pred_result

        logger.log_success("Post-analysis complete")

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
