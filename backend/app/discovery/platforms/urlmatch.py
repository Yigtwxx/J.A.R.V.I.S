"""Decide whether a URL is a genuine profile URL, and whose.

This module exists because the old pipeline did:

    re.search(r'(twitter|x)\\.com/([A-Za-z0-9_]+)', url)

on the raw URL string. That matches *inside* ``roblox.com``, ``netflix.com``,
``wix.com``, ``dropbox.com`` and ``xbox.com``, so ``roblox.com/users/123``
produced the bogus profile ``https://x.com/users``, which then passed every
downstream filter.

**A URL is never matched as a string here.** It is parsed, the host is compared
for *equality*, and the path is matched against an anchored pattern. Five
independent rules each kill the bug class on their own:

1. Host equality against a lookup table — never a substring search.
2. Anchored ``^…$`` path patterns.
3. Per-platform reserved-path blocklist (``/about``, ``/explore``, …).
4. A cross-platform stoplist of handles that are never people (``users``, ``null``).
5. Platform charset and length rules baked into the pattern (X handles cannot
   contain ``.``; Instagram cannot exceed 30; GitHub cannot start or end with ``-``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import SplitResult, parse_qs, unquote, urlsplit

# Host -> platform key. Equality only. Every alias a platform serves must be
# listed explicitly; anything absent is simply not a profile URL.
_HOST_TO_PLATFORM: dict[str, str] = {
    "twitter.com": "x",
    "x.com": "x",
    "mobile.twitter.com": "x",
    "nitter.net": "x",
    "instagram.com": "instagram",
    "instagr.am": "instagram",
    "tiktok.com": "tiktok",
    "vm.tiktok.com": "tiktok",
    "linkedin.com": "linkedin",
    "github.com": "github",
    "gist.github.com": "github",
    "reddit.com": "reddit",
    "old.reddit.com": "reddit",
    "np.reddit.com": "reddit",
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "facebook.com": "facebook",
    "fb.com": "facebook",
    "fb.me": "facebook",
    "threads.net": "threads",
    "threads.com": "threads",
    "pinterest.com": "pinterest",
    "pin.it": "pinterest",
    "open.spotify.com": "spotify",
    "steamcommunity.com": "steam",
    "snapchat.com": "snapchat",
    "bsky.app": "bluesky",
    "t.me": "telegram",
    "telegram.me": "telegram",
    "twitch.tv": "twitch",
    "behance.net": "behance",
    "dribbble.com": "dribbble",
    "deviantart.com": "deviantart",
    "vimeo.com": "vimeo",
    "gitlab.com": "gitlab",
    "stackoverflow.com": "stackoverflow",
    "keybase.io": "keybase",
    "letterboxd.com": "letterboxd",
    "goodreads.com": "goodreads",
    "strava.com": "strava",
    "vk.com": "vk",
    "mastodon.social": "mastodon",
    "flickr.com": "flickr",
    "about.me": "aboutme",
    "linktr.ee": "linktree",
    "patreon.com": "patreon",
    "ko-fi.com": "kofi",
    "tumblr.com": "tumblr",
}

# Country-specific LinkedIn hosts (tr.linkedin.com, de.linkedin.com, …) all serve
# the same profiles, so they are resolved dynamically rather than enumerated.
_DYNAMIC_SUFFIX_HOSTS: dict[str, str] = {
    "linkedin.com": "linkedin",
    "wikipedia.org": "wikipedia",
}

# Anchored path patterns. Order matters only in that the first match wins.
_PATH_PATTERNS: dict[str, tuple[tuple[re.Pattern[str], str | None], ...]] = {
    "x": ((re.compile(r"^/(?P<u>[A-Za-z0-9_]{1,15})/?$"), None),),
    "instagram": ((re.compile(r"^/(?P<u>[A-Za-z0-9._]{1,30})/?$"), None),),
    "tiktok": ((re.compile(r"^/@(?P<u>[A-Za-z0-9._]{2,24})/?$"), None),),
    "linkedin": (
        (re.compile(r"^/in/(?P<u>[\w\-%.À-ɏ]{3,120})/?$"), None),
        (re.compile(r"^/company/(?P<u>[\w\-%.]{2,120})/?$"), "company"),
        (re.compile(r"^/school/(?P<u>[\w\-%.]{2,120})/?$"), "school"),
    ),
    # GitHub: 1-39 chars, alphanumeric or single hyphens, never leading/trailing.
    "github": ((re.compile(r"^/(?P<u>[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38})/?$"), None),),
    "reddit": ((re.compile(r"^/(?:user|u)/(?P<u>[A-Za-z0-9_\-]{3,20})/?$"), None),),
    "youtube": (
        (re.compile(r"^/@(?P<u>[A-Za-z0-9._\-]{3,30})/?$"), None),
        (re.compile(r"^/(?:c|user)/(?P<u>[A-Za-z0-9._\-]{1,64})/?$"), None),
        (re.compile(r"^/channel/(?P<u>UC[A-Za-z0-9_\-]{22})/?$"), "channel"),
    ),
    # `profile.php` must be tried BEFORE the generic vanity-name pattern, which
    # would otherwise swallow it and yield the "username" `profile.php`.
    "facebook": (
        (re.compile(r"^/profile\.php$"), "query_id"),
        (re.compile(r"^/people/[^/]+/(?P<u>\d{5,25})/?$"), "numeric"),
        (re.compile(r"^/(?P<u>[A-Za-z0-9.]{5,60})/?$"), None),
    ),
    "threads": ((re.compile(r"^/@(?P<u>[A-Za-z0-9._]{1,30})/?$"), None),),
    "pinterest": ((re.compile(r"^/(?P<u>[A-Za-z0-9_]{3,30})/?$"), None),),
    "spotify": (
        (re.compile(r"^/user/(?P<u>[A-Za-z0-9]{1,64})/?$"), None),
        (re.compile(r"^/artist/(?P<u>[A-Za-z0-9]{22})/?$"), "artist"),
    ),
    "steam": ((re.compile(r"^/(?:id|profiles)/(?P<u>[A-Za-z0-9_\-]{2,64})/?$"), None),),
    "snapchat": ((re.compile(r"^/add/(?P<u>[A-Za-z0-9._\-]{3,15})/?$"), None),),
    "bluesky": ((re.compile(r"^/profile/(?P<u>[A-Za-z0-9._:\-]{3,253})/?$"), None),),
    "telegram": ((re.compile(r"^/(?P<u>[A-Za-z][A-Za-z0-9_]{4,31})/?$"), None),),
    "twitch": ((re.compile(r"^/(?P<u>[A-Za-z0-9_]{4,25})/?$"), None),),
    "behance": ((re.compile(r"^/(?P<u>[A-Za-z0-9_\-]{3,40})/?$"), None),),
    "dribbble": ((re.compile(r"^/(?P<u>[A-Za-z0-9_\-]{3,40})/?$"), None),),
    "deviantart": ((re.compile(r"^/(?P<u>[A-Za-z0-9_\-]{3,20})/?$"), None),),
    "vimeo": ((re.compile(r"^/(?P<u>[A-Za-z0-9_]{3,32})/?$"), None),),
    "gitlab": ((re.compile(r"^/(?P<u>[A-Za-z0-9][A-Za-z0-9._\-]{1,254})/?$"), None),),
    "stackoverflow": ((re.compile(r"^/users/(?P<u>\d{1,12})(?:/[^/]*)?/?$"), None),),
    "keybase": ((re.compile(r"^/(?P<u>[A-Za-z0-9_]{2,16})/?$"), None),),
    "letterboxd": ((re.compile(r"^/(?P<u>[A-Za-z0-9_]{2,15})/?$"), None),),
    "goodreads": ((re.compile(r"^/user/show/(?P<u>\d+[A-Za-z0-9\-]*)/?$"), None),),
    "strava": ((re.compile(r"^/athletes/(?P<u>[A-Za-z0-9_\-]{1,40})/?$"), None),),
    "vk": ((re.compile(r"^/(?P<u>[A-Za-z0-9_.]{3,32})/?$"), None),),
    "mastodon": ((re.compile(r"^/@(?P<u>[A-Za-z0-9_]{1,30})/?$"), None),),
    "flickr": ((re.compile(r"^/(?:photos|people)/(?P<u>[A-Za-z0-9@_\-]{2,64})/?$"), None),),
    "aboutme": ((re.compile(r"^/(?P<u>[A-Za-z0-9_\-.]{2,40})/?$"), None),),
    "linktree": ((re.compile(r"^/(?P<u>[A-Za-z0-9_.]{2,40})/?$"), None),),
    "patreon": ((re.compile(r"^/(?P<u>[A-Za-z0-9_\-]{3,40})/?$"), None),),
    "kofi": ((re.compile(r"^/(?P<u>[A-Za-z0-9_]{3,40})/?$"), None),),
    "tumblr": ((re.compile(r"^/(?:blog/view/)?(?P<u>[A-Za-z0-9\-]{1,32})/?$"), None),),
    "wikipedia": ((re.compile(r"^/wiki/User:(?P<u>[^/]{1,80})/?$"), None),),
}

# Canonical profile URL templates. `{u}` is the username.
_CANONICAL: dict[str, str] = {
    "x": "https://x.com/{u}",
    "instagram": "https://www.instagram.com/{u}/",
    "tiktok": "https://www.tiktok.com/@{u}",
    "linkedin": "https://www.linkedin.com/in/{u}/",
    "github": "https://github.com/{u}",
    "reddit": "https://www.reddit.com/user/{u}/",
    "youtube": "https://www.youtube.com/@{u}",
    "facebook": "https://www.facebook.com/{u}",
    "threads": "https://www.threads.net/@{u}",
    "pinterest": "https://www.pinterest.com/{u}/",
    "spotify": "https://open.spotify.com/user/{u}",
    "steam": "https://steamcommunity.com/id/{u}",
    "snapchat": "https://www.snapchat.com/add/{u}",
    "bluesky": "https://bsky.app/profile/{u}",
    "telegram": "https://t.me/{u}",
    "twitch": "https://www.twitch.tv/{u}",
    "behance": "https://www.behance.net/{u}",
    "dribbble": "https://dribbble.com/{u}",
    "deviantart": "https://www.deviantart.com/{u}",
    "vimeo": "https://vimeo.com/{u}",
    "gitlab": "https://gitlab.com/{u}",
    "stackoverflow": "https://stackoverflow.com/users/{u}",
    "keybase": "https://keybase.io/{u}",
    "letterboxd": "https://letterboxd.com/{u}/",
    "goodreads": "https://www.goodreads.com/user/show/{u}",
    "strava": "https://www.strava.com/athletes/{u}",
    "vk": "https://vk.com/{u}",
    "mastodon": "https://mastodon.social/@{u}",
    "flickr": "https://www.flickr.com/people/{u}",
    "aboutme": "https://about.me/{u}",
    "linktree": "https://linktr.ee/{u}",
    "patreon": "https://www.patreon.com/{u}",
    "kofi": "https://ko-fi.com/{u}",
    "tumblr": "https://{u}.tumblr.com",
    "wikipedia": "https://en.wikipedia.org/wiki/User:{u}",
}

_CANONICAL_VARIANTS: dict[tuple[str, str], str] = {
    ("linkedin", "company"): "https://www.linkedin.com/company/{u}/",
    ("linkedin", "school"): "https://www.linkedin.com/school/{u}/",
    ("youtube", "channel"): "https://www.youtube.com/channel/{u}",
    ("spotify", "artist"): "https://open.spotify.com/artist/{u}",
    ("facebook", "numeric"): "https://www.facebook.com/profile.php?id={u}",
    ("facebook", "query_id"): "https://www.facebook.com/profile.php?id={u}",
}

# Per-platform path segments that are site chrome, not people.
_RESERVED: dict[str, frozenset[str]] = {
    "x": frozenset(
        {
            "home",
            "search",
            "explore",
            "i",
            "intent",
            "settings",
            "login",
            "signup",
            "share",
            "notifications",
            "messages",
            "compose",
            "hashtag",
            "users",
            "user",
            "about",
            "tos",
            "privacy",
            "download",
            "account",
            "session",
            "logout",
            "oauth",
            "widgets",
            "status",
        }
    ),
    "instagram": frozenset(
        {
            "p",
            "reel",
            "reels",
            "tv",
            "explore",
            "stories",
            "accounts",
            "directory",
            "about",
            "legal",
            "developer",
            "challenge",
            "emails",
            "web",
            "graphql",
            "api",
            "sessions",
            "privacy",
            "terms",
            "press",
            "topics",
            "locations",
            "create",
            "direct",
            "your_activity",
        }
    ),
    "tiktok": frozenset({"foryou", "following", "explore", "live", "upload", "tag", "music", "discover", "search"}),
    "linkedin": frozenset({"feed", "jobs", "learning", "sales", "help", "legal", "signup", "login", "pub", "posts"}),
    "github": frozenset(
        {
            "about",
            "pricing",
            "features",
            "explore",
            "topics",
            "trending",
            "collections",
            "events",
            "marketplace",
            "sponsors",
            "settings",
            "notifications",
            "issues",
            "pulls",
            "login",
            "join",
            "new",
            "orgs",
            "search",
            "apps",
            "codespaces",
            "security",
            "readme",
            "site",
            "contact",
            "enterprise",
            "team",
            "customer-stories",
            "nonprofit",
            "sitemap",
            "logout",
        }
    ),
    "reddit": frozenset({"me", "reddit", "all", "popular", "random", "settings"}),
    "youtube": frozenset({"watch", "feed", "results", "playlist", "shorts", "about", "account", "premium", "gaming"}),
    "facebook": frozenset(
        {
            "profile",
            "pages",
            "groups",
            "events",
            "marketplace",
            "watch",
            "gaming",
            "settings",
            "help",
            "policies",
            "login",
            "signup",
            "sharer",
            "share",
            "photo",
            "story",
            "notes",
            "public",
            "search",
            "messages",
            "bookmarks",
            "legal",
            "privacy",
            "business",
            "careers",
        }
    ),
    "threads": frozenset({"search", "activity", "settings", "about", "login"}),
    "pinterest": frozenset({"search", "ideas", "today", "pin", "settings", "login", "about", "business", "categories"}),
    "spotify": frozenset({"track", "album", "playlist", "show", "episode", "search", "collection", "genre"}),
    "steam": frozenset({"app", "games", "market", "workshop", "groups", "discussions", "login", "search"}),
    "snapchat": frozenset({"discover", "lens", "spotlight", "download", "explore", "login"}),
    "bluesky": frozenset({"search", "notifications", "settings", "feeds", "lists"}),
    "telegram": frozenset({"joinchat", "share", "iv", "addstickers", "proxy", "socks", "setlanguage", "s"}),
    "twitch": frozenset({"directory", "videos", "settings", "downloads", "p", "team", "subscriptions", "search"}),
    "behance": frozenset({"gallery", "search", "joblist", "assets", "live", "adobetalent", "onboarding", "for_you"}),
    "dribbble": frozenset({"shots", "designers", "jobs", "tags", "search", "signup", "session", "about", "stories"}),
    "deviantart": frozenset({"search", "topic", "shop", "about", "join", "daily-deviations", "groups", "forum"}),
    "vimeo": frozenset(
        {"watch", "upload", "features", "upgrade", "log_in", "join", "search", "categories", "ondemand"}
    ),
    "gitlab": frozenset({"explore", "help", "dashboard", "users", "groups", "projects", "admin", "api", "search"}),
    "vk": frozenset({"feed", "im", "audio", "video", "groups", "login", "search", "help", "about", "away"}),
    "flickr": frozenset({"search", "explore", "groups", "cameras", "commons", "map", "about"}),
    "patreon": frozenset({"home", "explore", "login", "signup", "search", "posts", "about", "join", "create"}),
    "kofi": frozenset({"explore", "login", "signup", "about", "discover", "gold", "manage"}),
    "tumblr": frozenset(
        {"dashboard", "explore", "search", "likes", "following", "settings", "login", "register", "www"}
    ),
    "letterboxd": frozenset({"films", "lists", "members", "journal", "search", "settings", "activity", "pro"}),
    "keybase": frozenset({"docs", "download", "blog", "about", "team", "jobs", "install"}),
    "linktree": frozenset({"login", "signup", "s", "pricing", "discover", "help", "admin"}),
    "aboutme": frozenset({"login", "signup", "explore", "help", "terms", "privacy"}),
}

# Handles that are never a person, on any platform.
_GENERIC_HANDLES: frozenset[str] = frozenset(
    {
        "users",
        "user",
        "share",
        "intent",
        "null",
        "undefined",
        "none",
        "index",
        "home",
        "login",
        "signin",
        "signup",
        "logout",
        "register",
        "about",
        "help",
        "support",
        "terms",
        "privacy",
        "policy",
        "legal",
        "contact",
        "search",
        "explore",
        "settings",
        "account",
        "admin",
        "api",
        "static",
        "assets",
        "img",
        "images",
        "css",
        "js",
        "www",
        "test",
        "example",
        "default",
        "profile",
        "profiles",
        "page",
        "pages",
        "post",
        "posts",
        "feed",
        "error",
        "404",
    }
)


# Corporate and infrastructure domains inside a platform's own family. They host
# no profiles, which is why they are absent from `_HOST_TO_PLATFORM` — and that
# absence is exactly why they used to survive as "outbound links": a logged-out
# Instagram page footers `about.meta.com`, `meta.ai` and a Facebook help article
# on *every* account it serves, so keeping them credits the person with links
# they never published.
_OPERATOR_DOMAINS: frozenset[str] = frozenset(
    {
        "meta.com",
        "meta.ai",
        "metacareers.com",
        "whatsapp.com",
        "messenger.com",
        "oculus.com",
        "cdninstagram.com",
        "fbcdn.net",
        "t.co",
        "twimg.com",
        "bytedance.com",
        "tiktokv.com",
        "redditinc.com",
        "redditstatic.com",
        "licdn.com",
        "githubstatus.com",
        "githubassets.com",
        # open.spotify.com carries the profiles; the bare domain is the company.
        "spotify.com",
        "snap.com",
        "gstatic.com",
    }
)

# Leftmost host labels a platform uses for its own furniture. Curated rather than
# "every subdomain we do not recognise", because `username.deviantart.com` and
# `blog.tumblr.com` are people and a blanket rule would eat them.
_CHROME_SUBDOMAINS: frozenset[str] = frozenset(
    {
        "about",
        "ads",
        "advertising",
        "api",
        "brand",
        "business",
        "careers",
        "cdn",
        "design",
        "developer",
        "developers",
        "docs",
        "download",
        "engineering",
        "help",
        "investor",
        "investors",
        "jobs",
        "l",
        "legal",
        "lm",
        "newsroom",
        "partners",
        "policies",
        "press",
        "privacy",
        "research",
        "security",
        "static",
        "status",
        "support",
        "terms",
        "transparency",
    }
)


@dataclass(frozen=True, slots=True)
class UrlMatch:
    """A URL confirmed to be a profile URL on a known platform."""

    platform: str
    username: str
    canonical_url: str
    variant: str | None = None
    """``company``/``school`` for LinkedIn, ``artist`` for Spotify, ``channel`` for YouTube, …"""

    source_url: str = ""

    @property
    def key(self) -> str:
        """Stable identity used as a candidate key throughout the pipeline."""
        return f"{self.platform}:{self.username.lower()}"


def registrable_host(netloc_or_url: str) -> str:
    """Lowercase host with port and the usual mobile/www prefixes stripped."""
    lowered = netloc_or_url.strip().lower()
    raw = ((urlsplit(lowered).hostname or "") if "://" in lowered else lowered.split("/", 1)[0].split(":", 1)[0]).strip(
        "."
    )
    for prefix in ("www.", "m.", "mobile.", "web.", "amp."):
        if raw.startswith(prefix):
            raw = raw[len(prefix) :]
            break
    return raw


def _normalised_split(url: str) -> SplitResult | None:
    """Parse a URL the way every rule here expects it, or None if it is not one."""
    if not url or not isinstance(url, str):
        return None
    candidate = url.strip()
    if not candidate:
        return None
    if candidate.startswith("//"):
        candidate = "https:" + candidate
    elif "://" not in candidate:
        candidate = "https://" + candidate
    try:
        split = urlsplit(candidate)
    except ValueError:
        return None
    if split.scheme not in ("http", "https"):
        return None
    return split


def _resolve_platform(host: str) -> str | None:
    """Host -> platform key, allowing locale subdomains for the hosts that use them."""
    direct = _HOST_TO_PLATFORM.get(host)
    if direct:
        return direct
    for suffix, platform in _DYNAMIC_SUFFIX_HOSTS.items():
        # `tr.linkedin.com` -> linkedin, but `evil-linkedin.com` must not match.
        if host.endswith("." + suffix):
            label = host[: -(len(suffix) + 1)]
            if label and "." not in label and label.isalnum():
                return platform
    # `<blog>.tumblr.com` is itself the profile URL.
    if host.endswith(".tumblr.com"):
        return "tumblr"
    return None


def match_profile_url(url: str) -> UrlMatch | None:
    """Return a UrlMatch only for a genuine profile URL. None for everything else.

    This is the single gate every discovered URL passes through. If it returns
    None the URL is treated as a plain web source, never as a social profile.
    """
    split = _normalised_split(url)
    if split is None:
        return None

    host = registrable_host(split.netloc)
    if not host:
        return None
    platform = _resolve_platform(host)
    if platform is None:
        return None

    # A tumblr blog is identified by its subdomain, not its path.
    if platform == "tumblr" and host.endswith(".tumblr.com"):
        blog = host[: -len(".tumblr.com")]
        if not blog or blog in _RESERVED.get("tumblr", frozenset()) or blog in _GENERIC_HANDLES:
            return None
        return _build(platform, blog, None, url)

    path = unquote(split.path or "/")
    if not path.startswith("/"):
        path = "/" + path

    for pattern, variant in _PATH_PATTERNS.get(platform, ()):
        match = pattern.match(path)
        if not match:
            continue

        if variant == "query_id":
            # facebook.com/profile.php?id=1234567890
            ids = parse_qs(split.query or "").get("id") or []
            raw_id = ids[0].strip() if ids else ""
            if not raw_id.isdigit() or not (5 <= len(raw_id) <= 25):
                return None
            return _build(platform, raw_id, "numeric", url)

        username = (match.groupdict().get("u") or "").strip()
        if not username:
            return None
        if _is_rejected(platform, username, variant):
            return None
        return _build(platform, username, variant, url)

    return None


# Legacy server scripts that sit at the same path depth as a username. The
# reserved lists hold bare segments, so `login` was blocked while `login.php`
# walked straight through: a live search on 2026-08-29 carried `facebook:login.php`
# and `facebook:r.php` as candidate profiles. No platform issues a handle ending
# in a script suffix, and Facebook ids without a vanity URL arrive as the bare
# number, never as `profile.php`.
_SCRIPT_SUFFIXES: tuple[str, ...] = (".php", ".aspx", ".jsp", ".cgi", ".html", ".htm")


def _is_rejected(platform: str, username: str, variant: str | None) -> bool:
    """Reserved paths, generic handles, and platform charset rules."""
    lowered = username.lower()
    # Numeric ids (Stack Overflow, Facebook, Goodreads) are legitimate handles.
    if lowered.isdigit():
        return False
    if lowered.endswith(_SCRIPT_SUFFIXES):
        return True
    if lowered in _RESERVED.get(platform, frozenset()):
        return True
    if lowered in _GENERIC_HANDLES:
        return True
    # Organisation-ish variants are allowed to be dictionary words.
    if variant in ("company", "school"):
        return False
    return False


def canonical_profile_url(platform: str, username: str, *, variant: str | None = None) -> str:
    """Build the canonical URL for ``platform:username``.

    Falls back to the plain profile template when the variant is unknown, so a new
    variant never produces an empty URL.
    """
    if variant:
        template = _CANONICAL_VARIANTS.get((platform, variant))
        if template:
            return template.format(u=username)
    template = _CANONICAL.get(platform)
    if not template:
        return ""
    return template.format(u=username)


def _build(platform: str, username: str, variant: str | None, source_url: str) -> UrlMatch:
    return UrlMatch(
        platform=platform,
        username=username,
        canonical_url=canonical_profile_url(platform, username, variant=variant),
        variant=variant,
        source_url=source_url,
    )


def platform_for_host(url: str) -> str | None:
    """Which platform owns this URL's host, ignoring the path. None if unknown."""
    if not url:
        return None
    return _resolve_platform(registrable_host(url))


def known_platforms() -> frozenset[str]:
    """Every platform this matcher can recognise."""
    return frozenset(_PATH_PATTERNS)


def is_generic_handle(username: str) -> bool:
    """True for handles that are site chrome rather than a person."""
    return username.strip().lower() in _GENERIC_HANDLES


def _is_operator_host(host: str) -> bool:
    """True for a corporate or infrastructure host in some platform's own family."""
    for domain in _OPERATOR_DOMAINS:
        if host == domain or host.endswith("." + domain):
            return True
    # A host the platform table already answers for is a front door to profiles,
    # not furniture — every alias that serves profiles is listed explicitly.
    if "." not in host or _resolve_platform(host) is not None:
        return False
    label, parent = host.split(".", 1)
    if label not in _CHROME_SUBDOMAINS:
        return False
    return _resolve_platform(parent) is not None or _is_operator_host(parent)


def is_platform_chrome(url: str) -> bool:
    """True when a URL is a platform's own furniture rather than a page about a person.

    Every logged-out Instagram profile carries the same Meta footer, so an
    extractor that keeps any URL it cannot classify records `about.meta.com` as
    something *this person* published — the card lists it under "links from this
    profile" and `scoring.py` reads it as corroboration for whoever the page is
    about. The same six links appear for every account on the site, so they
    corroborate nothing.

    Three shapes are furniture:

    * an operator host — `meta.ai`, `developers.facebook.com` — which serves no
      profiles at all;
    * the bare homepage of a platform we know (`threads.com/`): a root URL names
      the site, never a person;
    * a platform URL whose first path segment is already on that platform's
      reserved list (`facebook.com/help/…`, `instagram.com/p/…`).

    A URL `match_profile_url` accepts is never furniture, so the one real link in
    that footer — the account's own Threads profile — survives.
    """
    split = _normalised_split(url)
    if split is None:
        return False
    host = registrable_host(split.netloc)
    if not host:
        return False
    if match_profile_url(url) is not None:
        return False
    if _is_operator_host(host):
        return True
    platform = _resolve_platform(host)
    if platform is None:
        return False  # an unknown host is a plain web page; keep it
    segment = unquote(split.path or "").strip("/").split("/", 1)[0].lower()
    if not segment:
        return True
    return segment in _RESERVED.get(platform, frozenset()) or segment in _GENERIC_HANDLES
