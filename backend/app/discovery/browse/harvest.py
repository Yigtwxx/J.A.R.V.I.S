"""Turning a finished browse into evidence — the invariant-4 gate.

The rule this module exists to enforce, stated once:

    **A browse step may write nothing into the evidence journal. Only the
    terminal harvest may, and it runs through the pipeline's existing
    extractors, unchanged.**

Which is why there is no parsing here. The model's ``thought`` and any text it
read off a screenshot are provenance — they reach the event stream and the panel
and stop there. What becomes a claim is what ``ProfileExtractor`` reads out of
the HTML the page actually held, and every value it produces is then checked
against those same bytes. A value the document never contained is dropped and
**counted**, because a filter nobody can see is a filter nobody can falsify.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.discovery.browse.types import BrowseOutcome, BrowseReport
from app.discovery.evidence.model import Evidence
from app.discovery.fetch.result import FetchResult
from app.discovery.identity.normalize import fold_ascii
from app.discovery.platforms.urlmatch import match_profile_url
from app.discovery.types import EvidenceKind, FetchStatus, FetchTier
from app.utils.logger import logger

BROWSE_CONFIDENCE_MULTIPLIER = 0.85
"""How much a browse-derived fact is discounted against the same fact from a
plain GET.

The *parse* is not weaker — it is the identical extractor on identical bytes.
The *navigation* is: an agent may have followed a card, expanded a section or
landed somewhere adjacent, so the URL-to-identity binding is one step less
certain than a canonical profile fetch. Small, because only one of the two
halves is degraded. A module constant rather than a setting on purpose: this
must not be tunable into dishonesty."""

#: Kinds whose value is a fact *stated by the document*, and must therefore be
#: found in it. ``PROFILE`` and ``USERNAME`` are excluded because neither is a
#: claim the page made — the first is governed by :func:`may_claim_profile`, the
#: second is the handle we went looking for.
_GROUNDED_KINDS: frozenset[EvidenceKind] = frozenset(
    {
        EvidenceKind.REAL_NAME,
        EvidenceKind.BIO,
        EvidenceKind.LOCATION,
        EvidenceKind.EMPLOYER,
        EvidenceKind.SCHOOL,
        EvidenceKind.EMAIL,
        EvidenceKind.PHONE,
    }
)

_OUTCOME_STATUS: dict[BrowseOutcome, FetchStatus] = {
    BrowseOutcome.EXTRACTED: FetchStatus.OK,
    BrowseOutcome.REACHED_EMPTY: FetchStatus.OK,
    BrowseOutcome.NOT_FOUND: FetchStatus.NOT_FOUND,
    BrowseOutcome.LOGIN_WALL: FetchStatus.BLOCKED,
    BrowseOutcome.CHALLENGE: FetchStatus.BLOCKED,
    BrowseOutcome.STOPPED: FetchStatus.BLOCKED,
    BrowseOutcome.UNAVAILABLE: FetchStatus.BLOCKED,
    BrowseOutcome.REFUSED: FetchStatus.ERROR,
    BrowseOutcome.STALLED: FetchStatus.ERROR,
    BrowseOutcome.STEP_BUDGET: FetchStatus.TIMEOUT,
    BrowseOutcome.TIME_BUDGET: FetchStatus.TIMEOUT,
    BrowseOutcome.MODEL_UNAVAILABLE: FetchStatus.ERROR,
    BrowseOutcome.ERROR: FetchStatus.ERROR,
}

_BLOCK_SIGNALS: dict[BrowseOutcome, str] = {
    BrowseOutcome.LOGIN_WALL: "browse_login_wall",
    BrowseOutcome.CHALLENGE: "browse_challenge",
    BrowseOutcome.STOPPED: "browse_stopped_by_user",
    BrowseOutcome.UNAVAILABLE: "browse_unavailable",
}


def status_for(outcome: BrowseOutcome) -> FetchStatus:
    """Fetch status for an outcome. Never ``NOT_FOUND`` unless a code said so."""
    return _OUTCOME_STATUS.get(outcome, FetchStatus.ERROR)


def _selector(html: str) -> Any | None:
    """Parse HTML the way the rest of the pipeline does, or give up quietly.

    Imported here rather than at module scope because scrapling is a soft
    dependency everywhere else in ``discovery/`` and this module is imported by
    tests that never need a parser.
    """
    if not html:
        return None
    try:
        from scrapling.parser import Selector
    except Exception as exc:  # pragma: no cover - only without scrapling installed
        logger.log_warning(f"Browse harvest cannot parse without scrapling: {exc}", broadcast=False)
        return None
    try:
        return Selector(html)
    except Exception as exc:
        logger.log_warning(f"Browse harvest could not build a selector: {exc}", broadcast=False)
        return None


def to_fetch_result(report: BrowseReport) -> FetchResult:
    """The document the browse ended on, as the pipeline's own result type.

    Tagged ``FetchTier.BROWSE`` rather than ``STEALTH``: claiming the stealth
    tier produced this would be a small lie of exactly the kind invariant 1
    exists to prevent, since a plain GET of the same URL would not have returned
    these bytes.
    """
    status = status_for(report.outcome)
    page = _selector(report.html) if status is FetchStatus.OK else None
    if status is FetchStatus.OK and page is None:
        status = FetchStatus.ERROR

    return FetchResult(
        url=report.task.url,
        final_url=report.final_url or report.task.url,
        status=status,
        http_status=report.http_status,
        html=report.html or None,
        page=page,
        tier=FetchTier.BROWSE,
        attempts=max(1, report.steps_used),
        elapsed_ms=report.duration_ms,
        error=report.detail if status is FetchStatus.ERROR else None,
        block_signal=_BLOCK_SIGNALS.get(report.outcome),
    )


def may_claim_profile(report: BrowseReport) -> bool:
    """Whether this browse is allowed to assert that the account exists.

    Three conditions, all structural, none of them the model's opinion:

    1. something was actually extracted;
    2. the main-frame navigation answered 2xx — a wall or a redirect chain is
       not an existence proof;
    3. the URL we ended on still resolves to the *same* handle we set out to
       read. An agent that wandered onto a "related accounts" card would
       otherwise hand back a stranger's profile under the target's name.
    """
    if report.outcome is not BrowseOutcome.EXTRACTED:
        return False
    if report.http_status is None or not (200 <= report.http_status < 300):
        return False

    match = match_profile_url(report.final_url or report.task.url)
    if match is None:
        return False
    return match.platform == report.task.platform and match.username.lower() == (report.task.username or "").lower()


def ground(evidence: Sequence[Evidence], html: str) -> tuple[list[Evidence], int]:
    """Keep only what the document actually contained. Return the kept and the count dropped.

    Blunt on purpose — a substring test over folded text. A stricter check would
    reject legitimate values that the page renders across elements; a looser one
    would stop being a check.
    """
    folded = fold_ascii(html or "").casefold()
    kept: list[Evidence] = []
    dropped = 0

    for item in evidence:
        if item.kind not in _GROUNDED_KINDS:
            kept.append(item)
            continue
        # `raw["display"]` is the value as the page wrote it, which is the only
        # form a substring test can find once the value has been normalised.
        # Without it a phone stored as E.164 could never be grounded against the
        # page that published it in national form.
        written = str((item.raw or {}).get("display") or "") or item.value
        value = fold_ascii(written or "").casefold().strip()
        if value and value in folded:
            kept.append(item)
        else:
            dropped += 1

    if dropped:
        logger.log_warning(
            f"Browse harvest dropped {dropped} value(s) the page never contained",
            broadcast=False,
        )
    return kept, dropped


def discounted(confidence: float) -> float:
    """Apply the browse discount, clamped to the 0..1 the journal expects."""
    return max(0.0, min(1.0, confidence * BROWSE_CONFIDENCE_MULTIPLIER))
