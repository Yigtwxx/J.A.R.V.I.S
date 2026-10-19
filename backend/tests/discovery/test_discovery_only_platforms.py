"""A platform we cannot probe is not a platform whose accounts we must throw away.

Reported live, twice: Spotify comes back empty even when the account exists.

Spotify user existence is genuinely unanswerable anonymously — re-measured
2026-08-30, the oEmbed route answers 400 for every `/user/` URL and the profile
page answers 200 at ~157 KB for a real handle and an invented one alike. The
first fix took that to mean the platform should be retired from the picker.

That was the wrong conclusion. It confuses *"we cannot confirm a guess"* with
*"we cannot find the account"*. A `open.spotify.com/user/...` URL handed to us by
a search engine, an outbound link or the user is evidence in its own right, and
it needs no probe. The pipeline was creating exactly that candidate in `_expand`
and then deleting it one step later in `_verify`, because the checker's
platform-level `unsupported` verdict was written straight onto the candidate.

So the rule these tests pin: an unprobeable platform is *discovery-only*. Blind
username permutations are never spent on it, and a handle that arrived with its
own evidence survives verification untouched.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Coroutine, Sequence
from typing import Any

from app.discovery.engines.queries import build_query_terms
from app.discovery.identity.anchor import build_anchor
from app.discovery.loop import seeds
from app.discovery.loop.round import DiscoveryRound
from app.discovery.loop.runner import DiscoveryRunner
from app.discovery.loop.state import DiscoveryState, RoundBudget
from app.discovery.matching.candidate import MatchScore, ProfileCandidate
from app.discovery.platforms.existence import ExistenceResult
from app.discovery.platforms.registry import get_core_registry
from app.discovery.session.bus import SessionEventBus
from app.discovery.types import EntityType, ExistenceVerdict, MatchBand, PlatformStatus
from app.services.discovery_bridge import to_api

SPOTIFY_HANDLE = "31mv4kqkqzq6bkdw6tzq7bkzq6ba"
SPOTIFY_URL = f"https://open.spotify.com/user/{SPOTIFY_HANDLE}"


class _FakeStore:
    def __init__(self) -> None:
        self.outcomes: list[Any] = []

    async def add_many(self, target_key: str, session_id: str, evidence: list[Any]) -> list[Any]:
        return list(evidence)

    async def record_platform_outcome(self, session_id: str, result: Any) -> None:
        self.outcomes.append(result)


class _RecordingChecker:
    """Records what it was asked to probe and answers the way the real one would."""

    def __init__(self) -> None:
        self.pairs: list[tuple[str, str]] = []

    async def check_many(
        self, pairs: Sequence[tuple[str, str]], *, concurrency: int = 6, stealth_allowed: Any = None
    ) -> list[ExistenceResult]:
        self.pairs.extend(pairs)
        # What `ExistenceChecker.check` returns for a platform it refuses to probe.
        return [
            ExistenceResult(
                platform=platform,
                username=username,
                url="",
                verdict=ExistenceVerdict.UNSUPPORTED,
                signals=("platform has no public profile surface",),
            )
            for platform, username in pairs
        ]


def run(coro: Coroutine[Any, Any, Any]) -> Any:
    return asyncio.run(coro)


def _state() -> DiscoveryState:
    state = DiscoveryState(
        session_id="s1",
        target_key="yigit-erdogan:person",
        entity=EntityType.PERSON,
        terms=build_query_terms("Yigit Erdogan", EntityType.PERSON),
        anchor=build_anchor("Yigit Erdogan", EntityType.PERSON),
        budget=RoundBudget(),
    )
    seeds.seed_usernames(state)
    return state


def _round(store: _FakeStore, checker: _RecordingChecker) -> DiscoveryRound:
    round_runner = DiscoveryRound(
        fetch=None,
        engines=None,
        registry=get_core_registry(),
        store=store,
        bus=SessionEventBus("s1"),
        avatars=None,
    )
    round_runner._checker = checker
    return round_runner


def _with_serp_spotify(state: DiscoveryState) -> ProfileCandidate:
    """Exactly what `_expand` builds when an engine returns a Spotify profile."""
    candidate = ProfileCandidate(
        platform="spotify",
        username=SPOTIFY_HANDLE,
        url=SPOTIFY_URL,
        discovered_round=0,
        discovered_via="serp",
    )
    state.upsert_candidate(candidate)
    return candidate


def test_a_found_account_survives_verification() -> None:
    """The bug, stated directly: the account reached `_verify` and did not leave it."""
    state = _state()
    _with_serp_spotify(state)
    checker = _RecordingChecker()

    run(_round(_FakeStore(), checker)._verify(state))

    survivor = state.candidates[f"spotify:{SPOTIFY_HANDLE}"]
    assert survivor.is_live, (
        f"a Spotify profile URL a search engine handed us was erased by verification: verdict={survivor.verdict.value}"
    )
    assert survivor.platform_status is PlatformStatus.FOUND, (
        f"the account was found, so the user must be told 'found', not {survivor.platform_status.value!r}"
    )


def test_a_found_account_is_not_probed() -> None:
    """There is no probe that could add anything — every handle answers 200."""
    state = _state()
    _with_serp_spotify(state)
    checker = _RecordingChecker()

    run(_round(_FakeStore(), checker)._verify(state))

    assert ("spotify", SPOTIFY_HANDLE) not in checker.pairs, (
        "a handle backed by a discovered URL must not spend a request on a check that cannot answer"
    )


def test_blind_permutations_are_never_spent_on_it() -> None:
    """The waste half: every search was paying for guesses that could not resolve."""
    state = _state()
    checker = _RecordingChecker()

    run(_round(_FakeStore(), checker)._verify(state))

    spotify_probes = [pair for pair in checker.pairs if pair[0] == "spotify"]
    assert spotify_probes == [], f"blind Spotify guesses were probed anyway: {spotify_probes}"


def test_a_platform_that_can_be_probed_is_untouched() -> None:
    """The guard must not smuggle a free pass to platforms that do answer."""
    state = _state()
    checker = _RecordingChecker()

    run(_round(_FakeStore(), checker)._verify(state))

    assert any(pair[0] == "github" for pair in checker.pairs), "GitHub has a real API; it must still be probed"


def test_the_platform_is_reported_as_found() -> None:
    """Invariant 1: never silently empty. The grid must say `found`, not nothing."""
    state = _state()
    _with_serp_spotify(state)

    run(_round(_FakeStore(), _RecordingChecker())._verify(state))

    assert state.platform_status.get("spotify") is PlatformStatus.FOUND, (
        f"an account we hold the profile URL for must report `found`, got {state.platform_status.get('spotify')}"
    )


def test_the_outcome_is_persisted() -> None:
    """Skipping the probe must not also skip telling anyone what we have."""
    store = _FakeStore()
    state = _state()
    _with_serp_spotify(state)

    run(_round(store, _RecordingChecker())._verify(state))

    spotify_outcomes = [o for o in store.outcomes if o.platform == "spotify"]
    assert spotify_outcomes, "the found account left no record for the session store"
    assert spotify_outcomes[0].url == SPOTIFY_URL, (
        f"the recorded outcome must carry the URL that proves it, got {spotify_outcomes[0].url!r}"
    )


def test_a_stale_unsupported_verdict_does_not_erase_it() -> None:
    """Defence in depth: whatever route reaches the checker, the finding survives.

    `_verify` no longer forwards these handles, but a retry pair or a future
    caller could. `unsupported` describes the platform's probe surface, never
    this handle, so it must not be written onto a candidate backed by a URL.
    """
    state = _state()
    candidate = _with_serp_spotify(state)
    candidate.verdict = ExistenceVerdict.UNSUPPORTED  # as a previous run left it
    state.upsert_candidate(candidate)

    run(_round(_FakeStore(), _RecordingChecker())._verify(state))

    assert state.candidates[f"spotify:{SPOTIFY_HANDLE}"].is_live, (
        "a candidate poisoned by an earlier `unsupported` verdict must recover, not stay deleted"
    )


def test_an_account_the_user_rejected_is_not_reported_as_found() -> None:
    """ "That is not me" outranks "a search engine indexed it".

    Skipping the probe must not also skip the one judgement that beats the URL.
    `note_platform` takes a status, not a candidate, so hard-coding FOUND here
    would announce a platform the user had just struck off.
    """
    state = _state()
    candidate = _with_serp_spotify(state)
    candidate.user_rejected = True
    state.upsert_candidate(candidate)

    run(_round(_FakeStore(), _RecordingChecker())._verify(state))

    assert state.platform_status.get("spotify") is not PlatformStatus.FOUND, (
        "an account the user rejected was still announced as found"
    )


class _StubEngines:
    @staticmethod
    def health() -> dict[str, str]:
        return {}


class _FetchStats:
    @staticmethod
    def as_dict() -> dict[str, Any]:
        return {}


class _StubFetch:
    stealth_available = True
    stealth_unavailable_reason = ""
    stats = _FetchStats()


def test_the_found_account_reaches_the_finished_answer() -> None:
    """The whole report, end to end: ticked in the picker, found, and *shown*.

    The two fixes before this one each moved the account one step further and
    stopped short of the answer. The first stopped it being probed into
    `unsupported`; the second let it survive `_verify`. It still never appeared,
    because `_build_result` reports the elected cluster plus one row for every
    *other* platform — and that fallback skipped live candidates, so the one
    account that can never be corroborated into the elected cluster was also the
    one the fallback refused to speak for.

    A discovery-only account carries no avatar, no outbound link and no display
    name, so nothing can tie it to the elected identity. It always clusters
    alone. Reporting it is therefore not an optional nicety here — it is the only
    way this platform can ever appear at all.
    """
    state = _state()
    github = ProfileCandidate(
        platform="github",
        username="yigtwxx",
        url="https://github.com/yigtwxx",
        verdict=ExistenceVerdict.EXISTS,
        score=MatchScore(88, MatchBand.CONFIRMED, ()),
    )
    state.upsert_candidate(github)
    _with_serp_spotify(state)

    run(_round(_FakeStore(), _RecordingChecker())._verify(state))
    runner = DiscoveryRunner(store=None, broker=None, manager=None, rate_limiter=None)
    runner._recluster(state)
    state.elected = next(c for c in state.clusters if github.key in {m.key for m in c.members})
    result = runner._build_result(state, _StubEngines(), _StubFetch(), time.monotonic())

    spotify_rows = [p for p in result.profiles if p.platform == "spotify"]
    assert spotify_rows, (
        f"Spotify was ticked, found, and still absent from the answer; reported: "
        f"{sorted({p.platform for p in result.profiles})}"
    )
    assert spotify_rows[0].url == SPOTIFY_URL, (
        f"the row must carry the URL that is its entire evidence, got {spotify_rows[0].url!r}"
    )
    assert spotify_rows[0].platform_status is PlatformStatus.FOUND, (
        f"an account we hold the profile URL for is found, not {spotify_rows[0].platform_status.value!r}"
    )

    # And through the bridge, because `result.profiles` is not a surface anyone
    # looks at: the console reads `social_profiles`, and the platform buttons
    # read the legacy `spotify_url`. Both were empty for all three reports.
    payload = to_api(result)
    assert any(p.platform == "spotify" for p in payload["social_profiles"]), (
        "the API response the console renders still has no Spotify account"
    )
    assert payload["spotify_url"] == SPOTIFY_URL, (
        f"the Spotify button reads the legacy field, which is {payload['spotify_url']!r}"
    )
