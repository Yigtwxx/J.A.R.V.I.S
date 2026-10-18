"""Every effect an answer can produce must actually change the search.

`apply_answer` translates a reply into `(effect, value)` pairs, and the runner's
if/elif chain acts on them. Three of them fell through it:

* `focus_platform` — produced by the "which blocked platform matters most?"
  question, matched by nothing. The user picked a platform and the search carried
  on exactly as before.
* `reject_fact` — produced by "none of these" on an employer or school, matched
  by nothing. A fact the user had explicitly denied kept driving the answer.
* `select_avatar` — matched, but the body assigned `avatar_sha256` to itself, so
  choosing the right face did nothing either.

An unanswerable question is a wasted question; a question whose answer is
discarded is worse, because the user waited for it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

from app.config import get_settings
from app.discovery.engines.queries import build_query_terms
from app.discovery.hitl.broker import QuestionBroker
from app.discovery.hitl.questions import Answer, Question, QuestionKind, QuestionOption
from app.discovery.identity.anchor import build_anchor
from app.discovery.identity.workedu import EducationRecord, WorkRecord, normalize_org
from app.discovery.loop.runner import DiscoveryRunner
from app.discovery.loop.state import DiscoveryState, RoundBudget
from app.discovery.matching.candidate import ProfileCandidate
from app.discovery.session.bus import SessionEventBus
from app.discovery.session.manager import SessionManager
from app.discovery.types import EntityType, ExistenceVerdict


class _FakeStore:
    """The runner only reaches the store to persist new evidence here."""

    def __init__(self) -> None:
        self.added: list[Any] = []

    async def add_many(self, target_key: str, session_id: str, evidence: list[Any]) -> list[Any]:
        self.added.extend(evidence)
        return list(evidence)


def run(coro: Coroutine[Any, Any, Any]) -> Any:
    return asyncio.run(coro)


def _runner() -> DiscoveryRunner:
    return DiscoveryRunner(
        store=_FakeStore(),
        broker=QuestionBroker(),
        manager=SessionManager(),
        rate_limiter=None,
        settings=get_settings(),
    )


def _state() -> DiscoveryState:
    return DiscoveryState(
        session_id="s1",
        target_key="yigit-erdogan:person",
        entity=EntityType.PERSON,
        terms=build_query_terms("Yigit Erdogan", EntityType.PERSON),
        anchor=build_anchor("Yigit Erdogan", EntityType.PERSON),
        budget=RoundBudget(),
    )


def _work(org: str) -> WorkRecord:
    return WorkRecord(
        organization=org,
        organization_normalized=normalize_org(org),
        role="Engineer",
        source_url="https://x.test/1",
        confidence=0.7,
    )


def _education(inst: str) -> EducationRecord:
    return EducationRecord(
        institution=inst,
        institution_normalized=normalize_org(inst),
        source_url="https://x.test/2",
        confidence=0.6,
    )


def _question(kind: QuestionKind, *, options: list[QuestionOption], context: dict[str, Any]) -> Question:
    return Question(
        id="q1",
        kind=kind,
        text="?",
        options=tuple(options),
        context=context,
        semantic_hash="hash",
    )


def test_focus_platform_answer_reopens_that_platform_for_probing() -> None:
    """A pair is probed once per session, so the answer had to clear it to mean anything."""
    runner = _runner()
    state = _state()
    state.usernames_tried.update({("linkedin", "yigtwxx"), ("linkedin", "yigit"), ("github", "yigtwxx")})
    question = _question(
        QuestionKind.CHOOSE_DIRECTION,
        options=[QuestionOption(id="platform:linkedin", label="LinkedIn")],
        context={},
    )

    run(
        runner._apply_answer(
            state,
            SessionEventBus("s1"),
            question,
            Answer(question_id="q1", option_ids=["platform:linkedin"]),
        )
    )

    assert not any(pair[0] == "linkedin" for pair in state.usernames_tried), (
        f"the chosen platform must become probeable again, still tried: {state.usernames_tried}"
    )
    assert ("github", "yigtwxx") in state.usernames_tried, "other platforms must be left alone"


def test_rejected_employer_stops_driving_the_answer() -> None:
    """ "None of these" has to remove the fact, not merely record the click."""
    runner = _runner()
    state = _state()
    state.work = [
        _work("Getir"),
        _work("Trendyol"),
    ]
    state.anchor.employer = "Getir"
    question = _question(
        QuestionKind.CONFIRM_FACT,
        options=[QuestionOption(id="employer=Getir", label="Getir")],
        context={"kind": "employer", "values": ["Getir"]},
    )

    run(
        runner._apply_answer(
            state,
            SessionEventBus("s1"),
            question,
            Answer(question_id="q1", option_ids=["__no__"]),
        )
    )

    assert [w.organization for w in state.work] == ["Trendyol"], (
        f"the denied employer must be dropped, got {[w.organization for w in state.work]}"
    )
    assert state.anchor.employer is None, "the anchor must not keep steering on a denied fact"


def test_rejected_school_leaves_employers_untouched() -> None:
    """Retraction is targeted: denying a school must not clear the work history."""
    runner = _runner()
    state = _state()
    state.work = [_work("Getir")]
    state.education = [_education("ITU")]
    question = _question(
        QuestionKind.CONFIRM_FACT,
        options=[QuestionOption(id="school=ITU", label="ITU")],
        context={"kind": "school", "values": ["ITU"]},
    )

    run(
        runner._apply_answer(
            state,
            SessionEventBus("s1"),
            question,
            Answer(question_id="q1", option_ids=["__no__"]),
        )
    )

    assert state.education == [], "the denied school must be dropped"
    assert [w.organization for w in state.work] == ["Getir"], "employers must survive a school rejection"


def test_choosing_an_avatar_confirms_the_accounts_that_carry_it() -> None:
    """Picking the real face is a positive identification of the accounts showing it."""
    runner = _runner()
    state = _state()
    mine = ProfileCandidate(
        platform="github", username="yigtwxx", url="https://github.com/Yigtwxx", verdict=ExistenceVerdict.EXISTS
    )
    mine.avatar_sha256 = "sha-mine"
    stranger = ProfileCandidate(
        platform="x", username="yigtwx", url="https://x.com/Yigtwx", verdict=ExistenceVerdict.EXISTS
    )
    stranger.avatar_sha256 = "sha-other"
    state.candidates = {mine.key: mine, stranger.key: stranger}
    question = _question(
        QuestionKind.CONFIRM_AVATAR,
        options=[QuestionOption(id="sha-mine", label="github/yigtwxx")],
        context={"sha256": ["sha-mine", "sha-other"]},
    )

    run(
        runner._apply_answer(
            state,
            SessionEventBus("s1"),
            question,
            Answer(question_id="q1", option_ids=["sha-mine"]),
        )
    )

    assert mine.user_confirmed, "the account showing the chosen picture must be confirmed"
    assert not stranger.user_rejected, (
        "a different picture on another platform is normal for one person and must not be a rejection"
    )


class TestTheCardChangesWhenYouAnswer:
    """An answer must move the number on screen, not only a flag in memory.

    `_apply_answer` set `user_confirmed` and stopped. The score was recomputed by
    the *next* round's `_score`, and a round is minutes away — if another one runs
    at all. Watched live on 2026-08-29: the user was asked about a TikTok account,
    answered yes, and the card went on reading "REJECTED · 0" because that score
    had been computed before the question was asked. The one account they had
    personally vouched for was the worst-rated thing on screen, and nothing was
    published to tell the UI otherwise.
    """

    @staticmethod
    def _confirm_question(key: str) -> Question:
        return Question(
            id="q1",
            kind=QuestionKind.CONFIRM_PROFILE,
            text=f"Is https://www.tiktok.com/@{key.split(':')[1]} the account you are looking for?",
            options=(
                QuestionOption(id="__yes__", label="Yes, that's them"),
                QuestionOption(id="__no__", label="No, that's someone else"),
            ),
            context={"candidate_key": key, "platform": "tiktok", "username": key.split(":")[1]},
        )

    @staticmethod
    def _candidate() -> ProfileCandidate:
        return ProfileCandidate(
            platform="tiktok",
            username="yagmurozgx",
            url="https://www.tiktok.com/@yagmurozgx",
            verdict=ExistenceVerdict.EXISTS,
        )

    def _answer_yes(self, runner: DiscoveryRunner, state: DiscoveryState, bus: SessionEventBus) -> ProfileCandidate:
        candidate = self._candidate()
        state.candidates[candidate.key] = candidate
        run(
            runner._apply_answer(
                state,
                bus,
                self._confirm_question(candidate.key),
                Answer(question_id="q1", option_ids=["__yes__"]),
            )
        )
        return candidate

    def test_the_confirmed_account_is_re_scored_immediately(self) -> None:
        candidate = self._answer_yes(_runner(), _state(), SessionEventBus("s1"))

        assert candidate.score.value == 100, (
            f"the account the user just vouched for still reads {candidate.score.value}"
        )
        assert str(candidate.score.band) == "confirmed", f"banded {candidate.score.band}"

    def test_the_new_score_is_published_so_the_card_can_change(self) -> None:
        bus = SessionEventBus("s1")
        candidate = self._answer_yes(_runner(), _state(), bus)

        updates = [e for e in bus.replay(0) if str(e.type) == "candidate_updated"]
        assert updates, f"nothing told the UI, events were {[str(e.type) for e in bus.replay(0)]}"
        mine = [e for e in updates if e.data.get("username") == candidate.username]
        assert mine, f"the update was for something else: {[e.data.get('username') for e in updates]}"
        assert mine[-1].data["confidence"] == 100, (
            f"the event carried the stale score {mine[-1].data['confidence']}, so the card would not change"
        )
        assert mine[-1].data["band"] == "confirmed"

    def test_a_rejection_is_re_scored_too(self) -> None:
        """The same staleness applied in the other direction."""
        runner, state, bus = _runner(), _state(), SessionEventBus("s1")
        candidate = self._candidate()
        state.candidates[candidate.key] = candidate
        run(
            runner._apply_answer(
                state,
                bus,
                self._confirm_question(candidate.key),
                Answer(question_id="q1", option_ids=["__no__"]),
            )
        )

        assert candidate.user_rejected is True
        assert candidate.score.value == 0, f"a rejected account still reads {candidate.score.value}"
