"""The platform catalogue: CORE (swept always) plus EXTENDED (long tail).

CORE entries are hand-written because each one carries a real oracle endpoint and
honest reliability notes. EXTENDED entries load from
``data/extended_platforms.json`` and are only checked at higher depth or once a
confirmed handle exists — sweeping 100+ sites against a name permutation is a
false-positive factory, not thoroughness.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Mapping
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType

from app.discovery.platforms.spec import OracleRoute, PlatformSpec, spec_from_dict
from app.discovery.types import EntityType, FetchTier, PlatformTier
from app.utils.logger import logger

_DATA_DIR = Path(__file__).parent / "data"
_EXTENDED_FILE = _DATA_DIR / "extended_platforms.json"

_PERSON = frozenset({EntityType.PERSON})
_PERSON_COMPANY = frozenset({EntityType.PERSON, EntityType.COMPANY})
_ALL_ENTITIES = frozenset({EntityType.PERSON, EntityType.COMPANY, EntityType.PLACE})


# Platforms with no public surface at all. Listed so the API can report
# `unsupported` instead of pretending the search simply found nothing.
#
# A mapping rather than a set, because the reason has to reach the platform
# picker. Offering a choice that cannot do anything is the same failure as an
# empty status — it looks like a finding and is not one.
# `key in UNSUPPORTED_PLATFORMS` still works.
UNSUPPORTED_PLATFORMS: Mapping[str, str] = MappingProxyType(
    {
        "discord": "no public profile page exists to check",
        "tinder": "no public profile page exists to check",
        "bumble": "no public profile page exists to check",
        "whatsapp": "no public profile page exists to check",
        "signal": "no public profile page exists to check",
    }
)


# Platforms whose public profile page is real and indexable, but which no
# anonymous route can *confirm*. They are searched and reported; they are never
# probed.
#
# `spotify` was put in UNSUPPORTED_PLATFORMS on 2026-08-29 because its existence
# check is genuinely unanswerable. Re-measured 2026-08-30, unchanged:
#
#   * its oEmbed endpoint answers **400** for any `/user/` URL — encoded or not —
#     while the same call for an `/artist/` URL returns 200 and JSON, so the
#     oracle this platform shipped with could never succeed;
#   * the profile page returns **200 for a handle that does not exist**, within
#     13 bytes of the real one's ~157 KB. Falling back to it would have turned
#     every guessed handle into a confirmed account;
#   * a real browser renders the same "Spotify - Web Player" shell for both,
#     because user profiles now sit behind an account.
#
# All of that is true, and none of it means the account cannot be *found*.
# `open.spotify.com/user/...` is a public URL search engines index, and one that
# arrives from a SERP, an outbound link or the user carries its own evidence —
# there is nothing left for a probe to add. Retiring the platform answered "we
# cannot confirm a guess" with "we will not report the account", which is how a
# search holding the profile URL still came back with no Spotify account.
#
# Artists and playlists remain public; only *user* existence is unanswerable.
DISCOVERY_ONLY_PLATFORMS: Mapping[str, str] = MappingProxyType(
    {
        "spotify": (
            "found only when a search engine or a link points at it: no anonymous "
            "route can confirm a Spotify handle, real or invented"
        ),
    }
)


def is_discovery_only(platform: str) -> bool:
    """True for a platform that may be found by URL but must never be probed blind."""
    return platform in DISCOVERY_ONLY_PLATFORMS


# Platforms deliberately kept out of the social sweep. They have public profiles,
# but they are not treated as social media here, so nothing probes or reports
# them. The data file is regenerated from time to time, hence the guard below.
EXCLUDED_PLATFORMS: frozenset[str] = frozenset({"medium", "soundcloud"})


CORE_PLATFORMS: tuple[PlatformSpec, ...] = (
    PlatformSpec(
        key="github",
        display="GitHub",
        profile_url="https://github.com/{username}",
        host="github.com",
        oracle_url="https://api.github.com/users/{username}",
        oracle_kind="json",
        oracle_exists_path="login",
        supports_counts=True,
        expected_reliability=0.99,
        username_charset=r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$",
        entity_types=_PERSON_COMPANY,
        category="developer",
        notes="Real REST API. The single most reliable source in the pipeline.",
    ),
    PlatformSpec(
        key="bluesky",
        display="Bluesky",
        profile_url="https://bsky.app/profile/{username}",
        host="bsky.app",
        oracle_url="https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile?actor={username}",
        oracle_kind="json",
        oracle_exists_path="did",
        supports_counts=True,
        expected_reliability=0.95,
        entity_types=_PERSON_COMPANY,
        category="social",
        notes="Public XRPC API, no auth required.",
    ),
    PlatformSpec(
        key="reddit",
        display="Reddit",
        profile_url="https://www.reddit.com/user/{username}/",
        host="reddit.com",
        oracle_url="https://www.reddit.com/user/{username}/about.json",
        oracle_kind="json",
        oracle_exists_path="data.name",
        # Verified live 2026-08-22: about.json answered 403 from a residential IP
        # on every attempt while the same account's Atom feed answered 200. The
        # feed is not authoritative — a private or suspended account has no feed
        # yet still exists — so it may confirm a handle but never deny one.
        fallback_oracles=(
            OracleRoute(
                url="https://www.reddit.com/user/{username}/.rss",
                kind="rss",
                authoritative=False,
                label="rss",
            ),
        ),
        supports_counts=True,
        expected_reliability=0.9,
        username_charset=r"^[A-Za-z0-9_\-]{3,20}$",
        category="forum",
        notes="about.json is authoritative, but many IPs get 403 -> blocked, not absent.",
    ),
    PlatformSpec(
        key="youtube",
        display="YouTube",
        profile_url="https://www.youtube.com/@{username}",
        host="youtube.com",
        embedded_json_pattern=r"ytInitialData\s*=\s*(\{.+?\})\s*;\s*</script>",
        embedded_json_path="metadata.channelMetadataRenderer",
        supports_counts=True,
        expected_reliability=0.9,
        entity_types=_ALL_ENTITIES,
        category="video",
    ),
    PlatformSpec(
        key="steam",
        display="Steam",
        profile_url="https://steamcommunity.com/id/{username}",
        host="steamcommunity.com",
        oracle_url="https://steamcommunity.com/id/{username}?xml=1",
        oracle_kind="xml",
        oracle_exists_path="steamID64",
        oracle_absent_path="error",
        expected_reliability=0.85,
        category="gaming",
        notes="Private profiles still resolve; only the bio is hidden.",
    ),
    PlatformSpec(
        key="x",
        display="X (Twitter)",
        profile_url="https://x.com/{username}",
        host="x.com",
        oracle_url="https://publish.twitter.com/oembed?url=https://twitter.com/{username}",
        oracle_kind="json",
        # Verified live: the endpoint answers 200 with a `url` field for a real
        # handle and 404 for a missing one. It no longer returns `author_name`,
        # so `url` is the only field that reliably proves existence.
        oracle_exists_path="url",
        supports_avatar=False,
        supports_bio=False,
        supports_counts=False,
        expected_reliability=0.8,
        username_charset=r"^[A-Za-z0-9_]{1,15}$",
        entity_types=_ALL_ENTITIES,
        category="social",
        notes=(
            "Existence + display name only. The avatar is genuinely unobtainable "
            "logged-out: no og:* for anonymous clients, syndication endpoints dead, "
            "Nitter instances offline. Never fabricate one."
        ),
    ),
    PlatformSpec(
        key="pinterest",
        display="Pinterest",
        profile_url="https://www.pinterest.com/{username}/",
        host="pinterest.com",
        og_image_implies_exists=True,
        supports_counts=True,
        expected_reliability=0.8,
        username_charset=r"^[A-Za-z0-9_]{3,30}$",
        entity_types=_PERSON_COMPANY,
        category="photo",
    ),
    PlatformSpec(
        key="tumblr",
        display="Tumblr",
        profile_url="https://{username}.tumblr.com",
        host="tumblr.com",
        oracle_url="https://{username}.tumblr.com",
        oracle_kind="status",
        supports_bio=False,
        expected_reliability=0.8,
        username_charset=r"^[A-Za-z0-9\-]{1,32}$",
        category="blogging",
        notes="Custom themes make bio extraction unreliable; the avatar API is keyless.",
    ),
    PlatformSpec(
        key="spotify",
        display="Spotify",
        profile_url="https://open.spotify.com/user/{username}",
        host="open.spotify.com",
        # No oracle, deliberately. The oEmbed route this spec shipped with answers
        # 400 for every `/user/` URL, so it spent three requests per candidate to
        # learn nothing. See DISCOVERY_ONLY_PLATFORMS above: the account is found
        # from an indexed URL or not at all.
        supports_bio=False,
        expected_reliability=0.75,
        entity_types=_PERSON_COMPANY,
        category="music",
        notes="Discovery-only: dorked and reported, never probed. User existence is unanswerable anonymously.",
    ),
    PlatformSpec(
        key="snapchat",
        display="Snapchat",
        profile_url="https://www.snapchat.com/add/{username}",
        host="snapchat.com",
        og_image_implies_exists=True,
        supports_bio=False,
        expected_reliability=0.75,
        username_charset=r"^[A-Za-z0-9._\-]{3,15}$",
        category="social",
        notes="Only accounts with a public profile are visible at all.",
    ),
    PlatformSpec(
        key="instagram",
        display="Instagram",
        profile_url="https://www.instagram.com/{username}/",
        host="instagram.com",
        # Verified live 2026-08-22: the logged-out profile page serves the full
        # og:* block over plain HTTP, counts included. Pinning this to the browser
        # tier meant blind handles were reported "blocked" without ever being
        # tried (existence.py's stealth-reserved short-circuit), and corroborated
        # ones paid 3-8 s for data the cheap tier already had. Escalation still
        # covers the days Instagram decides to serve a login wall instead.
        fetch_tier=FetchTier.HTTP,
        escalate=True,
        og_image_implies_exists=True,
        supports_counts=True,
        expected_reliability=0.7,
        username_charset=r"^[A-Za-z0-9._]{1,30}$",
        entity_types=_ALL_ENTITIES,
        category="social",
        notes="og:description carries counts but is localised — parse positionally on numbers.",
    ),
    PlatformSpec(
        key="tiktok",
        display="TikTok",
        profile_url="https://www.tiktok.com/@{username}",
        host="tiktok.com",
        # Verified live 2026-08-22: the profile page hands an anonymous HTTP client
        # a 1.5 KB shell, but /embed/@handle serves 300+ KB carrying the full
        # userInfo — uniqueId, nickname, signature, followerCount — and answers 400
        # for a handle that does not exist. So existence is settled over plain HTTP
        # and the browser is spent only on reading the profile itself.
        oracle_url="https://www.tiktok.com/embed/@{username}",
        oracle_kind="embedded_json",
        oracle_selector="script#__FRONTITY_CONNECT_STATE__",
        # The payload keys the profile by the request path, so the handle appears
        # inside the key; the wildcard avoids hard-coding a casing TikTok may change.
        oracle_exists_path="source.data.*.userInfo.uniqueId",
        not_found_status=(400, 404, 410),
        fetch_tier=FetchTier.STEALTH,
        embedded_json_selector="script#__UNIVERSAL_DATA_FOR_REHYDRATION__",
        embedded_json_path="__DEFAULT_SCOPE__.webapp\\.user-detail.userInfo",
        og_image_implies_exists=True,
        supports_counts=True,
        expected_reliability=0.6,
        username_charset=r"^[A-Za-z0-9._]{2,24}$",
        entity_types=_ALL_ENTITIES,
        category="social",
    ),
    PlatformSpec(
        key="threads",
        display="Threads",
        profile_url="https://www.threads.com/@{username}",
        host="threads.com",
        # Verified live 2026-08-22 at both tiers: threads.net now redirects to
        # threads.com, and an anonymous request for any profile — HTTP *and* a real
        # browser — lands on threads.com/login with no og:* at all. Escalating costs
        # 3-8 s and 50-150 MB to reach the identical wall, so this one fails fast and
        # honestly as BLOCKED. Revisit if Threads ever serves logged-out profiles.
        fetch_tier=FetchTier.HTTP,
        escalate=False,
        og_image_implies_exists=True,
        supports_counts=True,
        expected_reliability=0.05,
        username_charset=r"^[A-Za-z0-9._]{1,30}$",
        category="social",
        notes=(
            "A confirmed Threads handle IS an Instagram handle — worth seeding both, and "
            "with Instagram now answering over HTTP that correlation is the only route "
            "that still yields anything. Direct checks are a login wall at every tier."
        ),
    ),
    PlatformSpec(
        key="facebook",
        display="Facebook",
        profile_url="https://www.facebook.com/{username}",
        host="facebook.com",
        # Verified live 2026-08-22: a Page serves og:image and og:title over plain
        # HTTP. Personal profiles still bounce to the login wall, which arrives as
        # a login_redirect block signal rather than as a fabricated absence.
        fetch_tier=FetchTier.HTTP,
        escalate=True,
        og_image_implies_exists=True,
        expected_reliability=0.35,
        entity_types=_ALL_ENTITIES,
        category="social",
        notes="Pages work; personal profiles are effectively closed (~10%).",
    ),
    PlatformSpec(
        key="linkedin",
        display="LinkedIn",
        profile_url="https://www.linkedin.com/in/{username}/",
        host="linkedin.com",
        # Verified live 2026-08-22: the public profile served og:image, og:title and
        # the headline over plain HTTP from a residential IP — no 999. LinkedIn is
        # erratic rather than uniformly hostile, so try the cheap tier and let the
        # escalation ladder handle the days it refuses. The per-session cap below
        # is what keeps that experiment from costing us the IP.
        fetch_tier=FetchTier.HTTP,
        escalate=True,
        supports_avatar=False,
        supports_counts=False,
        expected_reliability=0.3,
        max_fetches_per_session=3,
        entity_types=_ALL_ENTITIES,
        category="professional",
        notes=(
            "Often answers bots with HTTP 999, but not always — a residential IP with a "
            "consistent browser identity does get served. Hammering it soft-bans the IP "
            "and degrades every future search, hence the hard per-session cap. The "
            "highest-yield source is still SERP titles, which need zero linkedin.com requests."
        ),
    ),
    PlatformSpec(
        key="telegram",
        display="Telegram",
        profile_url="https://t.me/{username}",
        host="t.me",
        og_image_implies_exists=True,
        expected_reliability=0.85,
        username_charset=r"^[A-Za-z][A-Za-z0-9_]{4,31}$",
        entity_types=_PERSON_COMPANY,
        category="messaging",
    ),
    PlatformSpec(
        key="twitch",
        display="Twitch",
        profile_url="https://www.twitch.tv/{username}",
        host="twitch.tv",
        # Verified live: Twitch answers 200 with a generic shell (og:title just
        # "Twitch") for handles that do not exist, so og:image proves nothing here.
        # Only a canonical URL carrying the handle counts.
        og_image_implies_exists=False,
        supports_counts=False,
        expected_reliability=0.6,
        username_charset=r"^[A-Za-z0-9_]{4,25}$",
        category="gaming",
    ),
    PlatformSpec(
        key="mastodon",
        display="Mastodon",
        profile_url="https://mastodon.social/@{username}",
        host="mastodon.social",
        oracle_url="https://mastodon.social/api/v1/accounts/lookup?acct={username}",
        oracle_kind="json",
        oracle_exists_path="id",
        supports_counts=True,
        expected_reliability=0.9,
        category="social",
        notes="Only the flagship instance; other instances need their own host.",
    ),
)


class PlatformRegistry:
    """Lookup and filtering over the platform catalogue."""

    def __init__(self, specs: tuple[PlatformSpec, ...]) -> None:
        self._by_key: dict[str, PlatformSpec] = {s.key: s for s in specs}

    def __contains__(self, key: str) -> bool:
        return key in self._by_key

    def __len__(self) -> int:
        return len(self._by_key)

    def get(self, key: str) -> PlatformSpec | None:
        return self._by_key.get(key)

    def require(self, key: str) -> PlatformSpec:
        spec = self._by_key.get(key)
        if spec is None:
            raise KeyError(f"unknown platform: {key}")
        return spec

    def keys(self) -> frozenset[str]:
        return frozenset(self._by_key)

    def all(self) -> tuple[PlatformSpec, ...]:
        return tuple(self._by_key.values())

    def select(
        self,
        *,
        entity: EntityType,
        tier: PlatformTier | None = None,
        include_stealth: bool = True,
    ) -> tuple[PlatformSpec, ...]:
        """Platforms worth checking for this entity type, best-reliability first."""
        out = [
            spec
            for spec in self._by_key.values()
            if spec.applies_to(entity)
            and (tier is None or spec.tier is tier)
            and (include_stealth or spec.fetch_tier is not FetchTier.STEALTH)
        ]
        out.sort(key=lambda s: (-s.expected_reliability, s.key))
        return tuple(out)

    def host_map(self) -> dict[str, str]:
        """``platform key -> host``, used by the proxy platform filter."""
        return {spec.key: spec.host for spec in self._by_key.values() if spec.host}


@lru_cache(maxsize=1)
def load_extended_specs() -> tuple[PlatformSpec, ...]:
    """Parse the EXTENDED data file.

    A missing or malformed file degrades to "no extended platforms" with a warning:
    the long tail is a bonus, and losing it must never take the search down.
    """
    if not _EXTENDED_FILE.exists():
        logger.log_warning(f"Extended platform data not found at {_EXTENDED_FILE}; CORE platforms only.")
        return ()
    try:
        raw = json.loads(_EXTENDED_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.log_warning(f"Extended platform data unreadable ({exc}); CORE platforms only.")
        return ()

    core_keys = {spec.key for spec in CORE_PLATFORMS}
    out: list[PlatformSpec] = []
    for entry in raw.get("platforms") or []:
        try:
            spec = spec_from_dict(entry, tier=PlatformTier.EXTENDED)
        except (KeyError, TypeError, ValueError) as exc:
            logger.log_warning(f"Skipping malformed extended platform entry {entry.get('key', '?')}: {exc}")
            continue
        if spec.key in EXCLUDED_PLATFORMS:
            continue
        # CORE always wins: a hand-written spec has an oracle the data file lacks.
        if spec.key in core_keys:
            continue
        out.append(spec)
    return tuple(out)


@lru_cache(maxsize=1)
def get_registry() -> PlatformRegistry:
    """The full catalogue: CORE first, then EXTENDED."""
    return PlatformRegistry(CORE_PLATFORMS + load_extended_specs())


@lru_cache(maxsize=1)
def get_core_registry() -> PlatformRegistry:
    """CORE only — the default sweep."""
    return PlatformRegistry(CORE_PLATFORMS)


def core_keys() -> frozenset[str]:
    """The keys a caller is allowed to pick from. EXTENDED is not selectable."""
    return get_core_registry().keys()


def registry_for_selection(
    *,
    selected: Collection[str] | None,
    include_extended: bool,
) -> PlatformRegistry:
    """The catalogue one session may sweep.

    ``selected`` is the user's CORE pick; ``None`` means "all of CORE", which is
    the historical behaviour. EXTENDED is governed by ``include_extended`` alone —
    the picker never lists the long tail, so filtering it by a CORE selection
    would silently switch it off for anyone who deselected a single platform.
    """
    base = get_registry() if include_extended else get_core_registry()
    if selected is None:
        return base
    keep = frozenset(selected)
    return PlatformRegistry(
        tuple(spec for spec in base.all() if spec.tier is PlatformTier.EXTENDED or spec.key in keep)
    )
