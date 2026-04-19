"""Step 5 — build deduplicated image list and labeled face-image pairs."""
from __future__ import annotations

from typing import Any

from .base import PipelineStep
from .context import PipelineContext


def _is_real_profile(items: list, platform_domain: str) -> bool:
    if not items:
        return False
    first = items[0]
    if first.get('bio') == '[SEARCH]':
        return False
    return platform_domain in first.get('url', '').lower()


class ImageCollectorStep(PipelineStep):
    def __init__(self, scraper_service: Any) -> None:
        self._scraper = scraper_service

    @property
    def name(self) -> str:
        return "image_collector"

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        social_profiles = ctx.orch_result.social_profiles
        github_data = ctx.github_data
        wiki_image = ctx.search_results[0] if ctx.search_results else None  # type: ignore[index]
        real_name = ctx.real_name

        ctx.images = self._collect_images(social_profiles, github_data, wiki_image, real_name)
        ctx.face_images = self._collect_face_images(social_profiles, github_data, wiki_image)
        return ctx

    def _collect_images(
        self,
        social_profiles: dict,
        github_data: dict | None,
        wiki_image: str | None,
        real_name: str,
    ) -> list[str]:
        images: list[str] = []
        if wiki_image:
            images.append(wiki_image)
        if github_data and github_data.get('avatar_url'):
            images.append(github_data['avatar_url'])

        instagram_items = social_profiles.get('instagram', [])
        if _is_real_profile(instagram_items, 'instagram.com'):
            ig_url = instagram_items[0]['url'].split(',')[0].strip()
            ig_username = ig_url.rstrip('/').split('/')[-1]
            if ig_username and len(ig_username) >= 2:
                direct_ig = self._scraper.fetch_avatar_from_url(ig_url)
                images.append(
                    direct_ig if direct_ig
                    else f"https://unavatar.io/instagram/{ig_username}?fallback=false"
                )

        twitter_items = social_profiles.get('twitter', [])
        if _is_real_profile(twitter_items, 'x.com') or _is_real_profile(twitter_items, 'twitter.com'):
            tw_url = twitter_items[0]['url'].split(',')[0].strip()
            tw_username = tw_url.rstrip('/').split('/')[-1].lstrip('@')
            if tw_username and len(tw_username) >= 2:
                images.append(f"https://unavatar.io/x/{tw_username}?fallback=false")

        for platform, domain in {
            'linkedin': 'linkedin.com', 'spotify': 'spotify.com', 'tiktok': 'tiktok.com',
            'snapchat': 'snapchat.com', 'tumblr': 'tumblr.com',
        }.items():
            items = social_profiles.get(platform, [])
            if _is_real_profile(items, domain):
                profile_url = items[0]['url'].split(',')[0].strip()
                social_username = profile_url.rstrip('/').split('/')[-1]
                if social_username and len(social_username) >= 2:
                    images.append(f"https://unavatar.io/{platform}/{social_username}?fallback=false")

        unique: list[str] = []
        for img in images:
            if img not in unique:
                unique.append(img)
        return unique

    def _collect_face_images(
        self,
        social_profiles: dict,
        github_data: dict | None,
        wiki_image: str | None,
    ) -> list[tuple[str, str]]:
        face_images: list[tuple[str, str]] = []
        if wiki_image:
            face_images.append(("Wikipedia", wiki_image))
        if github_data and github_data.get('avatar_url'):
            face_images.append(("GitHub", github_data['avatar_url']))

        instagram_items = social_profiles.get('instagram', [])
        if _is_real_profile(instagram_items, 'instagram.com'):
            ig_url = instagram_items[0]['url'].split(',')[0].strip()
            ig_username = ig_url.rstrip('/').split('/')[-1]
            if ig_username and len(ig_username) >= 2:
                direct_ig = self._scraper.fetch_avatar_from_url(ig_url)
                face_images.append((
                    "Instagram",
                    direct_ig if direct_ig
                    else f"https://unavatar.io/instagram/{ig_username}?fallback=false",
                ))

        twitter_items = social_profiles.get('twitter', [])
        if _is_real_profile(twitter_items, 'x.com') or _is_real_profile(twitter_items, 'twitter.com'):
            tw_url = twitter_items[0]['url'].split(',')[0].strip()
            tw_username = tw_url.rstrip('/').split('/')[-1].lstrip('@')
            if tw_username and len(tw_username) >= 2:
                face_images.append(("Twitter", f"https://unavatar.io/x/{tw_username}?fallback=false"))

        for platform, domain in {
            'linkedin': 'linkedin.com', 'spotify': 'spotify.com', 'tiktok': 'tiktok.com',
            'snapchat': 'snapchat.com', 'tumblr': 'tumblr.com',
        }.items():
            items = social_profiles.get(platform, [])
            if _is_real_profile(items, domain):
                first_url = items[0]['url'].split(',')[0].strip()
                social_username = first_url.rstrip('/').split('/')[-1]
                if social_username and len(social_username) >= 2:
                    face_images.append((
                        platform.capitalize(),
                        f"https://unavatar.io/{platform}/{social_username}?fallback=false",
                    ))

        return face_images
