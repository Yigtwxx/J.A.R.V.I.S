"""Contacts become evidence like anything else, or they do not exist.

`EvidenceKind.EMAIL` and `EvidenceKind.PHONE` were declared, grounded, graphed,
queried and expanded on — and never once produced. Four consumers agreed the
feature existed. These tests pin the producers, the provenance every hit has to
carry, and the two places where a contact is deliberately *not* used.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Sequence
from typing import Any

from app.discovery.browse.harvest import ground
from app.discovery.engines.queries import build_query_terms
from app.discovery.evidence.model import make_evidence
from app.discovery.identity.anchor import build_anchor
from app.discovery.identity.contacts import ContactHit
from app.discovery.loop.round import DiscoveryRound
from app.discovery.loop.seeds import followup_queries
from app.discovery.loop.state import DiscoveryState, RoundBudget
from app.discovery.matching.candidate import MatchScore, ProfileCandidate
from app.discovery.platforms.extract import ProfileData
from app.discovery.platforms.registry import get_core_registry
from app.discovery.session.bus import SessionEventBus
from app.discovery.sources import github_commits
from app.discovery.sources.website import SiteFindings
from app.discovery.types import (
    EntityType,
    EvidenceKind,
    ExistenceVerdict,
    MatchBand,
    SourceKind,
)

GITHUB_URL = "https://github.com/Yigtwxx"
SITE = "https://yigiterdogan.dev"
CONTACT_PAGE = f"{SITE}/iletisim"


def run(coro: Coroutine[Any, Any, Any]) -> Any:
    return asyncio.run(coro)


class _FakeStore:
    async def add_many(self, target_key: str, session_id: str, evidence: list[Any]) -> list[Any]:
        return list(evidence)


class _FakeWebsite:
    def __init__(self, findings: SiteFindings) -> None:
        self._findings = findings

    async def crawl(self, fetch: Any, url: str, *, name_tokens: Sequence[str] = ()) -> SiteFindings:
        return self._findings


def _candidate(*, emails: list[str] | None = None, phones: list[str] | None = None) -> ProfileCandidate:
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
            emails=emails or [],
            phones=phones or [],
        ),
        score=MatchScore(84, MatchBand.CONFIRMED, ()),
    )


def _state(candidate: ProfileCandidate) -> DiscoveryState:
    state = DiscoveryState(
        session_id="s1",
        target_key="yigit-erdogan:person",
        entity=EntityType.PERSON,
        terms=build_query_terms("Yigit Erdogan", EntityType.PERSON),
        anchor=build_anchor("Yigit Erdogan", EntityType.PERSON),
        budget=RoundBudget(),
    )
    state.anchor.domain = "yigiterdogan.dev"
    state.candidates[candidate.key] = candidate
    return state


def _round(*, website: Any = None, fetch: Any = None) -> DiscoveryRound:
    return DiscoveryRound(
        fetch=fetch,
        engines=None,
        registry=get_core_registry(),
        store=_FakeStore(),
        bus=SessionEventBus("s1"),
        avatars=None,
        website=website,
        reverse=None,
    )


class TestPersonalSite:
    def test_an_address_is_attributed_to_the_page_that_carried_it(self) -> None:
        """Not to the entry URL. `SiteFindings.emails` only ever recorded the
        value, so an address found three hops away on `/iletisim` used to be
        attributed to `/` — a provenance error nothing downstream could see."""
        findings = SiteFindings(url=SITE)
        findings.contacts.append(
            ContactHit(
                kind=EvidenceKind.EMAIL,
                value="yigit@yigiterdogan.dev",
                display="yigit@yigiterdogan.dev",
                source_url=CONTACT_PAGE,
                extractor="mailto",
                confidence=0.9,
            )
        )
        candidate = _candidate()
        state = _state(candidate)

        evidence = run(_round(website=_FakeWebsite(findings))._from_personal_site(state))

        emails = [e for e in evidence if e.kind is EvidenceKind.EMAIL]
        assert len(emails) == 1, f"expected one address, got {evidence}"
        assert emails[0].source_url == CONTACT_PAGE, "the page that published it is the source"
        assert emails[0].platform is None, "a website is not a platform"
        assert emails[0].raw == {"display": "yigit@yigiterdogan.dev"}

    def test_a_phone_keeps_the_form_the_page_wrote(self) -> None:
        """The normalised value cannot be found in the page; the display form can."""
        findings = SiteFindings(url=SITE)
        findings.contacts.append(
            ContactHit(
                kind=EvidenceKind.PHONE,
                value="+905321234567",
                display="0532 123 45 67",
                source_url=CONTACT_PAGE,
                extractor="tel",
                confidence=0.85,
            )
        )
        state = _state(_candidate())

        evidence = run(_round(website=_FakeWebsite(findings))._from_personal_site(state))

        phone = next(e for e in evidence if e.kind is EvidenceKind.PHONE)
        assert phone.value == "+905321234567"
        assert phone.raw["display"] == "0532 123 45 67"


class TestProfilePage:
    def test_an_address_on_a_profile_becomes_evidence(self) -> None:
        candidate = _candidate(emails=["yigit@yigiterdogan.dev"], phones=["+905321234567"])
        state = _state(candidate)

        evidence = _round()._evidence_from_profile(state, candidate, candidate.data)

        kinds = {e.kind for e in evidence}
        assert EvidenceKind.EMAIL in kinds and EvidenceKind.PHONE in kinds
        contact = next(e for e in evidence if e.kind is EvidenceKind.EMAIL)
        assert contact.source_url == GITHUB_URL
        assert contact.platform == "github"

    def test_a_bio_is_mined_for_addresses_but_never_for_numbers(self) -> None:
        """A bio is one line with no contact-word context, which is exactly where
        a phone pattern eats follower counts, years and `1M`."""
        candidate = _candidate()
        candidate.data.bio = "Engineer. yigit@yigiterdogan.dev. 1.299 followers, +90 000"
        state = _state(candidate)

        evidence = _round()._evidence_from_profile(state, candidate, candidate.data)

        assert any(e.kind is EvidenceKind.EMAIL for e in evidence), "an address in a bio is a finding"
        assert not any(e.kind is EvidenceKind.PHONE for e in evidence), "a bio must never yield a phone number"


class TestBrowseGrounding:
    def test_a_normalised_phone_is_grounded_on_the_form_the_page_wrote(self) -> None:
        """Without the display needle every browse-derived phone was dropped."""
        phone = make_evidence(
            EvidenceKind.PHONE,
            "phone",
            "+905321234567",
            source_url=CONTACT_PAGE,
            source_kind=SourceKind.BROWSE,
            extractor="contact:tel",
            confidence=0.8,
            raw={"display": "0532 123 45 67"},
        )

        kept, dropped = ground([phone], "<p>Telefon: 0532 123 45 67</p>")

        assert dropped == 0, "the page did contain this number, in its own notation"
        assert kept == [phone]

    def test_a_number_the_page_never_contained_is_still_dropped(self) -> None:
        phone = make_evidence(
            EvidenceKind.PHONE,
            "phone",
            "+905329999999",
            source_url=CONTACT_PAGE,
            source_kind=SourceKind.BROWSE,
            extractor="contact:tel",
            confidence=0.8,
            raw={"display": "0532 999 99 99"},
        )

        kept, dropped = ground([phone], "<p>Telefon: 0532 123 45 67</p>")

        assert kept == [] and dropped == 1


class TestGithubCommits:
    class _FakeFetch:
        def __init__(self, payload: Any) -> None:
            self.payload = payload
            self.calls: list[str] = []

        async def get_json(self, url: str, **_kwargs: Any) -> tuple[Any, Any]:
            self.calls.append(url)
            return type("R", (), {"status": "ok"})(), self.payload

    @staticmethod
    def _push(author_name: str, email: str) -> dict[str, Any]:
        return {"payload": {"commits": [{"author": {"name": author_name, "email": email}}]}}

    def test_the_privacy_proxy_address_is_never_published(self) -> None:
        """Publishing it would be publishing our inability to find an address."""
        fetch = self._FakeFetch([self._push("Yigit Erdogan", "1234+yigtwxx@users.noreply.github.com")])

        hits = run(github_commits.commit_emails(fetch, "Yigtwxx", name_tokens=("yigit", "erdogan")))

        assert hits == []

    def test_a_colleagues_address_on_a_pushed_branch_is_refused(self) -> None:
        """A PushEvent carries every commit on the branch, not only the pusher's."""
        fetch = self._FakeFetch(
            [
                self._push("Someone Else", "someone@other.dev"),
                self._push("Yigit Erdogan", "yigit@yigiterdogan.dev"),
            ]
        )

        hits = run(github_commits.commit_emails(fetch, "Yigtwxx", name_tokens=("yigit", "erdogan")))

        assert [h.value for h in hits] == ["yigit@yigiterdogan.dev"]

    def test_it_costs_exactly_one_request(self) -> None:
        fetch = self._FakeFetch([self._push("Yigit", "yigit@yigiterdogan.dev")])

        run(github_commits.commit_emails(fetch, "Yigtwxx", name_tokens=("yigit",)))

        assert len(fetch.calls) == 1, f"one request per session, got {fetch.calls}"

    def test_an_unavailable_api_reports_nothing_rather_than_guessing(self) -> None:
        fetch = self._FakeFetch(None)

        assert run(github_commits.commit_emails(fetch, "Yigtwxx", name_tokens=("yigit",))) == []


class TestExpansionPolicy:
    """A scraped contact is not ours to send to a search engine."""

    @staticmethod
    def _email(source_kind: SourceKind) -> Any:
        return make_evidence(
            EvidenceKind.EMAIL,
            "email",
            "yigit@yigiterdogan.dev",
            source_url=CONTACT_PAGE,
            source_kind=source_kind,
            extractor="contact:mailto",
            confidence=0.9,
        )

    def test_a_scraped_address_is_never_put_into_a_query(self) -> None:
        """It would be transmitted to DuckDuckGo, Bing and Brave unprompted."""
        state = _state(_candidate())

        queries = followup_queries(state, [self._email(SourceKind.WEBSITE)])

        assert not any("yigit@yigiterdogan.dev" in q for q in queries), (
            f"a scraped contact reached a third-party engine: {queries}"
        )

    def test_an_address_the_user_gave_us_is_theirs_to_search_with(self) -> None:
        state = _state(_candidate())

        queries = followup_queries(state, [self._email(SourceKind.USER_ANSWER)])

        assert any("yigit@yigiterdogan.dev" in q for q in queries), (
            f"the brief's own address must still expand, got {queries}"
        )


def test_every_producer_carries_full_provenance() -> None:
    """Invariant 4 for contacts, over every route that can emit one."""
    findings = SiteFindings(url=SITE)
    findings.contacts.append(
        ContactHit(
            kind=EvidenceKind.EMAIL,
            value="yigit@yigiterdogan.dev",
            display="yigit@yigiterdogan.dev",
            source_url=CONTACT_PAGE,
            extractor="mailto",
            confidence=0.9,
        )
    )
    candidate = _candidate(emails=["site@yigiterdogan.dev"], phones=["+905321234567"])
    state = _state(candidate)

    produced = run(_round(website=_FakeWebsite(findings))._from_personal_site(state))
    produced += _round()._evidence_from_profile(state, candidate, candidate.data)

    contacts = [e for e in produced if e.kind in (EvidenceKind.EMAIL, EvidenceKind.PHONE)]
    assert contacts, "the fixture must actually produce contacts"
    for item in contacts:
        assert item.source_url, f"{item.kind}={item.value} has no source URL"
        assert item.extractor, f"{item.kind}={item.value} has no extractor"
        assert 0.0 < item.confidence <= 1.0, f"{item.kind}={item.value} has confidence {item.confidence}"
        assert item.fingerprint, f"{item.kind}={item.value} has no fingerprint"
