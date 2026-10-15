"""Live block-rate probe for the fetch layer.

Answers one question with numbers instead of adjectives: *which hosts actually
refuse us from this machine, on this IP, right now?* Run it before and after a
change to the fetch layer and compare the tables.

It deliberately probes a handful of endpoints rather than running full searches:
a search is dominated by pipeline logic, and what is being measured here is the
transport. Every handle below belongs to a well-known public institution or
project, so nothing here profiles a private individual.

Pass ``--twice`` to measure carry-over: the second pass runs against the same
process, so it benefits from the cookies and browser profile the first earned.
That delta is the whole point of the cookie vault.

Usage (from ``backend/``):
    PYTHONIOENCODING=utf-8 ./venv/Scripts/python.exe scripts/verify_fetch_hardening.py
    PYTHONIOENCODING=utf-8 ./venv/Scripts/python.exe scripts/verify_fetch_hardening.py --twice --no-stealth
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.discovery.dependencies import (  # noqa: E402
    get_browser_profile_pool,
    get_cookie_vault,
    get_domain_rate_limiter,
)
from app.discovery.fetch.session import FetchSession  # noqa: E402
from app.discovery.types import FetchStatus, FetchTier  # noqa: E402


@dataclass(frozen=True, slots=True)
class Probe:
    label: str
    url: str
    tier: FetchTier = FetchTier.HTTP
    escalate: bool = False
    note: str = ""


# Existing public accounts. A NOT_FOUND here means the route is broken, not that
# the account is absent — which is exactly the distinction the pipeline defends.
PROBES: tuple[Probe, ...] = (
    # --- routes the pipeline uses today -----------------------------------
    Probe("reddit/about.json", "https://www.reddit.com/user/spez/about.json"),
    Probe("github/api", "https://api.github.com/users/torvalds"),
    Probe("bluesky/xrpc", "https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile?actor=bsky.app"),
    Probe("x/oembed", "https://publish.twitter.com/oembed?url=https://twitter.com/nasa"),
    Probe("steam/xml", "https://steamcommunity.com/id/gaben?xml=1"),
    Probe("telegram/page", "https://t.me/telegram"),
    Probe("instagram/page", "https://www.instagram.com/nasa/", FetchTier.HTTP, True, "stealth-tier platform"),
    Probe("tiktok/page", "https://www.tiktok.com/@nasa", FetchTier.HTTP, True, "stealth-tier platform"),
    Probe("linkedin/page", "https://www.linkedin.com/in/williamhgates/", FetchTier.HTTP, True, "expect 999"),
    # --- alternate routes the ladder now uses ------------------------------
    Probe("reddit/old.about.json", "https://old.reddit.com/user/spez/about.json", note="rejected: also 403"),
    Probe("reddit/.rss", "https://www.reddit.com/user/spez/.rss", note="wired fallback oracle"),
    Probe("tiktok/embed (oracle)", "https://www.tiktok.com/embed/@nasa", note="wired oracle"),
    Probe("tiktok/embed 404 case", "https://www.tiktok.com/embed/@zzq9xnope7781", note="expect 400 = absent"),
    Probe("threads.com page", "https://www.threads.com/@zuck", note="login wall at every tier"),
    Probe(
        "youtube/oembed",
        "https://www.youtube.com/oembed?url=https://www.youtube.com/@NASA&format=json",
        note="rejected: 404 for @handle URLs",
    ),
    # --- search engines ---------------------------------------------------
    Probe("ddg/html", "https://html.duckduckgo.com/html/?q=nasa"),
    Probe("mojeek", "https://www.mojeek.com/search?q=nasa"),
    Probe("brave", "https://search.brave.com/search?q=nasa"),
)


def verdict(status: FetchStatus) -> str:
    return {
        FetchStatus.OK: "OK     ",
        FetchStatus.BLOCKED: "BLOCKED",
        FetchStatus.NOT_FOUND: "404    ",
        FetchStatus.TIMEOUT: "TIMEOUT",
        FetchStatus.ERROR: "ERROR  ",
    }[status]


async def probe_all(fetch: FetchSession, pass_no: int) -> tuple[int, int]:
    print(f"\n{'=' * 96}\nPASS {pass_no}\n{'=' * 96}")
    print(f"{'probe':<26} {'status':<8} {'code':<5} {'tier':<8} {'ms':>6}  {'bytes':>7}  signal / note")
    print("-" * 96)

    blocked = 0
    for probe in PROBES:
        result = await fetch.get(
            probe.url,
            tier=probe.tier,
            escalate=probe.escalate,
            min_html_bytes=0,
            use_cache=False,
        )
        if result.status is FetchStatus.BLOCKED:
            blocked += 1
        detail = result.block_signal or probe.note or ""
        if result.error:
            detail = f"{detail} {result.error}".strip()[:34]
        print(
            f"{probe.label:<26} {verdict(result.status)} "
            f"{str(result.http_status or '-'):<5} {str(result.tier):<8} "
            f"{result.elapsed_ms:>6}  {result.html_len:>7}  {detail[:34]}"
        )
    return blocked, len(PROBES)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--twice", action="store_true", help="second pass, to measure cookie/profile carry-over")
    parser.add_argument("--no-stealth", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    stealth = settings.discovery_stealth_enabled and not args.no_stealth

    print("fetch-layer configuration")
    print(f"  stealth tier        : {stealth}")
    print(f"  cookie persistence  : {settings.discovery_cookie_persistence}")
    print(f"  browser profiles    : {settings.discovery_browser_profile_persist}")
    print(f"  real chrome         : {settings.discovery_real_chrome}")
    print(f"  hide canvas         : {settings.discovery_hide_canvas}")
    print(f"  rate jitter         : {settings.discovery_rate_jitter}")
    print(f"  adaptive backoff    : {settings.discovery_adaptive_backoff}")

    vault = get_cookie_vault()
    totals: list[tuple[int, int]] = []

    for pass_no in range(1, 3 if args.twice else 2):
        async with FetchSession(
            rate_limiter=get_domain_rate_limiter(),
            stealth_enabled=stealth,
            cookies=vault,
            profiles=get_browser_profile_pool(),
            real_chrome=settings.discovery_real_chrome,
            hide_canvas=settings.discovery_hide_canvas,
        ) as fetch:
            totals.append(await probe_all(fetch, pass_no))
            print(f"\nfetch stats: {fetch.stats.as_dict()}")
            if fetch.stealth_unavailable_reason:
                print(f"stealth unavailable: {fetch.stealth_unavailable_reason}")

    print(f"\n{'=' * 96}")
    for index, (blocked, total) in enumerate(totals, start=1):
        print(f"PASS {index}: {blocked}/{total} blocked ({100 * blocked / total:.0f}%)")
    print(f"cookie vault: {vault.snapshot()}")
    print(f"rate limiter: {get_domain_rate_limiter().snapshot()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
