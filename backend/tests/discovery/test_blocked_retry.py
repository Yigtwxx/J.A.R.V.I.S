"""Pins bug 2: a platform that refused us in round 0 was dead for the session.

``platform_probe_pairs`` added ``(platform, username)`` to ``usernames_tried``
*before* the probe and never looked at it again, so BLOCKED and ERROR — both of
which mean "we did not get to look" — were treated exactly like NOT_FOUND, which
is the one verdict that really is authoritative. A block that cleared two minutes
later was never noticed.

The rule these tests hold: blocked/errored pairs get one more chance per session,
not-found pairs get none.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.discovery.engines.queries import build_query_terms
from app.discovery.identity.anchor import build_anchor
from app.discovery.loop import seeds
from app.discovery.loop.round import DiscoveryRound
from app.discovery.loop.state import DiscoveryState, RoundBudget
from app.discovery.platforms.existence import ExistenceResult
from app.discovery.platforms.registry import get_registry
from app.discovery.session.bus import SessionEventBus
from app.discovery.types import EntityType, ExistenceVerdict

PAIR = ("instagram", "janedoe")


def build_state() -> DiscoveryState:
    state = DiscoveryState(
        session_id="test-session",
        target_key="jane-doe:person",
        entity=EntityType.PERSON,
        terms=build_query_terms("Jane Doe", EntityType.PERSON),
        anchor=build_anchor("Jane Doe", EntityType.PERSON),
        budget=RoundBudget(),
    )
    for candidate in seeds.seed_usernames(state):
        state.usernames[candidate.value] = candidate
    return state


def first_probed_pair(state: DiscoveryState) -> tuple[str, str]:
    """Run round 0's probe planning and return one pair it consumed."""
    pairs = seeds.platform_probe_pairs(state, get_registry(), include_extended=False)
    assert pairs, "round 0 must plan at least one existence check for this fixture to mean anything"
    return pairs[0]


class TestStateBookkeeping:
    def test_take_retry_pairs_reoffers_a_blocked_pair(self) -> None:
        state = build_state()
        state.record_pair_verdict(*PAIR, ExistenceVerdict.BLOCKED)

        assert state.take_retry_pairs(limit=8) == [PAIR], "a refusal is not an answer and must be retried once"

    def test_take_retry_pairs_reoffers_an_errored_pair(self) -> None:
        state = build_state()
        state.record_pair_verdict(*PAIR, ExistenceVerdict.ERROR)

        assert state.take_retry_pairs(limit=8) == [PAIR], "an error tells us nothing about the account either"

    def test_take_retry_pairs_never_reoffers_a_not_found_pair(self) -> None:
        """NOT_FOUND is the one verdict we actually established; re-probing it is waste."""
        state = build_state()
        state.record_pair_verdict(*PAIR, ExistenceVerdict.NOT_FOUND)

        assert state.take_retry_pairs(limit=8) == [], "'we looked, there is no account' is authoritative"

    def test_take_retry_pairs_gives_each_pair_at_most_one_retry(self) -> None:
        """A permanently walled platform must not be able to eat the budget."""
        state = build_state()
        state.record_pair_verdict(*PAIR, ExistenceVerdict.BLOCKED)

        assert state.take_retry_pairs(limit=8) == [PAIR]
        state.record_pair_verdict(*PAIR, ExistenceVerdict.BLOCKED)

        assert state.take_retry_pairs(limit=8) == [], "a pair that was already retried must not be offered again"

    def test_take_retry_pairs_honours_its_limit(self) -> None:
        state = build_state()
        for index in range(6):
            state.record_pair_verdict("instagram", f"jane{index}", ExistenceVerdict.BLOCKED)

        assert len(state.take_retry_pairs(limit=2)) == 2, "the per-round cap must bound the retry fan-out"

    def test_take_retry_pairs_returns_nothing_without_a_budget(self) -> None:
        state = build_state()
        state.record_pair_verdict(*PAIR, ExistenceVerdict.BLOCKED)

        assert state.take_retry_pairs(limit=0) == []
        assert state.take_retry_pairs(limit=8) == [PAIR], "a zero limit must not silently burn the pair's one retry"


class TestProbePlanning:
    def test_a_blocked_pair_is_probed_again_in_a_later_round(self) -> None:
        state = build_state()
        pair = first_probed_pair(state)
        state.record_pair_verdict(*pair, ExistenceVerdict.BLOCKED)
        state.round_no = 1

        again = seeds.platform_probe_pairs(state, get_registry(), include_extended=False)

        assert pair in again, f"a platform that refused us in round 0 was never re-probed: {again}"

    def test_a_not_found_pair_stays_dead_in_a_later_round(self) -> None:
        state = build_state()
        pair = first_probed_pair(state)
        state.record_pair_verdict(*pair, ExistenceVerdict.NOT_FOUND)
        state.round_no = 1

        again = seeds.platform_probe_pairs(state, get_registry(), include_extended=False)

        assert again == [], f"a handle already established as absent was re-probed: {again}"

    def test_a_blocked_pair_is_probed_again_only_once(self) -> None:
        state = build_state()
        pair = first_probed_pair(state)
        state.record_pair_verdict(*pair, ExistenceVerdict.BLOCKED)

        state.round_no = 1
        assert pair in seeds.platform_probe_pairs(state, get_registry(), include_extended=False)

        state.record_pair_verdict(*pair, ExistenceVerdict.BLOCKED)
        state.round_no = 2

        assert seeds.platform_probe_pairs(state, get_registry(), include_extended=False) == [], (
            "a platform that stays walled must not be probed round after round"
        )


class FakeChecker:
    """Stands in for ``ExistenceChecker`` — answers every pair with one verdict."""

    def __init__(self, verdict: ExistenceVerdict) -> None:
        self._verdict = verdict
        self.asked: list[tuple[str, str]] = []

    async def check_many(self, pairs: list[tuple[str, str]], **_kwargs: Any) -> list[ExistenceResult]:
        self.asked.extend(pairs)
        return [
            ExistenceResult(
                platform=platform,
                username=username,
                url=f"https://{platform}.example/{username}",
                verdict=self._verdict,
                http_status=403,
            )
            for platform, username in pairs
        ]


class SilentStore:
    """Stands in for ``EvidenceStore`` — persistence is not what these tests check."""

    async def add_many(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    async def record_platform_outcome(self, *_args: Any, **_kwargs: Any) -> None:
        return None


def build_round(verdict: ExistenceVerdict) -> DiscoveryRound:
    rounds = DiscoveryRound(
        fetch=object(),
        engines=object(),
        registry=get_registry(),
        store=SilentStore(),
        bus=SessionEventBus("test-session"),
        avatars=object(),
    )
    rounds._checker = FakeChecker(verdict)
    return rounds


class TestVerifyWiring:
    def test_verify_records_a_verdict_for_every_pair_it_probed(self) -> None:
        """Without this the retry planner has nothing to read and bug 2 is back."""
        state, rounds = build_state(), build_round(ExistenceVerdict.BLOCKED)

        results = asyncio.run(rounds._verify(state))

        assert results, "the fixture must probe something for this test to mean anything"
        for result in results:
            assert state.pair_verdicts.get((result.platform, result.username)) is ExistenceVerdict.BLOCKED, (
                f"no verdict was recorded for {result.platform}/{result.username}"
            )

    def test_the_next_round_re_probes_pairs_that_were_refused(self) -> None:
        """End to end: refused in round 0, actually checked again in round 1."""
        state, rounds = build_state(), build_round(ExistenceVerdict.BLOCKED)

        asyncio.run(rounds._verify(state))
        refused = set(rounds._checker.asked)
        rounds._checker.asked.clear()
        state.round_no = 1

        asyncio.run(rounds._verify(state))
        retried = rounds._checker.asked

        assert retried, "every pair was refused, yet round 1 checked nothing at all"
        assert set(retried) <= refused, f"round 1 invented pairs round 0 never probed: {set(retried) - refused}"
        assert len(retried) <= seeds.MAX_RETRY_PAIRS_PER_ROUND, (
            f"the per-round retry cap was ignored: {len(retried)} pairs re-probed"
        )

    def test_the_next_round_re_probes_nothing_when_every_handle_was_absent(self) -> None:
        state, rounds = build_state(), build_round(ExistenceVerdict.NOT_FOUND)

        asyncio.run(rounds._verify(state))
        rounds._checker.asked.clear()
        state.round_no = 1

        asyncio.run(rounds._verify(state))

        assert rounds._checker.asked == [], f"handles established as absent were probed again: {rounds._checker.asked}"
