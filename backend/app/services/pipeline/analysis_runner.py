"""Step 6 — run AI generation, face matching, and sentiment analysis concurrently."""
from __future__ import annotations

import asyncio
from typing import Any

from app.utils.logger import logger

from .base import PipelineStep
from .context import PipelineContext


class AnalysisRunnerStep(PipelineStep):
    def __init__(self, ai_service: Any, face_matching_service: Any) -> None:
        self._ai = ai_service
        self._face = face_matching_service

    @property
    def name(self) -> str:
        return "analysis_runner"

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        loop = asyncio.get_running_loop()
        logger.log_action("Running cognitive analysis...")

        ai_response = await self._ai.generate_response(
            prompt=f"Tell me everything you know about {ctx.raw_query}",
            context=ctx.context,
        )

        async def run_face_match():
            if ctx.face_images and len(ctx.face_images) >= 2:
                try:
                    logger.log_action(
                        f"Initiating biometric cross-reference across "
                        f"{len(ctx.face_images)} inputs..."
                    )
                    return await loop.run_in_executor(
                        None, self._face.analyze_all_images, ctx.face_images
                    )
                except Exception as e:
                    logger.log_warning(f"Face matching failed (non-critical): {e}")
            return None

        async def run_sentiment():
            if ctx.deep_context:
                try:
                    logger.log_action("Initiating socio-psychological sentiment analysis...")
                    return await self._ai.analyze_sentiment(ctx.deep_context)
                except Exception as e:
                    logger.log_warning(f"Sentiment analysis failed (non-critical): {e}")
            return None

        face_match_report, sentiment_report = await asyncio.gather(
            run_face_match(), run_sentiment(), return_exceptions=True,
        )
        if isinstance(face_match_report, BaseException):
            logger.log_warning(f"Face match gather exception: {face_match_report}")
            face_match_report = None
        if isinstance(sentiment_report, BaseException):
            logger.log_warning(f"Sentiment gather exception: {sentiment_report}")
            sentiment_report = None

        ctx.ai_response = ai_response
        ctx.face_match_report = face_match_report
        ctx.sentiment_report = sentiment_report
        return ctx
