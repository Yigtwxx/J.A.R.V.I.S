"""Per-domain outbound rate limiting.

Rate limits belong to the remote host, not to our search session, so this object
is a process-wide singleton: two concurrent searches that both want Instagram
must share one bucket, otherwise the limit is meaningless.

Keyed on the *registrable* domain so ``www.instagram.com``, ``m.instagram.com``
and ``instagram.com`` all queue behind the same token.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

# Multi-label public suffixes we care about. Anything not listed collapses to the
# last two labels, which is correct for every domain this pipeline touches.
_MULTI_LABEL_SUFFIXES: frozenset[str] = frozenset(
    {
        "co.uk",
        "org.uk",
        "ac.uk",
        "com.tr",
        "net.tr",
        "org.tr",
        "edu.tr",
        "gov.tr",
        "com.au",
        "com.br",
        "co.jp",
        "co.kr",
        "co.in",
        "com.mx",
    }
)


def registrable_domain(url_or_host: str) -> str:
    """Reduce a URL or host to the domain that owns the rate limit.

    ``https://www.instagram.com/foo`` -> ``instagram.com``
    ``api.github.com``               -> ``github.com``
    ``foo.tumblr.com``               -> ``tumblr.com``
    """
    lowered = url_or_host.strip().lower()
    raw = (urlsplit(lowered).hostname or "") if "://" in lowered else lowered.split("/", 1)[0].split(":", 1)[0]
    if not raw:
        return ""

    labels = raw.strip(".").split(".")
    if len(labels) <= 2:
        return ".".join(labels)
    if ".".join(labels[-2:]) in _MULTI_LABEL_SUFFIXES and len(labels) >= 3:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


@dataclass(frozen=True, slots=True)
class RateRule:
    """How often we may hit one domain."""

    min_interval_s: float
    burst: int = 1
    """How many requests may go out back-to-back before the interval applies."""


@dataclass(slots=True)
class DomainState:
    """Mutable per-domain bookkeeping. Exposed read-only via ``snapshot``."""

    tokens: float = 0.0
    last_refill: float = 0.0
    penalty_until: float = 0.0
    requests: int = 0
    waited_s: float = 0.0
    slowdown: float = 1.0
    """AIMD multiplier on the configured interval. 1.0 = the host is happy with us."""

    blocks: int = 0
    last_blocked: float = 0.0


# A host that refuses us is telling us our cadence is wrong. Back off fast and
# earn the speed back slowly: a doubled interval costs seconds, while a soft-ban
# on the only IP we have costs every future search.
_BLOCK_MULTIPLIER = 2.0
_MAX_SLOWDOWN = 8.0
_RECOVERY_STEP = 0.25

# Recovery cannot depend on success alone. A host that blocks *everything* never
# produces the success that would unwind its own penalty, so LinkedIn would climb
# to the 8x ceiling and stay there for the life of the process — this limiter is
# a singleton that is never rebuilt (app/discovery/dependencies.py). Time decay is
# what keeps a permanent refusal from becoming a permanent self-imposed stall.
_DECAY_AFTER_S = 600.0
_DECAY_STEP = 0.5


# Tuned from observed behaviour, not guesses: search engines tolerate a few
# requests per minute; LinkedIn soft-bans an IP that hammers it, and a soft-banned
# residential IP degrades every future search, so it gets the harshest rule.
DEFAULT_OVERRIDES: dict[str, RateRule] = {
    "google.com": RateRule(8.0),
    "startpage.com": RateRule(6.0),
    "duckduckgo.com": RateRule(4.0),
    "bing.com": RateRule(3.0),
    "brave.com": RateRule(3.0),
    "mojeek.com": RateRule(3.0),
    "yandex.com": RateRule(8.0),
    "tineye.com": RateRule(6.0),
    "linkedin.com": RateRule(10.0, burst=1),
    "instagram.com": RateRule(6.0),
    "tiktok.com": RateRule(6.0),
    "facebook.com": RateRule(6.0),
    "threads.net": RateRule(5.0),
    "api.github.com": RateRule(0.2, burst=5),
    "github.com": RateRule(1.0, burst=3),
    "reddit.com": RateRule(2.0),
    "web.archive.org": RateRule(1.5),
    "archive.org": RateRule(1.5),
}

DEFAULT_RULE = RateRule(2.0, burst=2)


class DomainRateLimiter:
    """Token-bucket limiter keyed on registrable domain.

    ``acquire`` is the only thing callers need; it sleeps as long as necessary and
    returns. It never raises and never gives up, because "we hit the rate limit"
    must not become "the platform returned nothing".
    """

    def __init__(
        self,
        default: RateRule = DEFAULT_RULE,
        overrides: Mapping[str, RateRule] | None = None,
        *,
        jitter: float = 0.0,
        adaptive: bool = True,
        decay_after_s: float = _DECAY_AFTER_S,
    ) -> None:
        self._decay_after = max(1.0, decay_after_s)
        self._default = default
        self._overrides: dict[str, RateRule] = dict(DEFAULT_OVERRIDES)
        if overrides:
            self._overrides.update(overrides)
        self._state: dict[str, DomainState] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._jitter = min(0.9, max(0.0, jitter))
        self._adaptive = adaptive

    def rule_for(self, domain: str) -> RateRule:
        """Exact-match override first, then the registrable domain, then the default."""
        return self._overrides.get(domain, self._default)

    def bucket_key(self, url: str) -> str:
        """The domain whose bucket ``url`` belongs to.

        An override may be registered under a full host (``api.github.com``) that the
        registrable-domain reduction would collapse (``github.com``). Every method
        that touches a bucket must resolve the key the *same* way — when ``acquire``
        used the host and ``penalize`` used the registrable domain, a ``Retry-After``
        from ``api.github.com`` was written to a bucket nobody ever read.
        """
        host = (urlsplit(url).hostname or url).lower() if "://" in url else url.lower()
        return host if host in self._overrides else registrable_domain(url)

    def _lock(self, domain: str) -> asyncio.Lock:
        lock = self._locks.get(domain)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[domain] = lock
        return lock

    def _jittered(self, delay: float) -> float:
        """Spread a delay so our cadence is not machine-perfect.

        Exactly periodic requests are themselves a bot signal: no human-driven
        client hits a host every 6.000 s. Never returns a shorter-than-configured
        wait on average, and never a negative one.
        """
        if delay <= 0 or self._jitter <= 0:
            return max(0.0, delay)
        return max(0.0, delay * random.uniform(1.0 - self._jitter, 1.0 + self._jitter))

    def _interval_for(self, domain: str, rule: RateRule) -> float:
        """The configured interval scaled by whatever this host has taught us."""
        if not self._adaptive:
            return rule.min_interval_s
        state = self._state.get(domain)
        if state is None:
            return rule.min_interval_s
        self._decay(state)
        return rule.min_interval_s * state.slowdown

    def _decay(self, state: DomainState) -> None:
        """Let a penalty lapse when the last refusal is old enough."""
        if state.slowdown <= 1.0 or not state.last_blocked:
            return
        elapsed = time.monotonic() - state.last_blocked
        if elapsed < self._decay_after:
            return
        steps = int(elapsed // self._decay_after)
        state.slowdown = max(1.0, state.slowdown - _DECAY_STEP * steps)
        state.last_blocked = time.monotonic()

    async def acquire(self, url: str) -> float:
        """Block until a request to ``url`` is allowed. Returns seconds waited."""
        domain = self.bucket_key(url)
        if not domain:
            return 0.0

        rule = self.rule_for(domain)
        async with self._lock(domain):
            state = self._state.setdefault(domain, DomainState(tokens=float(rule.burst), last_refill=time.monotonic()))
            waited = 0.0

            while True:
                now = time.monotonic()

                # Honour an explicit Retry-After penalty before anything else. It is
                # server-mandated, so it is never jittered *down*.
                if state.penalty_until > now:
                    delay = state.penalty_until - now
                    await asyncio.sleep(delay)
                    waited += delay
                    continue

                interval = self._interval_for(domain, rule)
                elapsed = now - state.last_refill
                if elapsed > 0 and interval > 0:
                    state.tokens = min(float(rule.burst), state.tokens + elapsed / interval)
                    state.last_refill = now

                if state.tokens >= 1.0 or interval <= 0:
                    state.tokens = max(0.0, state.tokens - 1.0)
                    state.requests += 1
                    state.waited_s += waited
                    return waited

                delay = self._jittered((1.0 - state.tokens) * interval)
                await asyncio.sleep(delay)
                waited += delay

    def penalize(self, url: str, seconds: float) -> None:
        """Record a server-mandated cooldown (``Retry-After``) for this domain."""
        domain = self.bucket_key(url)
        if not domain or seconds <= 0:
            return
        state = self._state.setdefault(domain, DomainState())
        state.penalty_until = max(state.penalty_until, time.monotonic() + seconds)

    def note_blocked(self, url: str) -> None:
        """This host refused us: widen its interval for the rest of the process.

        ``Retry-After`` is the polite case and is handled by ``penalize``. Most
        refusals carry no such header, and before this the pipeline kept knocking
        at exactly the cadence that had just been rejected.
        """
        if not self._adaptive:
            return
        domain = self.bucket_key(url)
        if not domain:
            return
        state = self._state.setdefault(domain, DomainState())
        state.blocks += 1
        state.last_blocked = time.monotonic()
        state.slowdown = min(_MAX_SLOWDOWN, max(1.0, state.slowdown) * _BLOCK_MULTIPLIER)

    def note_ok(self, url: str) -> None:
        """This host served us: earn back a little speed, additively."""
        if not self._adaptive:
            return
        domain = self.bucket_key(url)
        if not domain:
            return
        state = self._state.get(domain)
        if state is None or state.slowdown <= 1.0:
            return
        state.slowdown = max(1.0, state.slowdown - _RECOVERY_STEP)

    def snapshot(self) -> dict[str, dict[str, float]]:
        """Diagnostic view: requests made and seconds spent waiting, per domain."""
        now = time.monotonic()
        return {
            domain: {
                "requests": float(state.requests),
                "waited_s": round(state.waited_s, 2),
                "penalty_remaining_s": round(max(0.0, state.penalty_until - now), 2),
                "slowdown": round(state.slowdown, 2),
                "blocks": float(state.blocks),
            }
            for domain, state in sorted(self._state.items())
        }
