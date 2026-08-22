from __future__ import annotations

import asyncio
import math
from datetime import UTC, datetime
from typing import Any

from .base_agent import AgentResult, BaseAgent, StatusCallback


class SocialMediaAgent(BaseAgent):
    def __init__(
        self,
        scraper_service: Any,
        username: str,
        real_name: str,
        status_callback: StatusCallback,
        loop: asyncio.AbstractEventLoop,
        depth_config: Any = None,
    ) -> None:
        super().__init__(status_callback, loop)
        self._scraper = scraper_service
        self._username = username
        self._real_name = real_name
        self._depth_config = depth_config

    @property
    def agent_name(self) -> str:
        return "SocialMediaAgent"

    async def run_async(self) -> AgentResult:
        """Contribute no profiles — social discovery lives in `app/discovery/`.

        This agent drove `ScraperService.find_all_profiles`, which was deleted:
        it read HTTP 403/429 as "the profile exists" and injected a `[SEARCH]`
        placeholder for every platform that returned nothing, so it could not
        report an empty result even when there was one. Returning nothing is the
        honest outcome; the discovery pipeline supplies the real accounts.

        `_compute_platform_activity` below is still used by the orchestrator and
        is unaffected — it reads whatever profiles it is handed.
        """
        self._broadcast(
            f"[SYS] SocialMediaAgent: social discovery for {self._username} is handled by the discovery pipeline"
        )
        return AgentResult(agent_name=self.agent_name, social_profiles={})

    @staticmethod
    def _compute_platform_activity(github_data: dict | None, social_profiles: dict) -> dict:
        """
        Compute a 0-100 activity percentage for each detected platform.
        Returns: { "github": 85, "instagram": 60, ... } (only found platforms)
        """
        activity: dict[str, int] = {}

        # --- GitHub (richest data) ---
        if github_data:
            score = 30  # Base: profile exists
            followers = github_data.get("followers", 0) or 0
            if followers > 0:
                score += min(20, int(math.log10(followers + 1) * 7))
            repos = github_data.get("public_repos", 0) or 0
            if repos > 0:
                score += min(20, int(math.log10(repos + 1) * 12))
            last_active = github_data.get("last_active")
            if last_active:
                try:
                    if isinstance(last_active, str):
                        last_dt = datetime.fromisoformat(last_active.replace("Z", "+00:00"))
                    else:
                        last_dt = last_active
                    days = (datetime.now(UTC) - last_dt).days
                    if days <= 7:
                        score += 30
                    elif days <= 30:
                        score += 22
                    elif days <= 90:
                        score += 15
                    elif days <= 365:
                        score += 8
                    else:
                        score += 2
                except (ValueError, TypeError):
                    pass
            activity["github"] = min(100, score)

        # --- Standard social platforms ---
        standard_platforms = [
            "instagram",
            "twitter",
            "linkedin",
            "tiktok",
            "snapchat",
            "tumblr",
            "youtube",
            "reddit",
            "facebook",
            "pinterest",
            "threads",
            "steam",
        ]
        for platform in standard_platforms:
            items = social_profiles.get(platform, [])
            if items:
                score = 60  # Profile found = solid base
                for item in items:
                    if item.get("bio") and len(item["bio"].strip()) > 10:
                        score += 40
                        break
                activity[platform] = min(100, score)

        # --- Passive platforms (Spotify) ---
        if social_profiles.get("spotify"):
            activity["spotify"] = 60

        # --- Mention-only platforms (Tinder, Bumble) ---
        for platform in ["tinder", "bumble"]:
            if social_profiles.get(platform):
                activity[platform] = 40

        return activity
