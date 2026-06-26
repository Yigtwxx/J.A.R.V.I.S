"""Deterministic identity disambiguation for collected social profiles.

When a person is searched by name, the scraper intentionally collects many
candidate profiles per platform. Some of those profiles belong to DIFFERENT
people who merely share the same name. This module annotates each profile with a
``match`` label (``primary`` / ``candidate`` / ``divergent``) relative to an
*anchor identity* derived from the most trustworthy available signals: the
GitHub account (already cross-validated upstream), the searched name, and any
handle that recurs across multiple platforms.

Design constraints:
- It NEVER drops profiles — it only labels them. The downstream formatter still
  lists every account, so the "show many accounts" behaviour is preserved.
- It is conservative: disambiguation only activates when a confident anchor
  handle exists. Without one, every profile is labelled ``primary`` (i.e. the
  legacy behaviour), so we never hide the real profile on a weak guess.
- It is fully deterministic and offline — no extra LLM calls.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

MatchLabel = Literal["primary", "candidate", "divergent"]

# Mention-only platforms carry no verifiable handle; never gate identity on them.
_MENTION_PLATFORMS = {"tinder", "bumble", "discord"}

# A handle must recur on at least this many platforms to count as a cross-platform
# identity anchor (used only when no GitHub account is available).
_DOMINANT_HANDLE_MIN_PLATFORMS = 2


class IdentityClassification(TypedDict):
    """Result of :func:`classify_profiles`."""

    anchor: str
    profiles: dict[str, list[dict[str, Any]]]  # platform -> profile dicts (with "match")
    has_others: bool


@dataclass
class _Anchor:
    handle: str = ""
    name_tokens: set[str] = field(default_factory=set)
    location_tokens: set[str] = field(default_factory=set)

    @property
    def is_confident(self) -> bool:
        # We can only split same-name people apart when we have a stable handle to
        # compare against. Name/location alone are too weak (that's the whole point
        # of the bug — many namesakes share them).
        return bool(self.handle)

    def summary(self) -> str:
        parts: list[str] = []
        if self.handle:
            parts.append(f"handle '@{self.handle}'")
        if self.name_tokens:
            parts.append(f"name tokens {sorted(self.name_tokens)}")
        if self.location_tokens:
            parts.append(f"location {sorted(self.location_tokens)}")
        return "; ".join(parts) if parts else "no strong anchor signals"


def _normalize(text: str | None) -> str:
    """Lowercase and strip diacritics for fuzzy comparison."""
    nfkd = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _tokens(text: str | None) -> set[str]:
    """Split text into normalized alphanumeric tokens of length > 1."""
    return {t for t in re.split(r"[^a-z0-9]+", _normalize(text)) if len(t) > 1}


def _handle_from_url(url: str | None) -> str:
    """Extract the trailing user handle from a profile URL (normalized)."""
    if not url:
        return ""
    path = re.sub(r"[?#].*$", "", url).rstrip("/")
    segment = path.rsplit("/", 1)[-1].lstrip("@")
    # Drop obvious non-handle path keywords (e.g. linkedin '/in/', youtube '/channel/').
    if segment in {"in", "channel", "c", "user", "profile", "u"}:
        return ""
    return _normalize(segment)


def _build_anchor(
    github_data: dict | None,
    real_name: str,
    social_profiles: dict[str, list[dict[str, Any]]],
) -> _Anchor:
    anchor = _Anchor(name_tokens=_tokens(real_name))

    if github_data:
        anchor.handle = _normalize(github_data.get("login"))
        anchor.location_tokens = _tokens(github_data.get("location"))
        anchor.name_tokens |= _tokens(github_data.get("name"))

    # Fallback anchor: a handle that recurs across multiple platforms is a strong
    # single-identity signal even without GitHub.
    if not anchor.handle:
        handle_platforms: Counter[str] = Counter()
        for platform, items in social_profiles.items():
            if platform in _MENTION_PLATFORMS:
                continue
            seen: set[str] = set()
            for item in items or []:
                handle = _handle_from_url(item.get("url"))
                if handle and handle not in seen:
                    handle_platforms[handle] += 1
                    seen.add(handle)
        if handle_platforms:
            top_handle, platform_count = handle_platforms.most_common(1)[0]
            if platform_count >= _DOMINANT_HANDLE_MIN_PLATFORMS:
                anchor.handle = top_handle

    return anchor


def _label_profile(item: dict[str, Any], anchor: _Anchor) -> MatchLabel:
    handle = _handle_from_url(item.get("url"))
    bio_tokens = _tokens(item.get("bio"))
    handle_tokens = _tokens(handle)

    # Does this profile carry any positive evidence tying it to the anchor identity?
    has_support = bool(anchor.name_tokens & (bio_tokens | handle_tokens)) or bool(anchor.location_tokens & bio_tokens)

    if handle and anchor.handle:
        if handle == anchor.handle or anchor.handle in handle or handle in anchor.handle:
            return "primary"
        # Different handle from the anchor: only a hard "different person" call when
        # there is also zero supporting evidence. Otherwise stay cautious.
        return "candidate" if has_support else "divergent"

    # No comparable handle — cannot confirm it is the target, but no conflict either.
    return "candidate"


def anchor_corroborated_by_web(
    github_data: dict | None,
    raw_sources: list[dict[str, Any]] | None,
    deep_context: str = "",
) -> bool | None:
    """Whether the web/deep corpus corroborates the GitHub anchor via a DISTINCTIVE,
    non-name signal (the GitHub login or profile URL). Name tokens are deliberately
    NOT used here: a famous same-name namesake shares them, so only an identity-unique
    marker proves the web is actually about the anchored subject.

    Returns True/False when a GitHub anchor exists, or None when there is no GitHub
    anchor to corroborate (caller should fall back to other signals)."""
    if not github_data:
        return None
    login = _normalize(github_data.get("login"))
    profile_url = (github_data.get("profile_url") or "").lower()
    blob = _normalize(
        " ".join(f"{s.get('title', '')} {s.get('snippet', '')} {s.get('url', '')}" for s in (raw_sources or []))
    )
    blob += " " + _normalize(deep_context or "")
    if login and len(login) > 2 and login in blob:
        return True
    if profile_url and profile_url in blob:
        return True
    return False


def web_relevance_ratio(real_name: str, raw_sources: list[dict[str, Any]] | None) -> float | None:
    """Fraction of web sources whose title+snippet contains every token of the
    subject name. A low ratio means the web corpus is dominated by a different
    same-name person and should not drive the AI briefing. Returns None when there
    is nothing to measure."""
    name_tokens = _tokens(real_name)
    sources = raw_sources or []
    if not name_tokens or not sources:
        return None
    relevant = sum(
        1 for s in sources if name_tokens <= _tokens(f"{s.get('title', '')} {s.get('snippet', '')}")
    )
    return round(relevant / len(sources), 2)


def _filter_deep_nodes(deep_context: str, dropped_urls: set[str]) -> str:
    """Drop scraped deep-context node blocks whose source URL is a known off-target
    (different-name) result. Conservative: only removes nodes we have positive
    evidence are about a different person; unknown nodes are kept."""
    if not deep_context or not dropped_urls:
        return deep_context
    header_re = re.compile(r"--- (?:DEEP )?NODE[^\n]*?---")
    matches = list(header_re.finditer(deep_context))
    if not matches:
        return deep_context
    kept: list[str] = []
    preamble = deep_context[: matches[0].start()]
    if preamble.strip():
        kept.append(preamble)
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(deep_context)
        block = deep_context[match.start() : end]
        url_match = re.search(r"https?://\S+", match.group(0))
        url = url_match.group(0).rstrip(" -") if url_match else ""
        if url and url in dropped_urls:
            continue  # off-target namesake source — drop it
        kept.append(block)
    return "".join(kept)


def filter_intelligence_sources(
    real_name: str,
    web_results: str,
    deep_context: str,
    raw_sources: list[dict[str, Any]] | None,
) -> tuple[str, str, int]:
    """Deterministically drop web/deep sources that do not match the subject name.

    A source is kept only when every token of the subject name appears in its
    title+snippet (the same relevance test used for subject-confidence scoring).
    This removes a famous, differently-named namesake (e.g. results about a person
    whose name lacks a query token) before they can hijack the AI briefing.

    Returns ``(filtered_web_results, filtered_deep_context, dropped_count)``. Falls
    back to the original web text when filtering would remove every source, so a
    low-footprint legitimate subject is never left with an empty web section.
    """
    name_tokens = _tokens(real_name)
    if not name_tokens or not raw_sources:
        return web_results, deep_context, 0

    kept_sources: list[dict[str, Any]] = []
    dropped_urls: set[str] = set()
    for source in raw_sources:
        text_tokens = _tokens(f"{source.get('title', '')} {source.get('snippet', '')}")
        if name_tokens <= text_tokens:
            kept_sources.append(source)
        elif source.get("url"):
            dropped_urls.add(source["url"])

    if not dropped_urls:
        return web_results, deep_context, 0

    if kept_sources:
        web_out = "\n".join(
            f"- {s.get('title', '')} — {s.get('snippet', '')} ({s.get('url', '')})" for s in kept_sources
        )
    else:
        web_out = web_results  # never blank out the web section entirely

    deep_out = _filter_deep_nodes(deep_context, dropped_urls)
    return web_out, deep_out, len(dropped_urls)


def classify_profiles(
    social_profiles: dict[str, list[dict[str, Any]]],
    github_data: dict | None = None,
    real_name: str = "",
    web_results: str = "",  # reserved for future signal use; kept for a stable API
) -> IdentityClassification:
    """Annotate each social profile with an identity ``match`` label.

    Returns the original profile dicts (copied) with an added ``match`` key, plus
    a human-readable ``anchor`` summary for the AI prompt and a ``has_others``
    flag indicating whether any same-name candidate/divergent profile was found.
    """
    anchor = _build_anchor(github_data, real_name, social_profiles)

    profiles_out: dict[str, list[dict[str, Any]]] = {}
    has_others = False

    for platform, items in social_profiles.items():
        annotated: list[dict[str, Any]] = []
        for item in items or []:
            new_item = dict(item)
            if not anchor.is_confident or platform in _MENTION_PLATFORMS:
                # No confident anchor (or mention-only platform): do not risk a
                # split — treat as primary, matching legacy behaviour.
                new_item["match"] = "primary"
            else:
                label = _label_profile(item, anchor)
                new_item["match"] = label
                if label != "primary":
                    has_others = True
            annotated.append(new_item)
        profiles_out[platform] = annotated

    return IdentityClassification(
        anchor=anchor.summary(),
        profiles=profiles_out,
        has_others=has_others,
    )
