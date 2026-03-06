"""
Digital Impact Score (Dijital Etki Skoru) Service

Calculates a weighted, deterministic social media influence score
from real data signals across 5 dimensions:

1. Platform Presence  (20)  — How many platforms the person exists on
2. Follower Impact    (30)  — GitHub followers on a logarithmic scale
3. Activity Intensity (20)  — Repo count + recency of last activity
4. Web Visibility     (15)  — Number of web search results found
5. Digital Diversity  (15)  — Bio completeness, blog, cross-platform spread
"""

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from app.utils.logger import logger


class SocialScoreService:
    """Algorithmic engine for computing the Digital Impact Score."""

    # Maximum possible platforms we track
    TRACKED_PLATFORMS = ["github", "instagram", "twitter", "linkedin", "spotify", "tiktok", "snapchat", "tumblr", "tinder", "bumble"]

    # Dimension weights (must sum to 100)
    W_PLATFORM_PRESENCE = 20
    W_FOLLOWER_IMPACT = 30
    W_ACTIVITY_INTENSITY = 20
    W_WEB_VISIBILITY = 15
    W_DIGITAL_DIVERSITY = 15

    def calculate_score(
        self,
        github_data: Optional[Dict[str, Any]],
        social_profiles: Dict[str, list],
        raw_sources: List[Dict[str, str]],
        web_results: str,
    ) -> Dict[str, Any]:
        """
        Compute the Digital Impact Score from all gathered data.

        Returns a dict with:
          - total_score (int 0-100)
          - breakdown (dict of dimension names → normalized 0.0-1.0 floats)
          - explanation (str — human-readable summary)
        """
        logger.log_thought("Running Digital Impact Score algorithm across 5 dimensions...")

        # --- 1. Platform Presence (0.0 – 1.0) ---
        platform_presence = self._calc_platform_presence(github_data, social_profiles)

        # --- 2. Follower Impact (0.0 – 1.0) ---
        follower_impact = self._calc_follower_impact(github_data)

        # --- 3. Activity Intensity (0.0 – 1.0) ---
        activity_intensity = self._calc_activity_intensity(github_data)

        # --- 4. Web Visibility (0.0 – 1.0) ---
        web_visibility = self._calc_web_visibility(raw_sources, web_results)

        # --- 5. Digital Diversity (0.0 – 1.0) ---
        digital_diversity = self._calc_digital_diversity(github_data, social_profiles)

        # Weighted total
        raw_total = (
            platform_presence * self.W_PLATFORM_PRESENCE
            + follower_impact * self.W_FOLLOWER_IMPACT
            + activity_intensity * self.W_ACTIVITY_INTENSITY
            + web_visibility * self.W_WEB_VISIBILITY
            + digital_diversity * self.W_DIGITAL_DIVERSITY
        )
        total_score = max(0, min(100, round(raw_total)))

        breakdown = {
            "platform_presence": round(platform_presence, 3),
            "follower_impact": round(follower_impact, 3),
            "activity_intensity": round(activity_intensity, 3),
            "web_visibility": round(web_visibility, 3),
            "digital_diversity": round(digital_diversity, 3),
        }

        explanation = self._generate_explanation(total_score, breakdown, github_data, social_profiles)

        logger.log_success(f"Digital Impact Score computed: {total_score}/100")
        return {
            "total_score": total_score,
            "breakdown": breakdown,
            "explanation": explanation,
        }

    # ─── Dimension Calculators ───────────────────────────────────────────

    def _calc_platform_presence(
        self,
        github_data: Optional[Dict],
        social_profiles: Dict[str, list],
    ) -> float:
        """Ratio of platforms where a profile was actually found."""
        found = 0
        total = len(self.TRACKED_PLATFORMS)

        if github_data:
            found += 1

        for platform in self.TRACKED_PLATFORMS:
            if platform == "github":
                continue  # Already counted above
            if social_profiles.get(platform):
                found += 1

        return found / total

    def _calc_follower_impact(self, github_data: Optional[Dict]) -> float:
        """
        Logarithmic follower scale.
        0 followers  → 0.0
        10 followers → ~0.33
        100          → ~0.67
        1000+        → 1.0
        """
        if not github_data:
            return 0.0

        followers = github_data.get("followers", 0) or 0
        if followers <= 0:
            return 0.0

        # log10(1001) ≈ 3.0, so we divide by 3 to normalize to 0-1
        score = math.log10(followers + 1) / 3.0
        return min(1.0, score)

    def _calc_activity_intensity(self, github_data: Optional[Dict]) -> float:
        """
        Combines repo count (log scale) and recency of last activity.
        50/50 split within this dimension.
        """
        if not github_data:
            return 0.0

        # Sub-dimension A: Repo count (log scale)
        repos = github_data.get("public_repos", 0) or 0
        if repos > 0:
            # log10(51) ≈ 1.7 → normalize so 50+ repos = 1.0
            repo_score = min(1.0, math.log10(repos + 1) / 1.7)
        else:
            repo_score = 0.0

        # Sub-dimension B: Recency of last activity
        last_active = github_data.get("last_active")
        recency_score = 0.0
        if last_active:
            try:
                if isinstance(last_active, str):
                    last_dt = datetime.fromisoformat(last_active.replace("Z", "+00:00"))
                else:
                    last_dt = last_active

                now = datetime.now(timezone.utc)
                days_ago = (now - last_dt).days

                if days_ago <= 7:
                    recency_score = 1.0
                elif days_ago <= 30:
                    recency_score = 0.8
                elif days_ago <= 90:
                    recency_score = 0.6
                elif days_ago <= 180:
                    recency_score = 0.4
                elif days_ago <= 365:
                    recency_score = 0.2
                else:
                    recency_score = 0.05
            except (ValueError, TypeError):
                recency_score = 0.0

        return (repo_score * 0.5) + (recency_score * 0.5)

    def _calc_web_visibility(
        self,
        raw_sources: List[Dict[str, str]],
        web_results: str,
    ) -> float:
        """
        Based on the number of verified search results found.
        15+ results = 1.0, linear scale below that.
        Also gives a small bonus for deep content availability.
        """
        num_results = len(raw_sources) if raw_sources else 0

        # Primary: result count ratio
        result_score = min(1.0, num_results / 15.0)

        # Secondary bonus: deep content richness (up to 0.15 extra, capped at 1.0)
        content_len = len(web_results) if web_results else 0
        # If we have >4000 chars of deep context, that's very rich
        content_bonus = min(0.15, (content_len / 4000.0) * 0.15)

        return min(1.0, result_score + content_bonus)

    def _calc_digital_diversity(
        self,
        github_data: Optional[Dict],
        social_profiles: Dict[str, list],
    ) -> float:
        """
        Rewards richness and variety of digital identity.
        - GitHub bio existence (+0.25)
        - GitHub blog/website (+0.20)
        - Social media bios found (+0.25)
        - Platform type diversity: professional + personal + creative (+0.30)
        """
        score = 0.0

        # GitHub bio & blog
        if github_data:
            if github_data.get("bio"):
                score += 0.25
            if github_data.get("blog"):
                score += 0.20

        # Social media bios — check if any scraped profile has a bio/snippet
        has_social_bio = False
        for platform, items in social_profiles.items():
            for item in items:
                if item.get("bio") and len(item["bio"].strip()) > 10:
                    has_social_bio = True
                    break
            if has_social_bio:
                break

        if has_social_bio:
            score += 0.25

        # Platform type diversity bonus
        # Professional: LinkedIn, GitHub
        # Personal:     Instagram, Twitter, TikTok
        # Creative:     Spotify
        has_professional = bool(github_data) or bool(social_profiles.get("linkedin"))
        has_personal = any(social_profiles.get(p) for p in ["instagram", "twitter", "tiktok", "snapchat", "tinder", "bumble"])
        has_creative = bool(social_profiles.get("spotify")) or bool(social_profiles.get("tumblr"))

        diversity_types = sum([has_professional, has_personal, has_creative])
        # 1 type = 0.10, 2 types = 0.20, 3 types = 0.30
        score += diversity_types * 0.10

        return min(1.0, score)

    # ─── Explanation Generator ───────────────────────────────────────────

    def _generate_explanation(
        self,
        total_score: int,
        breakdown: Dict[str, float],
        github_data: Optional[Dict],
        social_profiles: Dict[str, list],
    ) -> str:
        """Generate a concise human-readable summary of the score."""
        parts = []

        # Overall tier
        if total_score >= 80:
            parts.append("Exceptional digital presence with strong cross-platform influence.")
        elif total_score >= 60:
            parts.append("Solid digital footprint with notable online activity.")
        elif total_score >= 40:
            parts.append("Moderate digital presence across several platforms.")
        elif total_score >= 20:
            parts.append("Limited digital footprint detected.")
        else:
            parts.append("Minimal digital presence found.")

        # Highlight strongest dimension
        best_dim = max(breakdown, key=breakdown.get)  # type: ignore[arg-type]
        dim_labels = {
            "platform_presence": "platform coverage",
            "follower_impact": "follower influence",
            "activity_intensity": "activity level",
            "web_visibility": "web visibility",
            "digital_diversity": "digital diversity",
        }
        parts.append(f"Strongest signal: {dim_labels.get(best_dim, best_dim)} ({breakdown[best_dim]:.0%}).")

        # Platform count
        found_platforms = []
        if github_data:
            found_platforms.append("GitHub")
        for p in ["instagram", "twitter", "linkedin", "spotify", "tiktok", "snapchat", "tumblr", "tinder", "bumble"]:
            if social_profiles.get(p):
                found_platforms.append(p.capitalize())

        if found_platforms:
            parts.append(f"Active on: {', '.join(found_platforms)}.")

        return " ".join(parts)
