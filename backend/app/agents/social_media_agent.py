from __future__ import annotations
from typing import Any
import asyncio
import math
from datetime import datetime, timezone, timedelta

from .base_agent import BaseAgent, AgentResult, StatusCallback


class SocialMediaAgent(BaseAgent):
    def __init__(
        self,
        scraper_service: Any,
        username: str,
        real_name: str,
        status_callback: StatusCallback,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        super().__init__(status_callback, loop)
        self._scraper   = scraper_service
        self._username  = username
        self._real_name = real_name

    @property
    def agent_name(self) -> str:
        return "SocialMediaAgent"

    async def run_async(self) -> AgentResult:
        self._broadcast(f"[SYS] SocialMediaAgent: scanning profiles for {self._username}")

        # 1. find_all_profiles(username)
        social_profiles = await self._run_sync(self._scraper.find_all_profiles, self._username)

        # 2. Merge by real_name if different from username
        if self._real_name.lower() != self._username.lower():
            social_by_name = await self._run_sync(self._scraper.find_all_profiles, self._real_name)
            for platform, items in social_by_name.items():
                existing_urls = {p['url'] for p in social_profiles.get(platform, [])}
                for item in items:
                    if item['url'] not in existing_urls:
                        social_profiles.setdefault(platform, []).append(item)

        found_count = sum(1 for v in social_profiles.values() if v)
        self._broadcast(f"[OK] SocialMediaAgent: {found_count} platform(s) found")

        return AgentResult(
            agent_name=self.agent_name,
            social_profiles=social_profiles,
        )

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
            followers = github_data.get('followers', 0) or 0
            if followers > 0:
                score += min(20, int(math.log10(followers + 1) * 7))
            repos = github_data.get('public_repos', 0) or 0
            if repos > 0:
                score += min(20, int(math.log10(repos + 1) * 12))
            last_active = github_data.get('last_active')
            if last_active:
                try:
                    if isinstance(last_active, str):
                        last_dt = datetime.fromisoformat(last_active.replace('Z', '+00:00'))
                    else:
                        last_dt = last_active
                    days = (datetime.now(timezone.utc) - last_dt).days
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
            activity['github'] = min(100, score)

        # --- Standard social platforms ---
        standard_platforms = ['instagram', 'twitter', 'linkedin', 'tiktok', 'snapchat', 'tumblr', 'youtube', 'reddit', 'facebook']
        for platform in standard_platforms:
            items = social_profiles.get(platform, [])
            if items:
                score = 60  # Profile found = solid base
                for item in items:
                    if item.get('bio') and len(item['bio'].strip()) > 10:
                        score += 40
                        break
                activity[platform] = min(100, score)

        # --- Passive platforms (Spotify) ---
        if social_profiles.get('spotify'):
            activity['spotify'] = 60

        # --- Mention-only platforms (Tinder, Bumble) ---
        for platform in ['tinder', 'bumble']:
            if social_profiles.get(platform):
                activity[platform] = 40

        return activity
