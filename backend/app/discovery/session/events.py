"""The wire protocol between a running discovery session and the browser.

Every event is a *named* SSE event (``event: question``) so the frontend can bind
one handler per kind with ``addEventListener``, and carries an ``id:`` line so a
reconnecting client can hand back a ``Last-Event-ID`` and be replayed exactly the
events it missed.

The ``data:`` line holds the **whole** event, not just its payload. That is
deliberate: ``frontend/services/api.ts`` reads the stream with ``fetch`` and a
manual reader (the native ``EventSource`` cannot send the ``X-API-Key`` header),
and that reader keeps only the ``data:`` lines. A payload-only body would reach
that parser stripped of its type and sequence number. Self-describing JSON works
with both consumers at once.

The JSON is always a single line — ``json.dumps`` escapes embedded newlines — so
an event body can never be mistaken for the blank line that terminates it.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:  # pragma: no cover - typing only, keeps this module import-light
    from app.discovery.evidence.model import Evidence
    from app.discovery.hitl.questions import Question
    from app.discovery.matching.candidate import ProfileCandidate
    from app.discovery.narrative.grounding import Claim
    from app.discovery.platforms.existence import ExistenceResult

# A single evidence value can be a whole bio. The stream is for progress, not
# for bulk transfer: the full text is in the final result and in the database.
_MAX_VALUE_CHARS = 300

PHASES: tuple[str, ...] = ("seed", "expand", "verify", "enrich", "browse", "score", "reflect", "finalize")


def utc_now_iso() -> str:
    """Second-precision ISO8601 in UTC, e.g. ``2026-08-11T10:02:11Z``."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class EventType(StrEnum):
    """Every kind of thing a session can tell the client about."""

    hello = "hello"
    progress = "progress"
    round_started = "round_started"
    round_finished = "round_finished"
    evidence_found = "evidence_found"
    platform_status = "platform_status"
    candidate_updated = "candidate_updated"
    anchor_changed = "anchor_changed"
    result_invalidated = "result_invalidated"
    question = "question"
    answer_received = "answer_received"

    browse_started = "browse_started"
    """A driven browser opened a page. The console shows it live from here."""

    browse_step = "browse_step"
    """One action and the frame it produced. The only browse event in
    `bus._DROPPABLE`: losing one degrades an animation, where losing a
    `browse_started` leaves the panel closed over work the user cannot see and
    losing a `browse_finished` leaves it open over work that already ended."""

    browse_finished = "browse_finished"
    """How the browse ended, and every count that matters — repeated here rather
    than accumulated from steps precisely because steps may be dropped."""

    narrative_delta = "narrative_delta"
    """One sentence of the biography, published as it is written.

    Emitted only *after* the sentence has passed the same grounding gate the
    final report applies, so a sentence on the wire is a sentence in the result:
    the stream can never show prose the evidence does not carry, which is the
    whole reason the biography was not streamed before.

    Never in `bus._DROPPABLE`. `progress` is superseded by the next tick and
    `browse_step` by `browse_finished`; a delta has no successor that repeats it,
    and `replay()` filters the ring by seq without knowing what a subscriber was
    actually offered — so a dropped delta is a hole in the biography that a
    `Last-Event-ID` reconnect cannot fill."""

    log = "log"
    """Console telemetry. Never published by the loop itself, but named here
    because `bus._DROPPABLE` needs it: it is what a saturated subscriber queue is
    allowed to discard instead of a `question` the loop is suspended on."""

    done = "done"
    error = "error"


class SearchEvent(BaseModel):
    """One frame on the wire."""

    v: int = 1
    seq: int
    session_id: str
    ts: str = Field(default_factory=utc_now_iso)
    type: EventType
    data: dict[str, Any] = {}

    def to_sse(self) -> str:
        """Serialise to ``id: <seq>\\nevent: <type>\\ndata: <json>\\n\\n``."""
        body = json.dumps(self.model_dump(mode="json"), ensure_ascii=False, default=str)
        return f"id: {self.seq}\nevent: {self.type.value}\ndata: {body}\n\n"


# -- payload builders --------------------------------------------------------
# Key names are part of the contract with the frontend; do not rename them.


def hello_payload(
    session_id: str,
    query: str,
    entity_type: str,
    depth: int,
    interactive: bool,
    resumed_evidence: int,
    started_at: str,
) -> dict[str, Any]:
    """The opening frame: what this session is and what it inherited."""
    return {
        "session_id": session_id,
        "query": query,
        "entity_type": str(entity_type),
        "depth": depth,
        "interactive": interactive,
        "resumed_evidence": resumed_evidence,
        "started_at": started_at,
    }


def progress_payload(phase: str, round: int, label: str, completed: int, total: int) -> dict[str, Any]:
    """Where the round is. ``pct`` is derived so the client never divides by zero."""
    pct = int(completed * 100 / total) if total > 0 else 0
    return {
        "phase": phase,
        "round": round,
        "label": label,
        "completed": completed,
        "total": total,
        "pct": max(0, min(100, pct)),
    }


def round_started_payload(round: int, planned_queries: int, planned_checks: int) -> dict[str, Any]:
    return {"round": round, "planned_queries": planned_queries, "planned_checks": planned_checks}


def round_finished_payload(
    round: int,
    new_evidence: int,
    new_candidates: int,
    blocked_platforms: int,
    dry_rounds: int,
    duration_ms: int,
) -> dict[str, Any]:
    """``dry_rounds`` is the termination signal: consecutive rounds that learned nothing."""
    return {
        "round": round,
        "new_evidence": new_evidence,
        "new_candidates": new_candidates,
        "blocked_platforms": blocked_platforms,
        "dry_rounds": dry_rounds,
        "duration_ms": duration_ms,
    }


def evidence_payload(ev: Evidence) -> dict[str, Any]:
    return {
        "kind": str(ev.kind),
        "subject": ev.subject,
        "value": ev.value[:_MAX_VALUE_CHARS],
        "platform": ev.platform,
        "source_url": ev.source_url,
        "source_domain": ev.source_domain,
        "confidence": round(ev.confidence, 3),
        "fingerprint": ev.fingerprint,
    }


def narrative_delta_payload(index: int, claim: Claim, source: str) -> dict[str, Any]:
    """One grounded sentence. ``source`` is ``"model"`` or ``"template"``.

    ``text`` is deliberately not truncated the way ``evidence_payload`` truncates
    a value: this string is what the panel renders, and a clipped sentence would
    render as clipped prose that disagrees with the stored result.
    """
    return {
        "index": index,
        "text": claim.text,
        "evidence_fingerprints": list(claim.evidence_fingerprints),
        "source_urls": list(claim.source_urls),
        "confidence": claim.confidence,
        "source": source,
    }


def platform_status_payload(result: ExistenceResult) -> dict[str, Any]:
    """A per-platform verdict. ``blocked`` is reported, never hidden as "not found"."""
    return {
        "platform": result.platform,
        "username": result.username,
        "status": str(result.verdict),
        "detail": result.detail,
        "signals": list(result.signals),
    }


def candidate_payload(c: ProfileCandidate) -> dict[str, Any]:
    return {
        "platform": c.platform,
        "username": c.username,
        "url": c.url,
        "status": str(c.platform_status),
        "confidence": c.score.value,
        "band": str(c.score.band),
        "reasons": [r.as_dict() for r in c.score.reasons[:3]],
        "avatar_url": c.avatar_local_url,
    }


def question_payload(q: Question) -> dict[str, Any]:
    """A question the loop is now blocked on, with no deadline attached.

    ``options`` already carries the implicit "I don't know", so the UI renders it
    like any other choice. There is deliberately no ``timeout_seconds``: the
    client cannot show a countdown for a wait that does not end on its own.
    """
    return {
        "id": q.id,
        "kind": str(q.kind),
        "text": q.text,
        "options": q.wire_options(),
        "allow_free_text": q.allow_free_text,
        "allow_unknown": q.allow_unknown,
        "context": dict(q.context),
        # `subject_url` and each option's `url` are what let the card offer a way
        # to go and look. Judging an account from a handle and a thumbnail is a
        # guess; opening it is the only way to actually answer.
        "subject_url": q.subject_url,
        "multi_select": q.multi_select,
    }


def anchor_changed_payload(from_handle: str, to_handle: str, reason: str, round: int) -> dict[str, Any]:
    """The search changed its mind about who the subject is."""
    return {"from_handle": from_handle, "to_handle": to_handle, "reason": reason, "round": round}


def result_invalidated_payload(reason: str, discarded: list[str]) -> dict[str, Any]:
    """Findings collected under the previous anchor are being thrown away, named."""
    return {"reason": reason, "discarded": list(discarded), "count": len(discarded)}


def done_payload(termination_reason: str, rounds: int, duration_ms: int, summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "termination_reason": termination_reason,
        "rounds": rounds,
        "duration_ms": duration_ms,
        "summary": dict(summary),
    }


def error_payload(message: str, fatal: bool, hint: str | None = None) -> dict[str, Any]:
    return {"message": message, "fatal": fatal, "hint": hint}


def browse_started_payload(
    task_id: str,
    url: str,
    platform: str,
    username: str,
    reason: str,
    max_steps: int,
    max_seconds: float,
) -> dict[str, Any]:
    """A browse task began. ``reason`` says why this target earned a browser."""
    return {
        "task_id": task_id,
        "url": url,
        "platform": platform,
        "username": username,
        "reason": reason,
        "max_steps": max_steps,
        "max_seconds": max_seconds,
    }


def browse_step_payload(task_id: str, step: dict[str, Any]) -> dict[str, Any]:
    """One step, as the agent already described it. ``by`` is ``rule`` or ``model``."""
    return {"task_id": task_id, **step}


def browse_finished_payload(
    task_id: str,
    outcome: str,
    detail: str,
    steps_used: int,
    duration_ms: int,
    model_calls: int,
    evidence_added: int,
    dropped_ungrounded: int,
) -> dict[str, Any]:
    """The closing frame.

    ``dropped_ungrounded`` is on the wire on purpose: the harvest refuses any
    value the page did not contain, and a filter the user cannot see is a filter
    nobody can check.
    """
    return {
        "task_id": task_id,
        "outcome": outcome,
        "detail": detail,
        "steps_used": steps_used,
        "duration_ms": duration_ms,
        "model_calls": model_calls,
        "evidence_added": evidence_added,
        "dropped_ungrounded": dropped_ungrounded,
    }
