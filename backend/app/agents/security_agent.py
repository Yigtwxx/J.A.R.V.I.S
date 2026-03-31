from __future__ import annotations

import asyncio
import unicodedata
from typing import Any

from .base_agent import AgentResult, BaseAgent, StatusCallback


def _normalize_text(text: str) -> str:
    """Normalize Unicode text: remove diacritics for fuzzy comparison."""
    nfkd = unicodedata.normalize('NFKD', text.lower())
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


class SecurityAgent(BaseAgent):
    def __init__(
        self,
        breach_service: Any,
        emails: list[str],
        status_callback: StatusCallback,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        super().__init__(status_callback, loop)
        self._breach = breach_service
        self._emails = emails

    @property
    def agent_name(self) -> str:
        return "SecurityAgent"

    async def run_async(self) -> AgentResult:
        self._broadcast(f"[SYS] SecurityAgent: checking {len(self._emails)} email(s) for breaches")

        data_breaches = await self._breach.check_breaches(self._emails)

        self._broadcast(f"[OK] SecurityAgent: {len(data_breaches or [])} breach(es) detected")

        return AgentResult(
            agent_name=self.agent_name,
            data_breaches=data_breaches or [],
        )

    @staticmethod
    def cross_validate(
        github_data: dict,
        social_profiles: dict,
        web_results: str,
        real_name: str,
        username: str = "",
    ) -> list[str]:
        """
        Algorithmically cross-validate data from different sources.
        Returns a list of detected inconsistency strings.
        """
        issues = []

        # --- 1. GitHub username vs searched username ---
        if github_data and username:
            gh_login = (github_data.get('login') or '').strip().lower()
            searched_username = username.strip().lower()
            if gh_login and searched_username and gh_login != searched_username and searched_username not in gh_login and gh_login not in searched_username:
                    issues.append(
                        f"GitHub login '@{github_data.get('login')}' doesn't match searched username '{username}'. Verify this is the correct account."
                    )

        # --- 2. GitHub location vs web results (word-level matching) ---
        if github_data:
            gh_location = (github_data.get('location') or '').strip()
            if gh_location and web_results and len(gh_location) > 2:
                location_words = set(_normalize_text(gh_location).split())
                web_normalized = _normalize_text(web_results)
                significant_words = {w for w in location_words if len(w) > 2}
                if significant_words and not any(w in web_normalized for w in significant_words):
                    issues.append(
                        f"GitHub states location as '{gh_location}' but none of its keywords appear in web search results."
                    )

        # --- 3. GitHub display name vs searched name (with Unicode normalization) ---
        if github_data:
            gh_name = (github_data.get('name') or '').strip()
            if gh_name and real_name:
                gh_words = set(_normalize_text(gh_name).split())
                search_words = set(_normalize_text(real_name).split())
                gh_significant = {w for w in gh_words if len(w) > 1}
                search_significant = {w for w in search_words if len(w) > 1}
                if gh_significant and search_significant and not gh_significant.intersection(search_significant):
                    issues.append(
                        f"GitHub profile name '{gh_name}' doesn't share any words with searched name '{real_name}'. Possible identity mismatch."
                    )

        # --- 4. No social media profiles but significant web presence ---
        found_platforms = [k for k, v in social_profiles.items() if v]
        if not found_platforms and web_results and len(web_results) > 500:
            issues.append(
                "No social media profiles found despite significant web results. The person may use different usernames across platforms."
            )

        # --- 5. GitHub bio profession vs web results profession ---
        if github_data:
            gh_bio = (github_data.get('bio') or '').strip().lower()
            if gh_bio and len(gh_bio) > 10 and web_results:
                web_lower = web_results.lower()
                profession_clusters = [
                    ({'developer', 'programmer', 'engineer', 'software', 'coding', 'github'},
                     {'doctor', 'physician', 'medical', 'hospital', 'clinical', 'surgeon'}),
                    ({'developer', 'programmer', 'engineer', 'software'},
                     {'lawyer', 'attorney', 'legal', 'law firm', 'court'}),
                    ({'student', 'öğrenci', 'university', 'üniversite', 'college'},
                     {'ceo', 'founder', 'director', 'chairman', 'president', 'managing'}),
                ]
                for cluster_a, cluster_b in profession_clusters:
                    bio_has_a = any(kw in gh_bio for kw in cluster_a)
                    web_has_b = any(kw in web_lower for kw in cluster_b)
                    bio_has_b = any(kw in gh_bio for kw in cluster_b)
                    web_has_a = any(kw in web_lower for kw in cluster_a)

                    if bio_has_a and web_has_b and not bio_has_b and not web_has_a:
                        bio_match = next(kw for kw in cluster_a if kw in gh_bio)
                        web_match = next(kw for kw in cluster_b if kw in web_lower)
                        issues.append(
                            f"GitHub bio mentions '{bio_match}' but web results reference '{web_match}'. Possible identity confusion with another person."
                        )
                        break

        # --- 6. GitHub exists but all other sources are empty ---
        if github_data and not found_platforms and (not web_results or len(web_results) < 100):
            issues.append(
                "Only GitHub data is available — no corroborating web or social media sources. Information reliability is limited."
            )

        return issues
