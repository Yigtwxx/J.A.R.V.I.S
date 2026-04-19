"""Step 2 — fetch GitHub, social, and web data in parallel."""
from __future__ import annotations

import asyncio
from typing import Any

from app.utils.logger import logger

from .base import PipelineStep
from .context import PipelineContext


class DataFetcherStep(PipelineStep):
    def __init__(self, github_service: Any, search_service: Any, search_orchestrator: Any) -> None:
        self._github = github_service
        self._search = search_service
        self._orchestrator = search_orchestrator

    @property
    def name(self) -> str:
        return "data_fetcher"

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        loop = asyncio.get_running_loop()
        tier_label = ctx.depth_config.tier if ctx.depth_config else "medium"
        logger.log_action(f"Launching parallel intelligence gathering (tier: {tier_label})...")

        github_future = loop.run_in_executor(None, self._github.search_user, ctx.username)
        search_future = loop.run_in_executor(
            None, self._search.search_person, ctx.real_name, ctx.depth_config,
        )

        orch_result, github_data, search_results = await self._orchestrator.run_parallel(
            username=ctx.username,
            real_name=ctx.real_name,
            github_future=github_future,
            search_future=search_future,
            depth_config=ctx.depth_config,
        )

        ctx.orch_result = orch_result
        ctx.github_data = github_data
        ctx.search_results = search_results
        return ctx
