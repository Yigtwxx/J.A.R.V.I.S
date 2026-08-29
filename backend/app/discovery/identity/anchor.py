"""The anchor identity: the one subject every candidate is judged against.

An anchor is only useful when it carries an **identity-unique marker** — a
confirmed handle. Name and location alone are exactly what same-name people
share, so anchoring on them is what produced mixed-identity dossiers in the
first place. Hence :attr:`Anchor.is_confident` requires both a handle and the
reason it is trusted.

Production bug this module fixes: ``GitHubService.get_user_profile`` emits the
handle under the key ``"username"`` (``github_service.py:91``), while the old
resolver read ``"login"``. The anchor handle was therefore always empty and the
whole disambiguation path was dead code. Both keys are accepted here.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from app.discovery.identity.normalize import (
    is_similar_handle,
    name_tokens,
    normalize_handle,
    normalize_org,
    token_overlap,
)
from app.discovery.types import EntityType

CONFIRMED_GITHUB_API = "github_api"
CONFIRMED_USER_ANSWER = "user_answer"
CONFIRMED_RECIPROCAL_LINK = "reciprocal_link"

_LOCATION_OVERLAP_FLOOR = 0.01
_EMPLOYER_OVERLAP_FLOOR = 0.34


@dataclass(slots=True)
class Anchor:
    """The subject of a search, as far as we can currently prove it."""

    name: str
    tokens: tuple[str, ...]
    entity: EntityType
    handle: str = ""
    """The identity-unique marker, if we have one."""

    handle_platform: str = ""
    location_tokens: tuple[str, ...] = ()
    employer: str = ""
    school: str = ""
    email: str = ""
    domain: str = ""
    confirmed_by: str = ""
    """``github_api`` | ``user_answer`` | ``reciprocal_link`` | ``""``."""

    @property
    def is_confident(self) -> bool:
        """A handle alone is a guess; a handle plus the reason it is trusted is an anchor."""
        return bool(self.handle) and bool(self.confirmed_by)

    def summary(self) -> str:
        """One-line human-readable description, for logs and prompts."""
        parts: list[str] = [f"name '{self.name}'"]
        if self.handle:
            parts.append(f"handle '@{self.handle}' via {self.confirmed_by or 'unconfirmed'}")
        if self.employer:
            parts.append(f"employer '{self.employer}'")
        if self.school:
            parts.append(f"school '{self.school}'")
        if self.location_tokens:
            parts.append(f"location {list(self.location_tokens)}")
        return "; ".join(parts)


def _merge_tokens(*groups: tuple[str, ...]) -> tuple[str, ...]:
    """Concatenate token groups, order preserved, duplicates removed."""
    seen: set[str] = set()
    out: list[str] = []
    for group in groups:
        for token in group:
            if token not in seen:
                seen.add(token)
                out.append(token)
    return tuple(out)


def _domain_from_blog(blog: str) -> str:
    host = (blog or "").strip().lower()
    if not host:
        return ""
    host = host.split("//")[-1].split("/", 1)[0].split(":", 1)[0]
    return host[4:] if host.startswith("www.") else host


def build_anchor(name: str, entity: EntityType, *, github_data: dict[str, Any] | None = None) -> Anchor:
    """Build the anchor from the searched name plus any GitHub profile we already have.

    GitHub is the only source in the pipeline with a real, keyless, authoritative
    API, so when it is present it supplies the handle and every corroborating
    attribute (employer, location, email, personal domain).
    """
    anchor = Anchor(name=(name or "").strip(), tokens=name_tokens(name), entity=entity)
    if not github_data:
        return anchor

    # Accept BOTH spellings: GitHubService emits "username", the raw API says "login".
    handle = normalize_handle(str(github_data.get("username") or github_data.get("login") or ""))
    if handle:
        anchor.handle = handle
        anchor.handle_platform = "github"
        anchor.confirmed_by = CONFIRMED_GITHUB_API

    anchor.tokens = _merge_tokens(anchor.tokens, name_tokens(str(github_data.get("name") or "")))
    anchor.location_tokens = name_tokens(str(github_data.get("location") or ""))
    anchor.employer = normalize_org(str(github_data.get("company") or ""))
    anchor.email = (str(github_data.get("email") or "")).strip().lower()
    anchor.domain = _domain_from_blog(str(github_data.get("blog") or ""))
    return anchor


def strengthen(anchor: Anchor, *, handle: str, platform: str, reason: str) -> Anchor:
    """Return a NEW anchor carrying a stronger handle. The input is never mutated.

    An already-confirmed handle is not overwritten by a later, weaker claim: the
    first proof wins, so a reciprocal link cannot quietly displace a GitHub API
    confirmation.
    """
    cleaned = normalize_handle(handle)
    if not cleaned:
        return replace(anchor)
    if anchor.is_confident and not is_similar_handle(anchor.handle, cleaned):
        return replace(anchor)
    return replace(
        anchor,
        handle=cleaned,
        handle_platform=platform or anchor.handle_platform,
        confirmed_by=reason or anchor.confirmed_by,
    )


def conflicts(a: Anchor, b: Anchor) -> bool:
    """Whether two anchors provably describe different people.

    Two independent grounds, both deliberately strict — a false conflict silently
    discards the real subject:

    1. Both sides carry a *confirmed* handle and the handles are not the same.
    2. Employer and location BOTH disagree. Either one alone is far too weak:
       people change jobs, and location strings are written a dozen ways.
    """
    if a.is_confident and b.is_confident and not is_similar_handle(a.handle, b.handle):
        return True

    employer_conflict = bool(a.employer) and bool(b.employer) and a.employer != b.employer
    if employer_conflict:
        employer_conflict = token_overlap(a.employer.split(), b.employer.split()) <= _EMPLOYER_OVERLAP_FLOOR

    location_conflict = bool(a.location_tokens) and bool(b.location_tokens)
    if location_conflict:
        location_conflict = token_overlap(a.location_tokens, b.location_tokens) < _LOCATION_OVERLAP_FLOOR

    return employer_conflict and location_conflict
