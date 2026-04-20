"""Step 8 — assemble the final SearchResponse from all collected data."""
from __future__ import annotations

from app.schemas import SearchResponse
from app.utils.logger import logger

from .base import PipelineStep
from .context import PipelineContext
from .utils import _format_last_activity, _join_bios, _join_urls


class ResponseBuilderStep(PipelineStep):
    @property
    def name(self) -> str:
        return "response_builder"

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        post = ctx.post_analysis  # type: ignore[assignment]
        structured_data = post['structured_data']
        social_profiles = ctx.orch_result.social_profiles
        images = ctx.images or []
        ai_response = ctx.ai_response or ""

        # Image injection
        if images:
            logger.log_success(f"Injecting {len(images[:6])} visual identities.")
            images_md = " ".join([f"![{ctx.real_name}]({img})" for img in images[:6]])
            ai_response = f"{images_md}\n\n" + ai_response

        logger.log_success("Analysis complete")
        sp_keys = [k for k, v in social_profiles.items() if v]
        logger.log_action(f"[DIAG] build_response: {len(sp_keys)} platform(s): {sp_keys[:5]}")

        response = SearchResponse(
            name=structured_data.get('name', ctx.real_name),
            github_url=ctx.github_url or None,
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
            last_activity_summary=_format_last_activity(ctx.github_data, social_profiles),
            platform_activity=post['platform_activity'],
            description=structured_data.get('description'),
            additional_info=structured_data.get('additional_info'),
            network_connections=structured_data.get('network_connections', []),
            similar_profiles=structured_data.get('similar_profiles', []),
            cross_validation_issues=post['all_issues'],
            email_addresses=structured_data.get('email_addresses', []),
            data_breaches=post['data_breaches'],
            sources=ctx.raw_sources,
            ai_response=ai_response,
            company_records=ctx.orch_result.company_records or None,
            geoint_data=post.get('geoint_data') or None,
            timezone_analysis=post.get('timezone_analysis') or None,
        )

        if ctx.face_match_report:
            response.face_match_results = ctx.face_match_report
        if ctx.sentiment_report:
            response.sentiment_analysis = ctx.sentiment_report
            logger.log_success(
                f"Sentiment matrix locked: "
                f"{ctx.sentiment_report.get('dominant_emotion', 'N/A')}"
            )

        if ctx.depth_config:
            response.search_depth = ctx.depth_config.depth
            response.search_tier = ctx.depth_config.tier

        if post.get('tactical_analysis'):
            response.tactical_analysis = post['tactical_analysis']
        if post.get('psychological_analysis'):
            response.psychological_analysis = post['psychological_analysis']
        if post.get('prediction_data'):
            response.prediction_data = post['prediction_data']

        ctx.response = response
        return ctx
