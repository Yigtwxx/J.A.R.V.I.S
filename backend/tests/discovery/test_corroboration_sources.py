"""Reaching three independent source domains has to be possible.

`require_independent_sources` asks for two distinct sites before a candidate may
be `confirmed` at depth 7-8, and three at 9-10. Nothing in the round could supply
them: profile, bio, avatar, outbound links and the SERP hit are all read off the
candidate's own page and all carry its one domain, so the count was permanently
one and the gate was an unconditional ban rather than a graded requirement.

Two sources can genuinely produce another domain, and both existed in the tree
while nothing constructed them:

* the person's own website listing the account (`sources/website.WebsiteChain`)
* another page carrying the same profile picture (`media/reverse.ReverseImageSearcher`)

`discovery_reverse_image_enabled` even defaulted to True, which made the feature
look switched on while no code read the setting.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Sequence
from typing import Any

from app.discovery.engines.queries import build_query_terms
from app.discovery.evidence.model import make_evidence
from app.discovery.identity.anchor import build_anchor
from app.discovery.loop.round import DiscoveryRound
from app.discovery.loop.state import DiscoveryState, RoundBudget
from app.discovery.matching.candidate import MatchScore, ProfileCandidate
from app.discovery.matching.scoring import require_independent_sources
from app.discovery.media.reverse import ReverseHit
from app.discovery.platforms.extract import ProfileData
from app.discovery.platforms.registry import get_core_registry
from app.discovery.session.bus import SessionEventBus
from app.discovery.sources.website import SiteFindings
from app.discovery.types import (
    EntityType,
    EvidenceKind,
    ExistenceVerdict,
    MatchBand,
    SourceKind,
)

GITHUB_URL = "https://github.com/Yigtwxx"


class _FakeStore:
    async def add_many(self, target_key: str, session_id: str, evidence: list[Any]) -> list[Any]:
        return list(evidence)


class _FakeWebsite:
    """Stands in for a crawl of the subject's own site."""

    def __init__(self, findings: SiteFindings) -> None:
        self._findings = findings
        self.calls: list[str] = []

    async def crawl(self, fetch: Any, url: str, *, name_tokens: Sequence[str] = ()) -> SiteFindings:
        self.calls.append(url)
        return self._findings


class _FakeReverse:
    def __init__(self, hits: Sequence[ReverseHit]) -> None:
        self._hits = list(hits)
        self.calls: list[str] = []

    async def search(self, fetch: Any, image_url: str, *, limit: int = 20, **kwargs: Any) -> list[ReverseHit]:
        self.calls.append(image_url)
        return list(self._hits)


def run(coro: Coroutine[Any, Any, Any]) -> Any:
    return asyncio.run(coro)


def _candidate() -> ProfileCandidate:
    return ProfileCandidate(
        platform="github",
        username="Yigtwxx",
        url=GITHUB_URL,
        verdict=ExistenceVerdict.EXISTS,
        data=ProfileData(
            platform="github",
            username="Yigtwxx",
            url=GITHUB_URL,
            display_name="Yigit Erdogan",
            avatar_url="https://avatars.githubusercontent.com/u/1",
        ),
        score=MatchScore(84, MatchBand.CONFIRMED, ()),
    )


def _state(candidate: ProfileCandidate, *, domain: str = "yigiterdogan.dev") -> DiscoveryState:
    state = DiscoveryState(
        session_id="s1",
        target_key="yigit-erdogan:person",
        entity=EntityType.PERSON,
        terms=build_query_terms("Yigit Erdogan", EntityType.PERSON),
        anchor=build_anchor("Yigit Erdogan", EntityType.PERSON),
        budget=RoundBudget(),
    )
    state.anchor.domain = domain
    state.candidates[candidate.key] = candidate
    state.evidence.append(
        make_evidence(
            EvidenceKind.PROFILE,
            candidate.key,
            candidate.url,
            source_url=candidate.url,
            source_kind=SourceKind.PROFILE_PAGE,
            extractor="test",
            confidence=0.9,
            platform="github",
        )
    )
    return state


def _round(*, website: Any = None, reverse: Any = None) -> DiscoveryRound:
    return DiscoveryRound(
        fetch=None,
        engines=None,
        registry=get_core_registry(),
        store=_FakeStore(),
        bus=SessionEventBus("s1"),
        avatars=None,
        website=website,
        reverse=reverse,
    )


def test_a_candidate_read_only_from_its_own_page_reaches_one_domain() -> None:
    """The starting point, pinned: this is the state that made depth 7+ impossible."""
    candidate = _candidate()
    state = _state(candidate)

    domains = DiscoveryRound._source_domains_by_candidate(state)

    assert domains[candidate.key] == {"github.com"}


def test_the_personal_site_adds_the_second_domain() -> None:
    candidate = _candidate()
    state = _state(candidate)
    website = _FakeWebsite(SiteFindings(url="https://yigiterdogan.dev/about", rel_me_urls=[GITHUB_URL]))

    run(_round(website=website)._corroborate(state))
    domains = DiscoveryRound._source_domains_by_candidate(state)

    assert website.calls == ["https://yigiterdogan.dev"], f"the anchor domain must be crawled, got {website.calls}"
    assert "yigiterdogan.dev" in domains[candidate.key], (
        f"the subject's own site vouching for the account is a second source, got {domains[candidate.key]}"
    )


def test_reverse_image_adds_a_third_domain_and_three_becomes_reachable() -> None:
    """The question this module exists to answer: can depth 9-10 ever confirm?"""
    candidate = _candidate()
    state = _state(candidate)
    website = _FakeWebsite(SiteFindings(url="https://yigiterdogan.dev/about", rel_me_urls=[GITHUB_URL]))
    reverse = _FakeReverse(
        [ReverseHit(url="https://conference.example/speakers/yigit", title="Speaker", engine="yandex")]
    )

    run(_round(website=website, reverse=reverse)._corroborate(state))
    domains = DiscoveryRound._source_domains_by_candidate(state)

    assert len(domains[candidate.key]) >= 3, (
        f"three independent sites must be reachable, got {sorted(domains[candidate.key])}"
    )
    held = require_independent_sources(candidate.score, source_domains=len(domains[candidate.key]), required=3)
    assert held.band is MatchBand.CONFIRMED, f"the depth 9-10 validation pass must now be satisfiable, got {held.band}"


def test_reverse_image_is_not_spent_on_a_candidate_nobody_believes_in() -> None:
    """A Yandex lookup runs a browser; it is not spent on a `weak` guess."""
    candidate = _candidate()
    candidate.score = MatchScore(25, MatchBand.WEAK, ())
    state = _state(candidate, domain="")
    reverse = _FakeReverse([])

    run(_round(reverse=reverse)._corroborate(state))

    assert reverse.calls == [], "a candidate below `possible` must not cost a browser page"


def test_the_personal_site_is_crawled_once_per_search() -> None:
    candidate = _candidate()
    state = _state(candidate)
    website = _FakeWebsite(SiteFindings(url="https://yigiterdogan.dev/about", rel_me_urls=[GITHUB_URL]))
    round_runner = _round(website=website)

    run(round_runner._corroborate(state))
    run(round_runner._corroborate(state))

    assert len(website.calls) == 1, f"a second round must not re-crawl the same site, got {website.calls}"


def _github_data(display_name: str, blog: str) -> ProfileData:
    return ProfileData(
        platform="github",
        username="Yigtwxx",
        url=GITHUB_URL,
        display_name=display_name,
        outbound_links=[blog],
        extractor="api:github",
    )


def test_the_anchor_adopts_the_website_a_matching_github_profile_declares() -> None:
    """`anchor.domain` was never populated on any search, so nothing downstream ran."""
    candidate = _candidate()
    state = _state(candidate, domain="")

    DiscoveryRound._adopt_personal_site(state, candidate, _github_data("Yigit Erdogan", "https://yigiterdogan.dev"))

    assert state.anchor.domain == "yigiterdogan.dev", (
        f"the declared site must become the anchor domain, got {state.anchor.domain!r}"
    )


def test_a_namesakes_website_is_not_adopted() -> None:
    """A stranger's GitHub would otherwise send the crawler to a stranger's site."""
    candidate = _candidate()
    state = _state(candidate, domain="")

    DiscoveryRound._adopt_personal_site(state, candidate, _github_data("Recep Tayyip", "https://someone-else.example"))

    assert state.anchor.domain == "", (
        f"a name that does not match must not steer the crawl, got {state.anchor.domain!r}"
    )


def test_an_existing_anchor_domain_is_not_overwritten() -> None:
    candidate = _candidate()
    state = _state(candidate, domain="already.example")

    DiscoveryRound._adopt_personal_site(state, candidate, _github_data("Yigit Erdogan", "https://yigiterdogan.dev"))

    assert state.anchor.domain == "already.example", "the first, stronger claim must win"


def test_a_shared_surname_is_not_enough_to_adopt_a_website() -> None:
    """The namesake trap, caught in a live run on 2026-08-29.

    The first guard here required the GitHub profile's display name to share one
    token with the target. A surname is one token, so a search for "Yigit
    Erdogan" adopted `engin-erdogan.com` from a stranger's GitHub profile and then
    awarded that stranger `personal_site_backlink` (+25). The scorer was already
    saying `name_conflict` (-16) about the very same candidate.

    `names_contradict` is the test that separates them: two names that each carry
    a distinctive token the other lacks are two people, however much surname they
    share.
    """
    candidate = _candidate()
    state = _state(candidate, domain="")

    DiscoveryRound._adopt_personal_site(state, candidate, _github_data("Engin Erdogan", "https://engin-erdogan.com"))

    assert state.anchor.domain == "", (
        f"a namesake's website must not become the target's anchor, got {state.anchor.domain!r}"
    )


def test_a_fuller_form_of_the_same_name_still_adopts() -> None:
    """One person written two ways is not a contradiction."""
    candidate = _candidate()
    state = _state(candidate, domain="")

    DiscoveryRound._adopt_personal_site(
        state, candidate, _github_data("Yigit Erdogan (yigtwxx)", "https://yigiterdogan.dev")
    )

    assert state.anchor.domain == "yigiterdogan.dev", (
        f"a subset of the same name must still be accepted, got {state.anchor.domain!r}"
    )
