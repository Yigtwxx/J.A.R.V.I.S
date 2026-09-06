"""Declarative description of one platform.

Everything the existence checker and the extractor need to know about a site
lives here as data, so `existence.py` and `extract.py` stay generic and adding a
platform never means adding a branch.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from app.discovery.types import EntityType, FetchTier, PlatformTier

OracleKind = Literal["json", "xml", "rss", "status", "embedded_json"]
"""``embedded_json`` reads a JSON blob out of a ``<script>`` tag on an HTML page.

Some platforms serve no JSON endpoint but hand the same data to their own
front-end inside the markup — TikTok's ``/embed/@handle`` page is the case this
was added for, and it answers over plain HTTP what the profile page only answers
to a browser."""


@dataclass(frozen=True, slots=True)
class OracleRoute:
    """A second way to ask the same question when the first way is refused.

    Hosts do not block uniformly. Reddit answers ``/about.json`` with 403 from a
    residential IP while serving the same account's ``.rss`` feed with 200, so a
    single blocked endpoint is a fact about that endpoint, not about the account.

    ``authoritative`` is the guard on the pipeline's first invariant. A route we
    trust only partially may confirm existence, but it may never be the reason we
    tell a user an account does not exist — an alternate route that comes up empty
    means "this route did not see it", which is not the same as absence.
    """

    url: str
    """URL template containing ``{username}``."""

    kind: OracleKind = "status"
    exists_path: str | None = None
    absent_path: str | None = None
    selector: str | None = None
    """For ``embedded_json``: the ``<script>`` tag holding the payload."""

    not_found_status: tuple[int, ...] = ()
    """Codes that mean absence *on this route only*.

    Route-scoped rather than platform-scoped because the same code can mean
    different things at different endpoints: TikTok's embed answers 400 for a
    handle that does not exist, while a 400 from its profile page means nothing
    of the sort."""

    authoritative: bool = True
    label: str = ""

    def for_username(self, username: str) -> str:
        return self.url.format(username=username)


@dataclass(frozen=True, slots=True)
class PlatformSpec:
    """How to find, verify and read one platform's profiles."""

    key: str
    display: str
    profile_url: str
    """URL template containing ``{username}``."""

    host: str = ""
    tier: PlatformTier = PlatformTier.CORE
    fetch_tier: FetchTier = FetchTier.HTTP
    """Which transport to *start* with. STEALTH means the HTTP tier is pointless."""

    escalate: bool = True

    # -- existence oracle (strongest signal; no HTML parsing involved) --------
    oracle_url: str | None = None
    oracle_kind: OracleKind | None = None
    oracle_exists_path: str | None = None
    """Dotted path that must be present in a JSON oracle response."""

    oracle_absent_path: str | None = None
    """Dotted path whose presence means "definitely not found" (e.g. Steam's ``error``)."""

    oracle_selector: str | None = None
    """For an ``embedded_json`` oracle: the ``<script>`` tag holding the payload."""

    fallback_oracles: tuple[OracleRoute, ...] = ()
    """Tried in order when the primary oracle is *refused*, never when it answers."""

    not_found_status: tuple[int, ...] = (404, 410)

    # -- HTML-based existence fallbacks --------------------------------------
    canonical_check: bool = True
    og_image_implies_exists: bool = False
    embedded_json_selector: str | None = None
    embedded_json_pattern: str | None = None
    """Regex with one capture group, applied to raw markup (``ytInitialData`` etc.)."""

    embedded_json_path: str | None = None

    # -- capabilities (honest, drives the UI and the summary) -----------------
    supports_avatar: bool = True
    supports_bio: bool = True
    supports_counts: bool = False
    expected_reliability: float = 0.7
    """Rough share of logged-out checks that succeed. Pessimistic on purpose."""

    # -- identity / hygiene ---------------------------------------------------
    reserved: frozenset[str] = frozenset()
    username_charset: str | None = None
    entity_types: frozenset[EntityType] = frozenset({EntityType.PERSON})
    category: str = "social"
    max_fetches_per_session: int | None = None
    """Hard cap for hostile hosts. LinkedIn soft-bans an IP that is hammered."""

    notes: str = ""

    _charset_re: Any = field(default=None, init=False, repr=False, compare=False)

    def profile_for(self, username: str) -> str:
        return self.profile_url.format(username=username)

    def oracle_for(self, username: str) -> str | None:
        return self.oracle_url.format(username=username) if self.oracle_url else None

    def oracle_routes(self) -> tuple[OracleRoute, ...]:
        """The primary oracle followed by its fallbacks, as one uniform sequence.

        The primary is always authoritative: it is the endpoint the platform
        publishes for exactly this question, so when it answers "no" it is right.
        """
        primary: tuple[OracleRoute, ...] = ()
        if self.oracle_url:
            primary = (
                OracleRoute(
                    url=self.oracle_url,
                    kind=self.oracle_kind or "status",
                    exists_path=self.oracle_exists_path,
                    absent_path=self.oracle_absent_path,
                    selector=self.oracle_selector,
                    not_found_status=self.not_found_status,
                    authoritative=True,
                ),
            )
        return primary + self.fallback_oracles

    def accepts_username(self, username: str) -> bool:
        """Charset/length legality on this platform. No regex means "anything goes"."""
        if not username:
            return False
        if username.lower() in self.reserved:
            return False
        if not self.username_charset:
            return True
        try:
            return re.match(self.username_charset, username) is not None
        except re.error:
            return True

    def applies_to(self, entity: EntityType) -> bool:
        return entity in self.entity_types

    @property
    def is_supported(self) -> bool:
        """False for platforms with no public surface at all (Discord, Tinder, …)."""
        return bool(self.profile_url)


def spec_from_dict(raw: dict[str, Any], *, tier: PlatformTier = PlatformTier.EXTENDED) -> PlatformSpec:
    """Build a PlatformSpec from the JSON data file.

    Unknown keys are ignored and missing keys fall back to the dataclass defaults,
    so a data file written against an older schema still loads.
    """
    entity_types = frozenset(EntityType(e) for e in raw.get("entity_types") or ["person"])
    not_found = raw.get("not_found_status") or [404, 410]
    oracle_kind = raw.get("oracle_kind")
    return PlatformSpec(
        key=str(raw["key"]),
        display=str(raw.get("display") or raw["key"].title()),
        profile_url=str(raw["profile_url"]),
        host=str(raw.get("host") or ""),
        tier=tier,
        fetch_tier=FetchTier(raw.get("fetch_tier", "http")),
        escalate=bool(raw.get("escalate", True)),
        oracle_url=raw.get("oracle_url") or None,
        oracle_kind=oracle_kind if oracle_kind in ("json", "xml", "rss", "status", "embedded_json") else None,
        oracle_selector=raw.get("oracle_selector") or None,
        oracle_exists_path=raw.get("oracle_exists_path") or None,
        oracle_absent_path=raw.get("oracle_absent_path") or None,
        not_found_status=tuple(int(c) for c in not_found),
        canonical_check=bool(raw.get("canonical_check", True)),
        og_image_implies_exists=bool(raw.get("og_image_implies_exists", False)),
        embedded_json_selector=raw.get("embedded_json_selector") or None,
        embedded_json_pattern=raw.get("embedded_json_pattern") or None,
        embedded_json_path=raw.get("embedded_json_path") or None,
        supports_avatar=bool(raw.get("supports_avatar", True)),
        supports_bio=bool(raw.get("supports_bio", True)),
        supports_counts=bool(raw.get("supports_counts", False)),
        expected_reliability=float(raw.get("expected_reliability", 0.7)),
        reserved=frozenset(str(r).lower() for r in raw.get("reserved") or ()),
        username_charset=raw.get("username_charset") or None,
        entity_types=entity_types,
        category=str(raw.get("category") or "misc"),
        max_fetches_per_session=raw.get("max_fetches_per_session"),
        notes=str(raw.get("notes") or ""),
    )
