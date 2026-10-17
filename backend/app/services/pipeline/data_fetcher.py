"""Step 2 — fetch GitHub, social, and web data in parallel."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from app.config import get_settings
from app.discovery.types import EntityType
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
            None,
            self._search.search_person,
            ctx.real_name,
            ctx.depth_config,
        )

        # Social discovery and the legacy enrichment run concurrently. They are
        # independent: discovery finds and verifies accounts, the orchestrator
        # gathers GitHub, registry, breach and web context.
        discovery_task = asyncio.create_task(self._run_discovery(ctx))

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
        ctx.discovery_result = await discovery_task

        if ctx.discovery_result is not None and orch_result is not None:
            # Hand the legacy shape the accounts discovery actually verified, so
            # platform-activity and scoring downstream keep working unchanged.
            legacy = legacy_social_profiles(ctx.discovery_result)
            if legacy:
                orch_result.social_profiles = legacy
        return ctx

    async def _run_discovery(self, ctx: PipelineContext) -> Any | None:
        """Run the discovery pipeline non-interactively, or None if it is off.

        A failure here degrades the response rather than failing the request: the
        legacy enrichment is still worth returning on its own.
        """
        settings = get_settings()
        if not settings.discovery_enabled:
            return None
        try:
            from app.discovery.dependencies import get_discovery_runner

            runner = get_discovery_runner()
            depth = getattr(ctx.depth_config, "depth", 5) or 5
            return await runner.run(
                session_id=str(uuid.uuid4()),
                raw_query=ctx.real_name,
                entity_type=EntityType.PERSON,
                depth=depth,
                interactive=False,
            )
        except Exception as exc:
            logger.log_warning(f"Discovery pipeline failed (non-critical): {type(exc).__name__}: {exc}")
            return None


def legacy_social_profiles(result: Any) -> dict[str, list[dict[str, Any]]]:
    """Convert discovery profiles into the legacy ``{platform: [{url, bio}]}`` shape.

    Only accounts that were actually verified are included. The removed scraper
    used to inject a ``[SEARCH]`` placeholder for every empty platform, which made
    an empty result impossible to express and fed search-page URLs to the LLM.
    """
    out: dict[str, list[dict[str, Any]]] = {}
    for candidate in getattr(result, "profiles", []) or []:
        if not getattr(candidate, "is_live", False):
            continue
        entry = {
            "url": candidate.url,
            "bio": (candidate.bio or "")[:400],
            "username": candidate.username,
            "confidence": candidate.score.value,
        }
        out.setdefault(candidate.platform, []).append(entry)
    return out
