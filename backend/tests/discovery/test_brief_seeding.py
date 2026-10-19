"""What a supplied account does to the search, and what it stops the search doing.

Two claims are under test and they pull in opposite directions:

1. A platform whose account the user gave is **never searched** — no dork, no
   username permutation. Every hit such a search returns is a stranger, because
   the account we were looking for was already in hand.
2. That same account **feeds** every other platform: its handle anchors the
   identity, its URL becomes a confirmed link target, and its handle seeds the
   permutations that are tried elsewhere.

Together those are "give me the Instagram and I will find the rest".
"""

from __future__ import annotations

import pytest

from app.discovery.brief.apply import (
    DISCOVERED_VIA_USER_SUPPLIED,
    build_brief_anchor,
    build_terms,
    evidence_for,
    seed_state,
)
from app.discovery.brief.parse import parse_brief
from app.discovery.engines.queries import entity_queries
from app.discovery.identity.anchor import CONFIRMED_USER_ANSWER
from app.discovery.loop import seeds
from app.discovery.loop.state import DiscoveryState, RoundBudget
from app.discovery.matching.candidate import ProfileCandidate
from app.discovery.matching.scoring import ScoringContext, score_profile
from app.discovery.narrative.builder import ATTRIBUTABLE_BANDS
from app.discovery.platforms.extract import ProfileData
from app.discovery.platforms.registry import get_core_registry
from app.discovery.types import (
    EntityType,
    EvidenceKind,
    ExistenceVerdict,
    Gender,
    MatchBand,
    PlatformStatus,
    SourceKind,
)

QUERY = "Eylul Akduman, kız, instagram.com/eylulakduman"


def build_state(query: str = QUERY) -> DiscoveryState:
    brief = parse_brief(query)
    state = DiscoveryState(
        session_id="s",
        target_key="eylul-akduman:person",
        entity=EntityType.PERSON,
        terms=build_terms(brief, query),
        anchor=build_brief_anchor(brief, query),
        budget=RoundBudget(),
        brief=brief,
    )
    seed_state(state)
    return state


@pytest.fixture
def state() -> DiscoveryState:
    return build_state()


class TestPinning:
    def test_the_supplied_platform_is_never_probed(self, state: DiscoveryState) -> None:
        # Round 0 needs its username candidates before pairs can be planned.
        for candidate in seeds.seed_usernames(state):
            state.usernames[candidate.value] = candidate

        pairs = seeds.platform_probe_pairs(state, get_core_registry(), include_extended=False)

        assert not [p for p in pairs if p[0] == "instagram"], (
            f"instagram was pinned by the user but got probed anyway: {[p for p in pairs if p[0] == 'instagram']}"
        )
        assert [p for p in pairs if p[0] == "github"], "the other platforms must still be swept"

    def test_no_dork_is_ever_aimed_at_the_supplied_platform(self, state: DiscoveryState) -> None:
        for candidate in seeds.seed_usernames(state):
            state.usernames[candidate.value] = candidate

        queries = seeds.round_zero_queries(state, get_core_registry())

        assert not [q for q in queries if "site:instagram.com" in q], (
            f"a dork was aimed at the pinned platform: {[q for q in queries if 'instagram.com' in q]}"
        )
        assert [q for q in queries if "site:github.com" in q], "unpinned platforms must still get their dorks"

    def test_an_unpinned_search_still_sweeps_everything(self) -> None:
        """The guard must be inert for a plain query, or it would narrow every search."""
        plain = build_state("Eylul Akduman")
        for candidate in seeds.seed_usernames(plain):
            plain.usernames[candidate.value] = candidate

        pairs = seeds.platform_probe_pairs(plain, get_core_registry(), include_extended=False)

        assert plain.pinned_platforms == {}
        assert [p for p in pairs if p[0] == "instagram"], "nothing was pinned, so instagram must be swept"


class TestTheSuppliedAccount:
    def test_it_is_already_a_candidate_before_round_zero(self, state: DiscoveryState) -> None:
        candidate = state.candidates["instagram:eylulakduman"]

        assert candidate.user_confirmed is True
        assert candidate.discovered_via == DISCOVERED_VIA_USER_SUPPLIED
        assert candidate.url == "https://www.instagram.com/eylulakduman/"

    def test_its_existence_says_where_it_came_from(self, state: DiscoveryState) -> None:
        """`EXISTS` here is the user's assertion, not a probe of ours.

        The pipeline's first invariant is that a status always carries how it was
        reached, so the provenance has to travel with the verdict.
        """
        candidate = state.candidates["instagram:eylulakduman"]

        assert candidate.verdict is ExistenceVerdict.EXISTS
        assert "user_supplied" in candidate.signals
        assert candidate.status_detail

    def test_the_platform_reports_found_with_exactly_one_account(self, state: DiscoveryState) -> None:
        instagram = [c for c in state.candidates.values() if c.platform == "instagram"]

        assert len(instagram) == 1
        assert state.platform_status["instagram"] is PlatformStatus.FOUND

    def test_it_becomes_evidence_the_biography_can_be_grounded_on(self) -> None:
        brief = parse_brief(QUERY)

        evidence = evidence_for(brief.known_profiles[0])

        assert evidence.kind is EvidenceKind.PROFILE
        assert evidence.source_kind is SourceKind.USER_ANSWER
        assert evidence.confidence == 1.0


class TestWhatItLendsTheRestOfTheSearch:
    def test_the_handle_anchors_the_identity_before_any_searching(self, state: DiscoveryState) -> None:
        """The whole point. `Anchor.is_confident` used to be False on every search."""
        assert state.anchor.handle == "eylulakduman"
        assert state.anchor.handle_platform == "instagram"
        assert state.anchor.confirmed_by == CONFIRMED_USER_ANSWER
        assert state.anchor.is_confident is True

    def test_the_handle_is_seeded_at_full_strength_for_other_platforms(self, state: DiscoveryState) -> None:
        seeded = {c.value: c for c in seeds.seed_usernames(state)}

        assert "eylulakduman" in seeded
        assert seeded["eylulakduman"].prior == 1.0, "a handle the user gave is not a guess"

    def test_the_anchor_handle_scores_a_match_on_another_platform(self, state: DiscoveryState) -> None:
        """`exact_username_anchor` (+18) was unreachable at round 0 before this."""
        elsewhere = ProfileCandidate(
            platform="x",
            username="eylulakduman",
            url="https://x.com/eylulakduman",
            verdict=ExistenceVerdict.EXISTS,
        )

        score = score_profile(elsewhere, state.anchor, (), state.context)

        assert "exact_username_anchor" in {r.code for r in score.reasons}

    def test_the_supplied_url_is_a_confirmed_link_target(self, state: DiscoveryState) -> None:
        """A profile linking to the known account earns `outbound_link_match` (+22)."""
        linking = ProfileCandidate(
            platform="x", username="someone", url="https://x.com/someone", verdict=ExistenceVerdict.EXISTS
        )
        linking.data = ProfileData(
            platform="x",
            username="someone",
            url="https://x.com/someone",
            outbound_links=["https://www.instagram.com/eylulakduman/"],
        )

        score = score_profile(linking, state.anchor, (), state.context)

        assert "outbound_link_match" in {r.code for r in score.reasons}

    def test_the_stated_gender_reaches_the_scorer(self, state: DiscoveryState) -> None:
        assert state.context.brief_gender is Gender.FEMALE

    def test_stated_attributes_reach_the_dorks_and_the_anchor(self) -> None:
        rich = build_state("Yigit Erdogan, sehir: Istanbul, okul: Bogazici, is: Getir, yigit@example.com")

        queries = entity_queries(rich.terms, limit=30)

        assert any("Istanbul" in q for q in queries), f"the stated city never reached a dork: {queries}"
        assert any("Bogazici" in q for q in queries)
        assert any("Getir" in q for q in queries)
        assert rich.anchor.location_tokens == ("istanbul",)
        assert rich.anchor.email == "yigit@example.com"


class TestIdempotence:
    def test_seeding_twice_creates_nothing_twice(self, state: DiscoveryState) -> None:
        before = len(state.candidates)

        created = seed_state(state)

        assert created == []
        assert len(state.candidates) == before


def test_an_empty_brief_leaves_the_state_exactly_as_it_was() -> None:
    plain = build_state("Jane Doe")

    assert plain.candidates == {}
    assert plain.pinned_platforms == {}
    assert plain.context == ScoringContext()
    assert plain.anchor.is_confident is False


class TestSuppliedAccountScore:
    """The account the user handed us must never read as rejected at 0 confidence.

    `ProfileCandidate.score` defaults to `EMPTY_SCORE` — value 0, band `rejected`.
    `seed_state` built its candidates before round 0 and left that default in
    place, so the UI showed the one account the user personally vouched for as
    "Rejected / 0" for the whole of round 0, until `DiscoveryRound._score` got
    round to re-scoring everything. Worse than cosmetic: `rejected` is outside
    `ATTRIBUTABLE_BANDS`, so for that window the account was excluded from the
    biography and the accounts list it should have been anchoring.

    The fix scores the candidate at seeding time with the same pure
    `score_profile` every other candidate goes through — no second scoring path,
    no hardcoded number.
    """

    def test_the_supplied_account_is_scored_at_seeding_time(self, state: DiscoveryState) -> None:
        candidate = state.candidates["instagram:eylulakduman"]

        assert candidate.score.value > 0, (
            f"the user supplied this account but it entered the search at {candidate.score.value} confidence"
        )

    def test_the_supplied_account_reads_100(self, state: DiscoveryState) -> None:
        """The user is not a source to be corroborated; they are the answer.

        Before this, a given account was scored like any other candidate and
        typically landed in `possible` — a number the user had already
        contradicted by handing us the URL.
        """
        candidate = state.candidates["instagram:eylulakduman"]

        assert candidate.score.value == 100, f"an account the user gave us reads {candidate.score.value}, not 100"
        assert candidate.score.band is MatchBand.CONFIRMED, (
            f"an account the user gave us is banded {candidate.score.band}"
        )

    def test_the_supplied_account_is_never_banded_rejected(self, state: DiscoveryState) -> None:
        candidate = state.candidates["instagram:eylulakduman"]

        assert candidate.score.band is not MatchBand.REJECTED, (
            "the account the user gave us is shown as rejected, contradicting the user's own input"
        )

    def test_the_supplied_account_is_attributable(self, state: DiscoveryState) -> None:
        """`rejected` is outside ATTRIBUTABLE_BANDS, so the band decides whether
        the biography and the accounts list are allowed to mention the account."""
        candidate = state.candidates["instagram:eylulakduman"]

        assert candidate.score.band in ATTRIBUTABLE_BANDS, (
            f"band {candidate.score.band} keeps the supplied account out of the narrative and the accounts list"
        )

    def test_the_score_says_it_came_from_the_user(self, state: DiscoveryState) -> None:
        """Invariant 4: the number has to trace to named signals, not to a constant."""
        candidate = state.candidates["instagram:eylulakduman"]
        codes = [reason.code for reason in candidate.score.reasons]

        assert "user_confirmed" in codes, f"the seeded score cites no user signal, only {codes}"

    def test_scoring_at_seed_time_agrees_with_the_round_scorer(self, state: DiscoveryState) -> None:
        """The seed-time score must be what the round would have computed, or the
        number would jump the moment round 0 finished."""
        candidate = state.candidates["instagram:eylulakduman"]

        rescored = score_profile(candidate, state.anchor, state.evidence, state.context)

        assert candidate.score.value == rescored.value, (
            f"seed time said {candidate.score.value}, the round scorer says {rescored.value}"
        )
        assert candidate.score.band is rescored.band, (
            f"seed time said {candidate.score.band}, the round scorer says {rescored.band}"
        )
