"""Read a profile page into structured data.

Four strategies, tried in order of how much they can go wrong:

1. **API / oEmbed JSON** — GitHub, Reddit, Bluesky, Spotify, Steam, Mastodon.
   Structured, no parsing risk.
2. **Embedded JSON** — TikTok's ``__UNIVERSAL_DATA_FOR_REHYDRATION__``, YouTube's
   ``ytInitialData``. Parsed with ``json.loads``; values are never regexed out.
3. **JSON-LD** — ``Person`` / ``ProfilePage`` / ``Organization`` objects.
4. **OpenGraph** — ``og:image``, ``og:title``, ``og:description``.

Nothing here fabricates a field. If a platform cannot supply an avatar (X, logged
out) the avatar is ``None`` and ``status_detail`` says why — the old pipeline
instead emitted an ``unavatar.io`` URL for platforms unavatar does not support,
producing guaranteed-404 images inlined as markdown.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.discovery.fetch.result import FetchResult
from app.discovery.fetch.selectors import (
    css_all_attr,
    dig,
    embedded_json,
    json_ld_of_type,
    meta_content,
    script_json,
)
from app.discovery.fetch.session import FetchSession
from app.discovery.identity import contacts as contacts_module
from app.discovery.platforms.existence import ExistenceResult, _dig_escaped
from app.discovery.platforms.registry import PlatformRegistry
from app.discovery.platforms.spec import PlatformSpec
from app.discovery.platforms.urlmatch import is_platform_chrome, match_profile_url
from app.discovery.types import EvidenceKind
from app.utils.logger import logger

# Instagram's og:description is localised, so the *words* differ by locale but the
# number order never does: followers, following, posts.
_IG_COUNTS = re.compile(r"([\d.,]+\s*[KMBkmb]?)\s+\S+,\s*([\d.,]+\s*[KMBkmb]?)\s+\S+,\s*([\d.,]+\s*[KMBkmb]?)")
_IG_HANDLE = re.compile(r"\(@([A-Za-z0-9._]{1,30})\)")
_COUNT_SUFFIX = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}


@dataclass(slots=True)
class ProfileData:
    """Everything we could read off one profile, with provenance."""

    platform: str
    username: str
    url: str
    display_name: str | None = None
    bio: str | None = None
    avatar_url: str | None = None
    followers: int | None = None
    following: int | None = None
    posts: int | None = None
    verified: bool | None = None
    location: str | None = None
    employer: str | None = None
    emails: list[str] = field(default_factory=list)
    """Addresses this profile page published — a ``mailto:`` or a bio line."""
    phones: list[str] = field(default_factory=list)
    """Numbers from a ``tel:`` href only.

    Never from the bio: it is one line of free text with no contact-word context
    to lean on, and that is exactly where a phone pattern eats follower counts,
    years and `1M`."""
    outbound_links: list[str] = field(default_factory=list)
    rel_me_links: list[str] = field(default_factory=list)
    """Links carrying ``rel="me"`` — an explicit "this is also me" claim.

    Kept apart from ``outbound_links`` because the assertion is different: an
    ordinary link says "related", ``rel="me"`` says "same person". Two profiles
    making that claim about each other is the IndieAuth handshake and the
    strongest keyless identity signal available without an account.
    """

    last_activity: datetime | None = None
    extractor: str = ""
    """Which strategy produced this, e.g. ``api:github`` or ``og``."""

    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not any((self.display_name, self.bio, self.avatar_url, self.followers, self.outbound_links))


def parse_count(value: Any) -> int | None:
    """Parse ``"1,234"``, ``"12.3K"``, ``"4.5M"`` or a plain int into an int."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip().replace(" ", " ").replace(" ", "")
    if not text:
        return None
    multiplier = 1
    if text[-1].lower() in _COUNT_SUFFIX:
        multiplier = _COUNT_SUFFIX[text[-1].lower()]
        text = text[:-1]
    # "1,234" is a thousands separator; "1.2K" is a decimal. With a multiplier the
    # dot is decimal, without one both separators are grouping.
    text = text.replace(",", "") if multiplier > 1 else text.replace(",", "").replace(".", "")
    try:
        return int(float(text) * multiplier)
    except ValueError:
        return None


class ProfileExtractor:
    """Turns an ExistenceResult into ProfileData. Never raises."""

    def __init__(self, fetch: FetchSession, registry: PlatformRegistry) -> None:
        self._fetch = fetch
        self._registry = registry

    async def extract(self, existence: ExistenceResult) -> ProfileData | None:
        """Read the profile behind ``existence``, or None if nothing is readable."""
        spec = self._registry.get(existence.platform)
        if spec is None or not existence.usable:
            return None
        try:
            api = await self._from_api(spec, existence)
            if api is not None and not api.is_empty:
                return api

            embed = await self._from_embed(spec, existence)
            if embed is not None and not embed.is_empty:
                return embed

            result = existence.fetch or await self._fetch.get(
                existence.url, tier=spec.fetch_tier, escalate=spec.escalate
            )
            if not result.ok:
                return api
            return self._from_page(spec, existence.username, existence.url, result) or api
        except Exception as exc:
            # Still a None, because a profile that will not parse is a missing
            # profile rather than a failed search. But the caller cannot tell this
            # None from the two "nothing readable" returns above, and outbound
            # links — the strongest keyless corroborator we collect — come out of
            # here, so a crash used to look exactly like an empty profile. Only
            # the exception type and the public profile URL are logged: the page
            # body and any API response may carry scraped personal data.
            logger.log_warning(
                f"Profile extraction failed for {existence.platform} at {existence.url}: {type(exc).__name__}: {exc}"
            )
            return None

    # -- strategy 1b: JSON embedded in an embed page --------------------------

    async def _from_embed(self, spec: PlatformSpec, existence: ExistenceResult) -> ProfileData | None:
        """Read the profile out of the embed page's payload. See `_EMBED_HANDLERS`.

        ``existence.fetch`` is reused when it is already that page — for TikTok the
        existence oracle *is* the embed URL, so the common path costs no request at
        all. It is checked by URL rather than assumed: reusing whatever the oracle
        happened to fetch is how the profile page came to be parsed with the embed
        page's selectors and vice versa.
        """
        handler = _EMBED_HANDLERS.get(spec.key)
        if handler is None:
            return None

        url = handler["url"].format(username=existence.username)
        result = existence.fetch
        if result is None or result.url != url:
            result = await self._fetch.get(url)
        if not result.ok:
            return None

        payload = script_json(result.page, handler["selector"])
        info = _dig_escaped(payload, handler["path"]) if payload is not None else None
        if not isinstance(info, dict):
            return None

        mapping: dict[str, str] = handler["fields"]
        data = ProfileData(
            platform=spec.key,
            username=existence.username,
            url=existence.url,
            extractor=f"embed:{spec.key}",
        )
        data.display_name = _as_text(dig(info, mapping.get("display_name", "")))
        data.bio = _as_text(dig(info, mapping.get("bio", "")))
        data.avatar_url = _as_text(dig(info, mapping.get("avatar_url", "")))
        data.followers = parse_count(dig(info, mapping.get("followers", "")))
        data.following = parse_count(dig(info, mapping.get("following", "")))
        verified = dig(info, mapping.get("verified", ""))
        if isinstance(verified, bool):
            data.verified = verified
        data.raw = {k: v for k, v in info.items() if not isinstance(v, dict | list)}
        return data

    # -- strategy 1: real APIs -----------------------------------------------

    async def _from_api(self, spec: PlatformSpec, existence: ExistenceResult) -> ProfileData | None:
        handler = _API_HANDLERS.get(spec.key)
        if handler is None:
            return None
        url = handler["url"].format(username=existence.username)
        _result, payload = await self._fetch.get_json(url)
        if not isinstance(payload, dict):
            return None
        data = ProfileData(
            platform=spec.key,
            username=existence.username,
            url=existence.url,
            extractor=f"api:{spec.key}",
        )
        mapping: dict[str, str] = handler["fields"]
        data.display_name = _as_text(dig(payload, mapping.get("display_name", "")))
        data.bio = _as_text(dig(payload, mapping.get("bio", "")))
        data.avatar_url = _as_text(dig(payload, mapping.get("avatar_url", "")))
        data.location = _as_text(dig(payload, mapping.get("location", "")))
        data.employer = _as_text(dig(payload, mapping.get("employer", "")))
        data.followers = parse_count(dig(payload, mapping.get("followers", "")))
        data.following = parse_count(dig(payload, mapping.get("following", "")))
        data.posts = parse_count(dig(payload, mapping.get("posts", "")))
        blog = _as_text(dig(payload, mapping.get("link", "")))
        if blog:
            data.outbound_links.append(blog)
        data.raw = {k: v for k, v in payload.items() if not isinstance(v, dict | list)} if payload else {}
        return data

    # -- strategies 2-4: the page --------------------------------------------

    def from_result(self, platform: str, username: str, url: str, result: FetchResult) -> ProfileData | None:
        """Parse a document we already hold, with no fetching of any kind.

        The browse tier's entry point. It captured the HTML itself, after the
        page had been scrolled and unblocked, so re-fetching would both cost a
        request and throw away the very state it worked to reach. Deliberately
        skips ``_from_api``: a platform is only ever browsed because the cheap
        routes were refused.
        """
        spec = self._registry.get(platform)
        if spec is None or not result.ok:
            return None
        try:
            return self._from_page(spec, username, url, result)
        except Exception as exc:
            logger.log_warning(f"Browse harvest could not parse {url}: {exc}", broadcast=False)
            return None

    def _from_page(self, spec: PlatformSpec, username: str, url: str, result: FetchResult) -> ProfileData | None:
        page = result.page
        if page is None:
            return None

        data = ProfileData(platform=spec.key, username=username, url=url, extractor="og")

        # 2. embedded JSON (richest when present)
        payload = None
        if spec.embedded_json_selector:
            payload = script_json(page, spec.embedded_json_selector)
        if payload is None and spec.embedded_json_pattern:
            payload = embedded_json(result.html, spec.embedded_json_pattern)
        if payload is not None:
            if spec.key == "tiktok":
                self._apply_tiktok(data, payload, spec)
            elif spec.key == "youtube":
                self._apply_youtube(data, payload)

        # 3. JSON-LD
        ld = json_ld_of_type(page, "Person", "ProfilePage", "Organization", "MusicGroup")
        if ld:
            data.display_name = data.display_name or _as_text(ld.get("name"))
            data.bio = data.bio or _as_text(ld.get("description"))
            data.avatar_url = data.avatar_url or _image_from_ld(ld.get("image"))
            works_for = ld.get("worksFor")
            if isinstance(works_for, dict):
                data.employer = data.employer or _as_text(works_for.get("name"))
            address = ld.get("address")
            if isinstance(address, dict):
                data.location = data.location or _as_text(
                    address.get("addressLocality") or address.get("addressRegion")
                )
            if data.extractor == "og":
                data.extractor = "json_ld"

        # 4. OpenGraph fallback
        data.display_name = data.display_name or _strip_platform_suffix(meta_content(page, "og:title", "twitter:title"))
        description = meta_content(page, "og:description", "twitter:description", "description")
        if spec.key == "instagram" and description:
            self._apply_instagram_description(data, description)
        elif description and not data.bio:
            data.bio = description
        if spec.supports_avatar and not data.avatar_url:
            data.avatar_url = meta_content(page, "og:image", "twitter:image")

        for href in css_all_attr(page, "a", "href")[:200]:
            self._maybe_outbound(data, href, spec)
        for href in css_all_attr(page, 'a[rel~="me"]', "href")[:25]:
            self._maybe_rel_me(data, href, spec)

        return None if data.is_empty else data

    @staticmethod
    def _apply_instagram_description(data: ProfileData, description: str) -> None:
        """Parse counts positionally — the surrounding words are localised."""
        counts = _IG_COUNTS.search(description)
        if counts:
            data.followers = parse_count(counts.group(1))
            data.following = parse_count(counts.group(2))
            data.posts = parse_count(counts.group(3))
        handle = _IG_HANDLE.search(description)
        if handle:
            data.raw["og_handle"] = handle.group(1)
        # The bio is whatever follows the counts sentence.
        tail = description.split(" - ", 1)[-1] if " - " in description else description
        cleaned = re.sub(r'^"|"$', "", tail).strip()
        if cleaned and cleaned != description:
            data.bio = cleaned
        data.extractor = "og:instagram"

    @staticmethod
    def _apply_tiktok(data: ProfileData, payload: Any, spec: PlatformSpec) -> None:
        base = _dig_escaped(payload, spec.embedded_json_path or "") if spec.embedded_json_path else None
        if not isinstance(base, dict):
            return
        user = dig(base, "user") or {}
        stats = dig(base, "stats") or {}
        data.display_name = _as_text(user.get("nickname")) or data.display_name
        data.bio = _as_text(user.get("signature")) or data.bio
        data.avatar_url = _as_text(user.get("avatarLarger") or user.get("avatarMedium")) or data.avatar_url
        data.verified = bool(user.get("verified")) if "verified" in user else data.verified
        data.followers = parse_count(stats.get("followerCount")) or data.followers
        data.following = parse_count(stats.get("followingCount")) or data.following
        data.posts = parse_count(stats.get("videoCount")) or data.posts
        link = _as_text(dig(user, "bioLink.link"))
        if link:
            data.outbound_links.append(link)
        data.extractor = "embedded_json:tiktok"

    @staticmethod
    def _apply_youtube(data: ProfileData, payload: Any) -> None:
        meta = dig(payload, "metadata.channelMetadataRenderer") or {}
        data.display_name = _as_text(meta.get("title")) or data.display_name
        data.bio = _as_text(meta.get("description")) or data.bio
        avatar = dig(meta, "avatar.thumbnails.-1.url") or dig(meta, "avatar.thumbnails.0.url")
        data.avatar_url = _as_text(avatar) or data.avatar_url
        data.location = _as_text(meta.get("country")) or data.location
        subs = dig(payload, "header.c4TabbedHeaderRenderer.subscriberCountText.simpleText")
        data.followers = parse_count(_first_number(subs)) or data.followers
        for link in dig(meta, "ownerUrls") or []:
            if isinstance(link, str):
                data.outbound_links.append(link)
        data.extractor = "embedded_json:youtube"

    @staticmethod
    def _maybe_rel_me(data: ProfileData, href: str, spec: PlatformSpec) -> None:
        """Record an explicit identity claim, canonicalised where we recognise it."""
        if not href or not href.startswith("http") or len(data.rel_me_links) >= 25:
            return
        # A `rel="me"` on site furniture is the theme's doing, not a claim.
        if is_platform_chrome(href):
            return
        match = match_profile_url(href)
        if match is not None:
            if match.platform == spec.key:
                return  # a profile pointing at itself claims nothing
            href = match.canonical_url
        if href not in data.rel_me_links:
            data.rel_me_links.append(href)
        if href not in data.outbound_links and len(data.outbound_links) < 25:
            data.outbound_links.append(href)

    @staticmethod
    def _maybe_outbound(data: ProfileData, href: str, spec: PlatformSpec) -> None:
        """Collect links that point somewhere *else* — same-site links are chrome.

        Outbound links are the single strongest keyless corroborator: a profile that
        links to another confirmed profile ties the two together.
        """
        # A `mailto:`/`tel:` is routed rather than dropped — but it must never
        # become an `outbound_link`, which means "another page about this
        # person" and is scored as corroboration.
        if href.startswith(("mailto:", "tel:")):
            for hit in contacts_module.from_hrefs([href], source_url=data.url):
                bucket = data.emails if hit.kind is EvidenceKind.EMAIL else data.phones
                if hit.value not in bucket and len(bucket) < 5:
                    bucket.append(hit.value)
            return
        if not href or href.startswith(("#", "/", "javascript:")):
            return
        if len(data.outbound_links) >= 25:
            return
        # The platform's own footer sits on every profile it serves, so it says
        # nothing about *this* person. Dropping it here rather than at render
        # time also keeps it out of the corroboration score.
        if is_platform_chrome(href):
            return
        match = match_profile_url(href)
        if match is not None:
            if match.platform != spec.key and match.canonical_url not in data.outbound_links:
                data.outbound_links.append(match.canonical_url)
            return
        # Only keep plausible personal/company sites, not CDN or tracker noise.
        is_noise = any(n in href for n in ("googleapis", "gstatic", "cdn.", "doubleclick", "facebook.com/tr"))
        if (
            href.startswith("http")
            and spec.host
            and spec.host not in href
            and href not in data.outbound_links
            and not is_noise
        ):
            data.outbound_links.append(href)


# Platforms whose profile page is unreadable, but which publish the same profile
# as JSON embedded in an *embed* page. Values are dotted paths into that object.
#
# TikTok, measured live 2026-08-29: `tiktok.com/@handle` answers HTTP 200 with a
# 1.8 KB shell — one `<script id="slardar-config">`, no og:image, no
# `__UNIVERSAL_DATA_FOR_REHYDRATION__` — for the stealth browser as well as for a
# plain client, so `_from_page` had nothing to read and every TikTok account came
# back with no name, no bio and no picture. `tiktok.com/embed/@handle` serves
# 290 KB carrying the whole `userInfo`, and the existence oracle already fetches
# it, so this costs nothing extra when that response is reused.
_EMBED_HANDLERS: dict[str, dict[str, Any]] = {
    "tiktok": {
        "url": "https://www.tiktok.com/embed/@{username}",
        "selector": "script#__FRONTITY_CONNECT_STATE__",
        # The payload keys the profile by request path, hence the wildcard — the
        # same reason `oracle_exists_path` uses one.
        "path": "source.data.*.userInfo",
        # Flat, not nested under `user`: the keys sit directly on `userInfo`.
        "fields": {
            "display_name": "nickname",
            "bio": "signature",
            "avatar_url": "avatarThumbUrl",
            "followers": "followerCount",
            "following": "followingCount",
            "verified": "verified",
        },
    },
}

# Real APIs, keyless. Values are dotted paths into the JSON response.
_API_HANDLERS: dict[str, dict[str, Any]] = {
    "github": {
        "url": "https://api.github.com/users/{username}",
        "fields": {
            "display_name": "name",
            "bio": "bio",
            "avatar_url": "avatar_url",
            "location": "location",
            "employer": "company",
            "followers": "followers",
            "following": "following",
            "posts": "public_repos",
            "link": "blog",
        },
    },
    "reddit": {
        "url": "https://www.reddit.com/user/{username}/about.json",
        "fields": {
            "display_name": "data.subreddit.title",
            "bio": "data.subreddit.public_description",
            "avatar_url": "data.icon_img",
            "followers": "data.subreddit.subscribers",
            "posts": "data.link_karma",
        },
    },
    "bluesky": {
        "url": "https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile?actor={username}",
        "fields": {
            "display_name": "displayName",
            "bio": "description",
            "avatar_url": "avatar",
            "followers": "followersCount",
            "following": "followsCount",
            "posts": "postsCount",
        },
    },
    "mastodon": {
        "url": "https://mastodon.social/api/v1/accounts/lookup?acct={username}",
        "fields": {
            "display_name": "display_name",
            "bio": "note",
            "avatar_url": "avatar",
            "followers": "followers_count",
            "following": "following_count",
            "posts": "statuses_count",
        },
    },
    "spotify": {
        "url": "https://open.spotify.com/oembed?url=https://open.spotify.com/user/{username}",
        "fields": {"display_name": "title", "avatar_url": "thumbnail_url"},
    },
    "x": {
        # Existence only. The oembed endpoint returns `url` and an embed `html`
        # blob; `title` is usually empty and `author_name` is gone. There is
        # deliberately no avatar mapping — logged-out X serves no usable image, and
        # inventing one is how the old pipeline produced broken <img> tags.
        "url": "https://publish.twitter.com/oembed?url=https://twitter.com/{username}",
        "fields": {"display_name": "title"},
    },
}


def _as_text(value: Any) -> str | None:
    if value is None or isinstance(value, dict | list):
        return None
    text = str(value).strip()
    return text or None


def _first_number(value: Any) -> str | None:
    if value is None:
        return None
    match = re.search(r"[\d.,]+\s*[KMBkmb]?", str(value))
    return match.group(0) if match else None


def _image_from_ld(value: Any) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        return _as_text(value.get("url") or value.get("contentUrl"))
    if isinstance(value, list) and value:
        return _image_from_ld(value[0])
    return None


def _strip_platform_suffix(title: str | None) -> str | None:
    """``"Jane Doe (@jdoe) • Instagram photos"`` -> ``"Jane Doe"``."""
    if not title:
        return None
    cleaned = re.split(r"\s+[•|·]\s+|\s+\|\s+", title)[0]
    cleaned = re.sub(r"\s*\(@[A-Za-z0-9._]+\)\s*$", "", cleaned).strip()
    return cleaned or None
