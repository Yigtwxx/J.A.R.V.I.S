"""Step 5 — collect avatar images for the report and for face matching.

Images are only ever *sourced*, never synthesised. The previous implementation
built ``https://unavatar.io/{platform}/{username}?fallback=false`` for linkedin,
snapchat, tumblr and spotify — providers unavatar does not serve — so every one
of those URLs was a guaranteed 404. The old response builder inlined them into
the AI answer as markdown ``![](url)``, where they rendered as broken images
inside the biography.

Three real sources replace it:

* the avatars the discovery pipeline already downloaded into ``data/avatars``
  (see ``app/discovery/media/store.py``), reached through the adapters in
  ``app/services/discovery_integration.py``. They are content-addressed local
  files, so they neither expire nor 404 the way a signed CDN link does;
* the absolute ``http(s)`` avatar URLs the legacy path genuinely holds — the
  Wikipedia image and the GitHub API's ``avatar_url``;
* an ``avatar_url`` scraped off a profile page that was actually **found**.

A platform that was not reached contributes nothing. That is the point: an
absent picture is honest, a fabricated one is not.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.services.discovery_integration import face_match_inputs

from .base import PipelineStep
from .context import PipelineContext

PLACEHOLDER_BIO = "[SEARCH]"
"""Marker the deleted scraper injected for every empty platform. Still filtered
here so a stale cached payload can never resurrect a search-page URL."""


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    """Read a field from a pydantic model, a dataclass or a plain dict alike."""
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _is_http_url(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(("http://", "https://"))


def _found_avatars(social_profiles: Any) -> list[tuple[str, str]]:
    """``(label, absolute avatar URL)`` for accounts that were actually found.

    Accepts both the typed ``list[SocialProfile]`` shape and the legacy
    ``{platform: [item, ...]}`` dict. Entries that were not reached, and the
    ``[SEARCH]`` placeholders, are dropped — and no URL is ever *constructed*
    from a username.
    """
    out: list[tuple[str, str]] = []

    def consider(platform: str, item: Any) -> None:
        if _attr(item, "bio") == PLACEHOLDER_BIO:
            return
        status = _attr(item, "status")
        if status is not None and str(status) != "found":
            return
        url = _attr(item, "avatar_url")
        if _is_http_url(url):
            out.append((str(platform or "profile").capitalize(), url))

    if isinstance(social_profiles, Mapping):
        for platform, items in social_profiles.items():
            for item in items or []:
                consider(str(platform), item)
    elif isinstance(social_profiles, Sequence) and not isinstance(social_profiles, str):
        for item in social_profiles:
            consider(str(_attr(item, "platform") or ""), item)
    return out


def _dedupe(values: Sequence[str]) -> list[str]:
    unique: list[str] = []
    for value in values:
        if value and value not in unique:
            unique.append(value)
    return unique


class ImageCollectorStep(PipelineStep):
    """Builds the report's picture list and the face-matching input pairs."""

    def __init__(self, avatar_root: Path | None = None) -> None:
        self._avatar_root = avatar_root

    @property
    def name(self) -> str:
        return "image_collector"

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        social_profiles = _attr(ctx.orch_result, "social_profiles") or {}
        wiki_image = ctx.search_results[0] if ctx.search_results else None
        ctx.images = self.collect_images(social_profiles, ctx.github_data, wiki_image, ctx.real_name)
        ctx.face_images = self.collect_face_images(social_profiles, ctx.github_data, wiki_image)
        return ctx

    def collect_images(
        self,
        social_profiles: Any,
        github_data: dict | None,
        wiki_image: str | None,
        real_name: str = "",  # noqa: ARG002 - part of the stable caller signature
        profile_pictures: Sequence[Any] | None = None,
    ) -> list[str]:
        """Deduplicated picture URLs for the report, most trusted first.

        Discovery pictures come first because they are our own stored files;
        everything after them is a third-party URL that may rot.
        """
        images: list[str] = []
        for picture in profile_pictures or []:
            url = _attr(picture, "url")
            if isinstance(url, str) and url:
                images.append(url)
        if _is_http_url(wiki_image):
            images.append(str(wiki_image))
        if github_data and _is_http_url(github_data.get("avatar_url")):
            images.append(str(github_data["avatar_url"]))
        images.extend(url for _, url in _found_avatars(social_profiles))
        return _dedupe(images)

    def collect_face_images(
        self,
        social_profiles: Any,
        github_data: dict | None,
        wiki_image: str | None,
        profile_pictures: Sequence[Any] | None = None,
    ) -> list[tuple[str, str]]:
        """``(label, image)`` pairs for the face-match feature.

        Discovery avatars are handed over as **local file paths** resolved by
        ``discovery_integration.face_match_inputs``, which applies the avatar
        store's allow-list and containment check. ``FaceMatchingService`` uses an
        existing local file as-is and never deletes it, so the content-addressed
        store survives the comparison; everything else is downloaded to a temp
        file as before.
        """
        pairs: list[tuple[str, str]] = []
        if profile_pictures:
            pairs.extend(face_match_inputs(list(profile_pictures), avatar_root=self._avatar_root))
        if _is_http_url(wiki_image):
            pairs.append(("Wikipedia", str(wiki_image)))
        if github_data and _is_http_url(github_data.get("avatar_url")):
            pairs.append(("GitHub", str(github_data["avatar_url"])))
        pairs.extend(_found_avatars(social_profiles))

        seen: set[str] = set()
        unique: list[tuple[str, str]] = []
        for label, image in pairs:
            if image in seen:
                continue
            seen.add(image)
            unique.append((label, image))
        return unique
