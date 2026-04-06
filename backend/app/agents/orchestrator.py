from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .base_agent import AgentResult
from .deep_search_agent import DeepSearchAgent
from .legal_records_agent import LegalRecordsAgent
from .security_agent import SecurityAgent
from .social_media_agent import SocialMediaAgent


@dataclass
class OrchestratorResult:
    social_profiles:   dict[str, list]       = field(default_factory=dict)
    phone_numbers:     list[str]             = field(default_factory=list)
    platform_activity: dict[str, int]        = field(default_factory=dict)
    company_records:   list[dict[str, Any]]  = field(default_factory=list)
    academic_context:  str                   = ""
    patent_context:    str                   = ""
    registry_context:  str                   = ""
    data_breaches:     list[dict[str, Any]]  = field(default_factory=list)
    agent_results:     list[AgentResult]     = field(default_factory=list)


class SearchOrchestrator:
    def __init__(
        self,
        scraper_service: Any,
        company_service: Any,
        search_service: Any,
        breach_service: Any,
        status_callback: Callable[[str], None],
    ) -> None:
        self._scraper  = scraper_service
        self._company  = company_service
        self._search   = search_service
        self._breach   = breach_service
        self._status   = status_callback

    async def run_parallel(
        self,
        username: str,
        real_name: str,
        github_future,
        search_future,
        depth_config=None,
    ) -> tuple[OrchestratorResult, dict | None, tuple]:
        """
        Phase 1: SocialMediaAgent + LegalRecordsAgent + github_future + search_future
        run concurrently via asyncio.gather().  When depth_config.multi_agent is True,
        a DeepSearchAgent is also spawned in parallel.

        After gather: GitHub correlation and platform_activity computation are applied.
        Returns: (orch_result, github_data, search_results)
        """
        loop = asyncio.get_running_loop()

        social_agent = SocialMediaAgent(
            scraper_service=self._scraper,
            username=username,
            real_name=real_name,
            status_callback=self._status,
            loop=loop,
            depth_config=depth_config,
        )
        legal_agent = LegalRecordsAgent(
            company_service=self._company,
            search_service=self._search,
            name=real_name,
            status_callback=self._status,
            loop=loop,
        )

        # Optionally spawn DeepSearchAgent for depth >= 7
        use_deep = depth_config and depth_config.multi_agent
        if use_deep:
            deep_agent = DeepSearchAgent(
                search_service=self._search,
                name=real_name,
                depth=depth_config.depth,
                status_callback=self._status,
                loop=loop,
            )
            social_result, legal_result, deep_result, github_data, search_results = await asyncio.gather(
                social_agent.run(),
                legal_agent.run(),
                deep_agent.run(),
                github_future,
                search_future,
            )
        else:
            deep_result = None
            social_result, legal_result, github_data, search_results = await asyncio.gather(
                social_agent.run(),
                legal_agent.run(),
                github_future,
                search_future,
            )

        social_profiles = social_result.social_profiles

        # GitHub correlation: apply after we have github_data
        if github_data and github_data.get('username'):
            gh_username = github_data['username']

            # 1. GitHub API gives Twitter handle — inject directly
            if github_data.get('twitter') and not social_profiles.get('twitter'):
                tw_url = f"https://x.com/{github_data['twitter']}"
                social_profiles['twitter'] = [{"url": tw_url, "bio": ""}]
                self._status(f"[OK] Twitter correlated via GitHub API: {tw_url}")

            # 2. Try same username on other platforms
            username_hits = await loop.run_in_executor(
                None, self._scraper.find_profiles_by_username, gh_username
            )
            for platform, items in username_hits.items():
                if items and not social_profiles.get(platform):
                    social_profiles[platform] = items

        # Phone extraction (needs deep_context from search_results)
        wiki_image, web_results, deep_context, raw_sources = search_results
        phone_numbers = self._scraper.extract_phone_numbers(real_name, deep_context)

        # Per-platform activity scores
        platform_activity = SocialMediaAgent._compute_platform_activity(github_data, social_profiles)

        found = [k for k, v in social_profiles.items() if v]
        self._status(f"[DIAG] Orchestrator: {len(found)} platform(s) in final result: {found[:5]}")

        # Merge deep-search extra context if available
        extra_academic = legal_result.academic_context
        extra_registry = legal_result.registry_context
        agent_list = [social_result, legal_result]

        if deep_result and deep_result.success:
            if deep_result.academic_context:
                extra_academic += "\n" + deep_result.academic_context
            if deep_result.registry_context:
                extra_registry += "\n" + deep_result.registry_context
            agent_list.append(deep_result)

        orch_result = OrchestratorResult(
            social_profiles=social_profiles,
            phone_numbers=phone_numbers or [],
            platform_activity=platform_activity,
            company_records=legal_result.company_records,
            academic_context=extra_academic,
            patent_context=legal_result.patent_context,
            registry_context=extra_registry,
            data_breaches=[],
            agent_results=agent_list,
        )

        return orch_result, github_data, search_results

    async def run_breach_check(self, emails: list[str]) -> list[dict]:
        """
        Phase 2: Run SecurityAgent breach check after AI has extracted emails.
        """
        loop = asyncio.get_running_loop()
        security_agent = SecurityAgent(
            breach_service=self._breach,
            emails=emails,
            status_callback=self._status,
            loop=loop,
        )
        result = await security_agent.run()
        return result.data_breaches
