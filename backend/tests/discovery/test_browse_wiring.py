"""Which targets earn a browser, and which the phase must refuse to spend one on.

The browse tier is the most expensive thing in the pipeline — a step is a local
vision inference, and the model that serves it cannot share 8 GB of VRAM with
the one that writes the biography. So the gates matter as much as the loop, and
each of them protects something specific:

* a blind name permutation is wrong at every tier, so a browser cannot rescue it;
* a login wall was already answered honestly by the cheap tiers, and an anonymous
  browser will reach the same wall a dozen inferences later;
* the phase runs once per search, or ollama evicts and reloads a 6 GB model every
  round;
* and it never starts without enough clock left for the rest of the search.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.discovery.browse.runner import BrowseSettings
from app.discovery.browse.types import BrowseOutcome, BrowseReport
from app.discovery.engines.queries import build_query_terms
from app.discovery.fetch.result import FetchResult
from app.discovery.identity.anchor import build_anchor
from app.discovery.loop.round import DiscoveryRound
from app.discovery.loop.state import DiscoveryState, RoundBudget
from app.discovery.matching.candidate import ProfileCandidate
from app.discovery.platforms.existence import ExistenceResult
from app.discovery.platforms.registry import get_registry
from app.discovery.session.bus import SessionEventBus
from app.discovery.types import EntityType, ExistenceVerdict, FetchStatus, FetchTier

URL = "https://www.instagram.com/janedoe/"


def run(coro: Any) -> Any:
    return asyncio.run(coro)


class SilentStore:
    async def add_many(self, *_args: Any, **_kwargs: Any) -> None:
        return None


class FakeBrowseRunner:
    """Stands in for ``BrowseRunner`` — records what it was asked to browse."""

    def __init__(self, *, settings: BrowseSettings | None = None) -> None:
        self.settings = settings or BrowseSettings()
        self.tasks: list[str] = []

    async def run(self, task, *, session_id, emit=None, should_stop=None) -> BrowseReport:
        del session_id, emit, should_stop
        self.tasks.append(f"{task.platform}:{task.username}")
        return BrowseReport(task=task, outcome=BrowseOutcome.REACHED_EMPTY, detail="nothing there")


def build_round(browse: FakeBrowseRunner | None) -> DiscoveryRound:
    return DiscoveryRound(
        fetch=object(),
        engines=object(),
        registry=get_registry(),
        store=SilentStore(),
        bus=SessionEventBus("test-session"),
        avatars=object(),
        browse=browse,
    )


def build_state(*, discovered_via: str = "serp", wall_clock: float = 1800.0) -> DiscoveryState:
    state = DiscoveryState(
        session_id="test-session",
        target_key="jane-doe:person",
        entity=EntityType.PERSON,
        terms=build_query_terms("Jane Doe", EntityType.PERSON),
        anchor=build_anchor("Jane Doe", EntityType.PERSON),
        budget=RoundBudget(max_wall_clock_s=wall_clock),
    )
    state.upsert_candidate(
        ProfileCandidate(
            platform="instagram",
            username="janedoe",
            url=URL,
            verdict=ExistenceVerdict.BLOCKED,
            discovered_via=discovered_via,
        )
    )
    return state


def blocked_result(*, block_signal: str | None = None) -> ExistenceResult:
    fetch = FetchResult(
        url=URL,
        final_url=URL,
        status=FetchStatus.BLOCKED,
        http_status=403,
        tier=FetchTier.STEALTH,
        block_signal=block_signal,
    )
    return ExistenceResult(
        platform="instagram",
        username="janedoe",
        url=URL,
        verdict=ExistenceVerdict.BLOCKED,
        http_status=403,
        tier_used=FetchTier.STEALTH,
        fetch=fetch,
    )


# -- who earns a browser --------------------------------------------------------


def test_a_refused_target_something_points_at_earns_a_browse():
    browse = FakeBrowseRunner()
    state = build_state(discovered_via="serp")

    run(build_round(browse)._browse(state, [blocked_result()]))

    assert browse.tasks == ["instagram:janedoe"], f"got {browse.tasks}"


def test_a_check_that_errored_before_a_verdict_earns_a_browse():
    """`error` means we never reached an answer, which is what a page can fix.

    A render that needed JavaScript, a truncated response, a redirect the plain
    client would not follow — all land here, and all are cases a real browser
    settles. Excluded until 2026-08-29, so a platform that crashed mid-check was
    simply dropped.
    """
    browse = FakeBrowseRunner()
    state = build_state(discovered_via="serp")
    errored = ExistenceResult(
        platform="instagram",
        username="janedoe",
        url=URL,
        verdict=ExistenceVerdict.ERROR,
        detail="parser blew up",
        tier_used=FetchTier.STEALTH,
    )

    run(build_round(browse)._browse(state, [errored]))

    assert browse.tasks == ["instagram:janedoe"], f"an errored check was dropped instead of browsed: {browse.tasks}"


def test_a_settled_absence_never_earns_a_browse():
    """`not_found` is an answer. Spending a browser on it buys nothing."""
    browse = FakeBrowseRunner()
    state = build_state(discovered_via="serp")
    absent = ExistenceResult(
        platform="instagram",
        username="janedoe",
        url=URL,
        verdict=ExistenceVerdict.NOT_FOUND,
        http_status=404,
    )

    run(build_round(browse)._browse(state, [absent]))

    assert browse.tasks == [], f"a settled 404 was browsed: {browse.tasks}"


def test_a_blind_permutation_never_earns_a_browse():
    """A guessed handle is wrong at every tier; a browser cannot make it right."""
    browse = FakeBrowseRunner()
    state = build_state(discovered_via="permutation")

    run(build_round(browse)._browse(state, [blocked_result()]))

    assert browse.tasks == [], f"a guessed handle was browsed: {browse.tasks}"


def test_a_login_walled_target_is_not_browsed():
    """We already hold the honest verdict; an anonymous browser reaches the same wall."""
    browse = FakeBrowseRunner()
    state = build_state()

    run(build_round(browse)._browse(state, [blocked_result(block_signal="login_redirect")]))

    assert browse.tasks == [], f"a known auth wall was browsed anyway: {browse.tasks}"


def test_a_target_already_browsed_is_not_browsed_again():
    browse = FakeBrowseRunner()
    state = build_state()
    state.browsed.add("instagram:janedoe")

    run(build_round(browse)._browse(state, [blocked_result()]))

    assert browse.tasks == [], f"the same page was browsed twice: {browse.tasks}"


def test_the_task_limit_is_respected():
    browse = FakeBrowseRunner(settings=BrowseSettings(max_tasks_per_search=1))
    state = build_state()
    state.upsert_candidate(
        ProfileCandidate(
            platform="x",
            username="janedoe",
            url="https://x.com/janedoe",
            verdict=ExistenceVerdict.BLOCKED,
            discovered_via="serp",
        )
    )
    second = ExistenceResult(
        platform="x",
        username="janedoe",
        url="https://x.com/janedoe",
        verdict=ExistenceVerdict.BLOCKED,
        tier_used=FetchTier.STEALTH,
    )

    run(build_round(browse)._browse(state, [blocked_result(), second]))

    assert len(browse.tasks) == 1, f"the per-search task limit was exceeded: {browse.tasks}"


# -- when the phase runs at all -------------------------------------------------


def test_browse_runs_at_most_once_per_search():
    """Twice would make ollama evict and reload a 6 GB model for the same targets."""
    browse = FakeBrowseRunner()
    state = build_state()
    rounds = build_round(browse)

    run(rounds._browse(state, [blocked_result()]))
    run(rounds._browse(state, [blocked_result()]))

    assert len(browse.tasks) == 1, f"the phase ran more than once: {browse.tasks}"
    assert state.browse_used is True


def test_browse_is_skipped_when_too_little_wall_clock_remains():
    browse = FakeBrowseRunner(settings=BrowseSettings(min_time_left_seconds=3000.0))
    state = build_state(wall_clock=600.0)

    run(build_round(browse)._browse(state, [blocked_result()]))

    assert browse.tasks == [], "the phase started with no budget left for the rest of the search"
    assert state.browse_used is False, "a phase that never ran marked itself used"


def test_the_phase_is_inert_when_the_tier_is_switched_off():
    state = build_state()

    run(build_round(None)._browse(state, [blocked_result()]))

    assert state.browse_used is False, "a disabled phase still marked itself used"


def test_a_disabled_settings_flag_also_makes_the_phase_inert():
    browse = FakeBrowseRunner(settings=BrowseSettings(enabled=False))
    state = build_state()

    run(build_round(browse)._browse(state, [blocked_result()]))

    assert browse.tasks == [], f"a disabled tier still browsed: {browse.tasks}"


# -- invariant 1 ----------------------------------------------------------------


def test_browse_never_changes_a_platform_verdict():
    """The cheap tiers already spoke. Browse may enrich, never overrule."""
    browse = FakeBrowseRunner()
    state = build_state()
    before = dict(state.platform_status)

    run(build_round(browse)._browse(state, [blocked_result()]))

    assert state.platform_status == before, f"browse rewrote a platform verdict: {before} -> {state.platform_status}"


def test_an_empty_result_set_costs_nothing():
    browse = FakeBrowseRunner()
    state = build_state()

    run(build_round(browse)._browse(state, []))

    assert browse.tasks == []
    assert state.browse_used is False, "a phase with no targets marked itself used"
