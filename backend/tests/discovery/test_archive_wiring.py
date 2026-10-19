"""The archive recovery phase, and the line it must not cross.

``ArchiveRecovery`` and ``ProfileCandidate.archived_only`` were both written,
tested and then never connected to anything — ``discovery_archive_recovery_enabled``
was read by no code at all. These tests exist because wiring it up is precisely
where the pipeline's first invariant is easiest to break: a snapshot is evidence
about the *past*, and the temptation is to let it answer a question about the
present.

So the phase is allowed to add what an account looked like, and forbidden from
changing whether it exists.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import Any

from app.discovery.engines.queries import build_query_terms
from app.discovery.evidence.model import Evidence
from app.discovery.identity.anchor import build_anchor
from app.discovery.loop.round import DiscoveryRound
from app.discovery.loop.state import DiscoveryState, RoundBudget
from app.discovery.matching.candidate import ProfileCandidate
from app.discovery.platforms.existence import ExistenceResult
from app.discovery.platforms.registry import get_registry
from app.discovery.session.bus import SessionEventBus
from app.discovery.sources.archive import ArchivedSnapshot
from app.discovery.types import EntityType, EvidenceKind, ExistenceVerdict, SourceKind

SNAPSHOT = ArchivedSnapshot(
    url="https://www.instagram.com/janedoe/",
    snapshot_url="https://web.archive.org/web/20210411120000/https://www.instagram.com/janedoe/",
    timestamp=datetime(2021, 4, 11, 12, 0, tzinfo=UTC),
    status=200,
    display_name="Jane Doe",
    bio="Engineer at Acme Corp",
    avatar_url="https://web.archive.org/web/20210411120000im_/https://example.com/a.jpg",
)


def run(coro: Coroutine[Any, Any, Any]) -> Any:
    return asyncio.run(coro)


class FakeArchive:
    """Stands in for ``ArchiveRecovery`` — records calls, returns a fixed capture."""

    def __init__(self, snapshot: ArchivedSnapshot | None = SNAPSHOT) -> None:
        self._snapshot = snapshot
        self.asked: list[str] = []

    async def recover_profile(self, _fetch: Any, url: str, *, platform: str) -> ArchivedSnapshot | None:
        del platform
        self.asked.append(url)
        return self._snapshot


class SilentStore:
    """Stands in for ``EvidenceStore`` — the phase under test is not persistence."""

    async def add_many(self, *_args: Any, **_kwargs: Any) -> None:
        return None


def build_round(archive: FakeArchive | None, **kwargs: Any) -> DiscoveryRound:
    return DiscoveryRound(
        fetch=object(),
        engines=object(),
        registry=get_registry(),
        store=SilentStore(),
        bus=SessionEventBus("test-session"),
        avatars=object(),
        archive=archive,
        **kwargs,
    )


def build_state(*, with_candidate: bool = True, discovered_via: str = "serp") -> DiscoveryState:
    state = DiscoveryState(
        session_id="test-session",
        target_key="jane-doe:person",
        entity=EntityType.PERSON,
        terms=build_query_terms("Jane Doe", EntityType.PERSON),
        anchor=build_anchor("Jane Doe", EntityType.PERSON),
        budget=RoundBudget(),
    )
    if with_candidate:
        state.upsert_candidate(
            ProfileCandidate(
                platform="instagram",
                username="janedoe",
                url="https://www.instagram.com/janedoe/",
                verdict=ExistenceVerdict.BLOCKED,
                discovered_via=discovered_via,
            )
        )
    return state


def blocked_result() -> ExistenceResult:
    return ExistenceResult(
        platform="instagram",
        username="janedoe",
        url="https://www.instagram.com/janedoe/",
        verdict=ExistenceVerdict.BLOCKED,
        http_status=403,
    )


def captured(state: DiscoveryState) -> list[Evidence]:
    return [e for e in state.evidence if e.source_kind is SourceKind.ARCHIVE]


def test_a_blocked_profile_with_a_candidate_is_looked_up_in_the_archive() -> None:
    archive, state = FakeArchive(), build_state()

    run(build_round(archive)._recover(state, [blocked_result()]))

    assert archive.asked == ["https://www.instagram.com/janedoe/"]
    assert state.candidates["instagram:janedoe"].archived_only is True


def test_recovery_never_changes_the_verdict() -> None:
    """Invariant 1. The account was refused; a 2021 capture does not change that."""
    state = build_state()

    run(build_round(FakeArchive())._recover(state, [blocked_result()]))

    assert state.candidates["instagram:janedoe"].verdict is ExistenceVerdict.BLOCKED, (
        "an archived snapshot was allowed to promote a refused profile to existing"
    )


def test_recovery_emits_no_profile_evidence() -> None:
    """PROFILE is the kind the rest of the pipeline reads as "real and reachable"."""
    state = build_state()

    run(build_round(FakeArchive())._recover(state, [blocked_result()]))

    kinds = {e.kind for e in captured(state)}
    assert EvidenceKind.PROFILE not in kinds, f"archive claimed a live profile: {kinds}"
    assert EvidenceKind.REAL_NAME in kinds
    assert EvidenceKind.BIO in kinds


def test_archive_evidence_is_discounted_and_dated() -> None:
    """ "Worked at X" must read as "worked at X as of 2021-04-11"."""
    state = build_state()

    run(build_round(FakeArchive())._recover(state, [blocked_result()]))

    name = next(e for e in captured(state) if e.kind is EvidenceKind.REAL_NAME)
    assert name.value == "Jane Doe"
    assert "2021-04-11" in name.extractor, f"the snapshot date is missing from {name.extractor}"
    assert name.raw and name.raw.get("snapshot_date") == "2021-04-11"
    assert name.confidence < 0.7, "archive-derived confidence must be discounted, not passed through"
    assert name.source_url.startswith("https://web.archive.org/"), (
        "evidence must point at the capture, not the live URL"
    )


def test_blind_permutations_are_not_worth_two_extra_fetches() -> None:
    """The gate that actually matters, and the one the first version got wrong.

    ``_verify`` creates a candidate for *every* handle it checks, so "has a
    candidate" is true even for a name permutation nobody has corroborated.
    The real test is where the handle came from — the same one the browser tier
    applies — and a guessed handle was almost certainly never archived either.
    """
    archive = FakeArchive()
    state = build_state(discovered_via="username_permutation")

    run(build_round(archive)._recover(state, [blocked_result()]))

    assert archive.asked == [], "the archive was spent on an uncorroborated guess"


def test_a_handle_from_a_search_hit_does_earn_the_lookup() -> None:
    archive = FakeArchive()
    state = build_state(discovered_via="serp")

    run(build_round(archive)._recover(state, [blocked_result()]))

    assert archive.asked == ["https://www.instagram.com/janedoe/"]


def test_a_handle_with_no_candidate_at_all_is_skipped() -> None:
    archive, state = FakeArchive(), build_state(with_candidate=False)

    run(build_round(archive)._recover(state, [blocked_result()]))

    assert archive.asked == []


def test_a_found_profile_is_never_sent_to_the_archive() -> None:
    archive, state = FakeArchive(), build_state()
    live = ExistenceResult(
        platform="instagram",
        username="janedoe",
        url="https://www.instagram.com/janedoe/",
        verdict=ExistenceVerdict.EXISTS,
        http_status=200,
    )

    run(build_round(archive)._recover(state, [live]))

    assert archive.asked == []


def test_the_lookup_budget_is_honoured() -> None:
    archive, state = FakeArchive(), build_state()
    for index in range(6):
        state.upsert_candidate(
            ProfileCandidate(
                platform="instagram",
                username=f"jane{index}",
                url=f"https://www.instagram.com/jane{index}/",
                verdict=ExistenceVerdict.BLOCKED,
                discovered_via="serp",
            )
        )
    results = [
        ExistenceResult(
            platform="instagram",
            username=f"jane{index}",
            url=f"https://www.instagram.com/jane{index}/",
            verdict=ExistenceVerdict.BLOCKED,
            http_status=403,
        )
        for index in range(6)
    ]

    run(build_round(archive, max_archive_lookups=2)._recover(state, results))

    assert len(archive.asked) == 2


def test_the_phase_is_inert_when_archive_recovery_is_disabled() -> None:
    state = build_state()

    run(build_round(None)._recover(state, [blocked_result()]))

    assert captured(state) == []
    assert state.candidates["instagram:janedoe"].archived_only is False


def test_a_capture_that_does_not_exist_leaves_the_candidate_untouched() -> None:
    state = build_state()

    run(build_round(FakeArchive(snapshot=None))._recover(state, [blocked_result()]))

    assert state.candidates["instagram:janedoe"].archived_only is False
    assert captured(state) == []


def test_the_same_url_is_not_re_queried_in_a_later_round() -> None:
    """The archive does not change between rounds; asking twice just costs fetches."""
    archive, state, results = FakeArchive(), build_state(), [blocked_result()]
    rounds = build_round(archive)

    run(rounds._recover(state, results))
    run(rounds._recover(state, results))

    assert len(archive.asked) == 1, f"the archive was asked again about the same URL: {archive.asked}"
