"""What is left of the legacy scraping layer after `app/discovery/` replaced it.

Discovery (search engines, username permutation, existence checking, profile
extraction, avatar download) now lives under `app/discovery/`. Everything that
used to do it here was deleted rather than kept "just in case", because several
pieces were not merely redundant but actively wrong:

* `_is_url_active` treated HTTP 403 and 429 as "the profile exists". Those codes
  mean we were refused, not that an account is there — it manufactured false
  positives on exactly the platforms that block bots hardest.
* `_platform_search_urls` injected a `{"url": <search page>, "bio": "[SEARCH]"}`
  entry for every platform that returned nothing, so `social_profiles` could
  never be empty. It inflated the counts and fed search-page URLs to the LLM,
  which then described the search page as if it were an account.
* A single `requests.Session` was mutated by `_rotate_user_agent` while six to
  eight worker threads read from it — a genuine data race. It is gone; nothing
  here performs I/O any more.

Two capabilities are still used elsewhere and stayed: phone-number extraction
from deep-scrape text, and rendering the found accounts into the AI briefing.
Username permutation moved verbatim to `app/discovery/identity/usernames.py`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from app.schemas.discovery import SocialProfile
from app.utils.logger import logger

PLACEHOLDER_BIO = "[SEARCH]"
"""The marker the deleted search-URL injector used. Filtered on the way in so a
stale cached payload can never put a search page back in front of the model."""

_MENTION_PLATFORMS = ("tinder", "bumble", "discord")

_PHONE_PATTERNS = (
    re.compile(r"\+?\d{1,3}[\s.-]?\(?\d{2,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{2,4}"),  # international
    re.compile(r"\(\d{3}\)[\s.-]?\d{3}[\s.-]?\d{4}"),  # US (555) 123-4567
    re.compile(r"\b0\d{3}[\s.-]?\d{3}[\s.-]?\d{2}[\s.-]?\d{2}\b"),  # TR 0555 123 45 67
)

_CONTACT_KEYWORDS = (
    "phone",
    "tel",
    "call",
    "contact",
    "mobile",
    "cell",
    "telefon",
    "iletişim",
    "numara",
    "gsm",
    "cep",
)


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    """Read a field from a pydantic model, a dataclass or a plain dict alike."""
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _row_to_profile(platform: str, item: Any) -> SocialProfile | None:
    """Normalise one legacy ``{"url": ..., "bio": ...}`` row into a `SocialProfile`.

    Returns None for a `[SEARCH]` placeholder or a row with no URL. The legacy
    shape carries no status, so a row that survives is treated as ``found`` —
    which is exactly what it meant before statuses existed.
    """
    if isinstance(item, SocialProfile):
        return item
    url = _attr(item, "url")
    if not url or _attr(item, "bio") == PLACEHOLDER_BIO:
        return None
    return SocialProfile(
        platform=platform,
        url=str(url),
        username=_attr(item, "username"),
        bio=_attr(item, "bio") or None,
        status="found",
    )


def to_social_profiles(source: Any) -> list[SocialProfile]:
    """Accept either shape — ``list[SocialProfile]`` or ``{platform: [row, ...]}``
    — and return only the accounts we actually found.

    Anything that is not ``found`` is dropped here rather than at the call site:
    handing the model a `blocked` or `not_found` row as if it were an account is
    how the old pipeline got it to write biographies about search pages.
    """
    out: list[SocialProfile] = []
    if isinstance(source, Mapping):
        for platform, items in source.items():
            for item in items or []:
                profile = _row_to_profile(str(platform), item)
                if profile is not None:
                    out.append(profile)
    elif isinstance(source, Sequence) and not isinstance(source, str):
        for item in source:
            profile = _row_to_profile(str(_attr(item, "platform") or ""), item)
            if profile is not None:
                out.append(profile)
    return [p for p in out if p.status == "found" and p.url]


class ScraperService:
    """Text helpers over already-collected data. Performs no network I/O."""

    def extract_phone_numbers(self, name: str, deep_context: str) -> list[str]:
        """Pull phone numbers out of deep-scrape text.

        Supports international formats: +90 555 123 4567, (555) 123-4567, etc.
        Only lines that mention part of the target's name or a contact keyword
        are considered, which keeps unrelated numbers on a shared page out.
        """
        if not deep_context:
            return []

        found: set[str] = set()
        name_parts = [w for w in name.lower().split() if len(w) > 2]

        for line in deep_context.split("\n"):
            line_lower = line.lower()
            has_name_context = any(part in line_lower for part in name_parts)
            has_contact_keyword = any(kw in line_lower for kw in _CONTACT_KEYWORDS)
            if not (has_name_context or has_contact_keyword):
                continue
            for pattern in _PHONE_PATTERNS:
                for match in pattern.findall(line):
                    digits_only = re.sub(r"\D", "", match)
                    # 7-15 digits, and not a bare year masquerading as a number
                    if 7 <= len(digits_only) <= 15 and not (len(digits_only) == 4 and digits_only.startswith("20")):
                        found.add(match.strip())

        result = list(found)[:5]  # cap to 5 numbers
        if result:
            logger.log_success(f"Phone numbers extracted: {len(result)} found")
        return result

    def format_social_profiles(
        self,
        profiles: Sequence[SocialProfile] | Mapping[str, list[dict[str, Any]]],
        classification: dict | None = None,
    ) -> str:
        """Render the found accounts as text for the AI briefing.

        When ``classification`` (output of ``identity_resolver.classify_profiles``)
        reports same-name candidates, the output is split into a PRIMARY TARGET
        group and a SAME-NAME CANDIDATES group so the model does not merge two
        people into one description. Otherwise a flat listing is used.

        Only profiles whose status is ``found`` appear, and a `[SEARCH]`
        placeholder is never emitted.
        """
        if classification and classification.get("has_others"):
            return self._format_grouped_profiles(classification)

        source = classification["profiles"] if classification else profiles
        found = to_social_profiles(source)

        formatted = "Social Media Profiles and Bios:\n"
        if not found:
            return formatted + "No social media profiles found.\n"

        grouped: dict[str, list[SocialProfile]] = {}
        for profile in found:
            grouped.setdefault(profile.platform, []).append(profile)
        for platform, items in grouped.items():
            formatted += self._format_platform_block(platform, items)
        return formatted

    def _format_platform_block(self, platform: str, items: Sequence[SocialProfile]) -> str:
        """Render one platform's accounts as text."""
        label = "MENTION" if platform in _MENTION_PLATFORMS else platform.upper()
        block = f"[{label}: {platform.upper()}]\n"
        for item in items:
            block += f"- URL: {item.url}\n"
            if item.bio:
                block += f"  Bio/Snippet: {item.bio}\n"
        return block + "\n"

    def _format_grouped_profiles(self, classification: dict) -> str:
        """Render the accounts split into PRIMARY TARGET and SAME-NAME CANDIDATES.

        The ``match`` label lives on the legacy row, so it is indexed by URL
        before the rows are normalised into `SocialProfile`.
        """
        raw = classification["profiles"]
        anchor = classification.get("anchor", "no strong anchor signals")

        match_by_url: dict[str, str] = {}
        if isinstance(raw, Mapping):
            for items in raw.values():
                for item in items or []:
                    url = _attr(item, "url")
                    if url:
                        match_by_url[str(url)] = str(_attr(item, "match") or "primary")

        primary: dict[str, list[SocialProfile]] = {}
        others: dict[str, list[SocialProfile]] = {}
        divergent_urls: set[str] = set()
        for profile in to_social_profiles(raw):
            label = match_by_url.get(profile.url or "", "primary")
            if label == "divergent":
                divergent_urls.add(profile.url or "")
            bucket = primary if label == "primary" else others
            bucket.setdefault(profile.platform, []).append(profile)

        formatted = (
            "Social Media Profiles and Bios:\n"
            f"ANCHOR IDENTITY (the confirmed target): {anchor}\n\n"
            "=== PRIMARY TARGET — use ONLY these accounts for the description ===\n"
        )
        if primary:
            for platform, items in primary.items():
                formatted += self._format_platform_block(platform, items)
        else:
            formatted += "(no high-confidence accounts matched the anchor)\n\n"

        formatted += (
            "=== SAME-NAME CANDIDATES — likely DIFFERENT people, do NOT attribute their facts to the target ===\n"
        )
        for platform, items in others.items():
            formatted += self._format_platform_block(platform, items)
            if all((item.url or "") in divergent_urls for item in items):
                formatted += "  [likely different person]\n"

        return formatted
