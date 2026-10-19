"""Invariant 4 for the browse tier: every claim traces to the document.

This is the file that matters most in the feature. An agent that can roam a page
and talk afterwards is the easiest way ever invented to manufacture a biography,
so the rules below are the ones that must not be allowed to rot:

* the model writes nothing into the journal — it manoeuvres, the extractor reads;
* a value the harvested HTML never contained is dropped, and counted;
* "this account exists" needs a 2xx and a URL that still names the same handle;
* a browse-derived fact is labelled ``browse`` and discounted, so nothing
  downstream can mistake it for a plain profile fetch.
"""

from app.discovery.browse.harvest import (
    BROWSE_CONFIDENCE_MULTIPLIER,
    discounted,
    ground,
    may_claim_profile,
    status_for,
    to_fetch_result,
)
from app.discovery.browse.types import BrowseOutcome, BrowseReport, BrowseTask
from app.discovery.evidence.model import make_evidence
from app.discovery.types import EvidenceKind, FetchStatus, FetchTier, SourceKind

PAGE = "<html><body><h1>Jane Doe</h1><p>Photographer based in Istanbul. Works at Acme Studio.</p></body></html>"

TASK = BrowseTask(
    task_id="t1",
    url="https://www.instagram.com/janedoe/",
    platform="instagram",
    username="janedoe",
    reason="stealth tier was refused",
)


def _report(**kwargs) -> BrowseReport:
    defaults = {
        "task": TASK,
        "outcome": BrowseOutcome.EXTRACTED,
        "html": PAGE,
        "final_url": "https://www.instagram.com/janedoe/",
        "http_status": 200,
    }
    defaults.update(kwargs)
    return BrowseReport(**defaults)


def _evidence(kind: EvidenceKind, value: str, confidence: float = 0.7):
    return make_evidence(
        kind,
        "subject",
        value,
        source_url=TASK.url,
        source_kind=SourceKind.BROWSE,
        extractor="browse",
        confidence=confidence,
        platform="instagram",
    )


# -- the grounding filter ------------------------------------------------------


def test_a_value_the_page_contained_survives():
    kept, dropped = ground([_evidence(EvidenceKind.LOCATION, "Istanbul")], PAGE)

    assert dropped == 0, f"a real value was dropped; kept={len(kept)}"
    assert len(kept) == 1


def test_a_value_the_page_never_contained_is_dropped_and_counted():
    """The fabrication case. It must not merely be filtered — it must be visible."""
    fabricated = _evidence(EvidenceKind.EMPLOYER, "Goldman Sachs")

    kept, dropped = ground([fabricated], PAGE)

    assert kept == [], f"a fabricated employer survived: {kept}"
    assert dropped == 1, f"the drop was not counted, got {dropped}"


def test_grounding_ignores_case_and_accents():
    kept, dropped = ground([_evidence(EvidenceKind.REAL_NAME, "JANE DOE")], PAGE)

    assert dropped == 0, "a case difference was treated as a fabrication"
    assert len(kept) == 1


def test_a_structural_value_is_not_subjected_to_the_text_test():
    """The canonical profile URL need not appear in the body it describes."""
    kept, dropped = ground([_evidence(EvidenceKind.PROFILE, TASK.url)], PAGE)

    assert dropped == 0, "the profile URL was treated as an ungrounded claim"
    assert len(kept) == 1


def test_an_empty_document_grounds_nothing_textual():
    kept, dropped = ground([_evidence(EvidenceKind.BIO, "Photographer")], "")

    assert kept == [], f"a claim survived an empty document: {kept}"
    assert dropped == 1


# -- the existence carve-out ---------------------------------------------------


def test_a_matching_2xx_page_may_claim_the_account_exists():
    assert may_claim_profile(_report()) is True, "a clean extraction was not allowed to claim existence"


def test_a_browse_that_ended_somewhere_else_may_not_claim_the_account():
    """An agent that followed a "related accounts" card must not hand back a stranger."""
    report = _report(final_url="https://www.instagram.com/someone.else/")

    assert may_claim_profile(report) is False, "a different handle was accepted as the target"


def test_a_non_2xx_page_may_not_claim_the_account_exists():
    report = _report(http_status=403)

    assert may_claim_profile(report) is False, "a refused page was read as an existence proof"


def test_an_outcome_short_of_extracted_may_not_claim_the_account():
    for outcome in (
        BrowseOutcome.REACHED_EMPTY,
        BrowseOutcome.LOGIN_WALL,
        BrowseOutcome.STEP_BUDGET,
        BrowseOutcome.STOPPED,
    ):
        report = _report(outcome=outcome)
        assert may_claim_profile(report) is False, f"{outcome} was allowed to claim existence"


# -- invariant 1: statuses ------------------------------------------------------


def test_no_outcome_but_a_real_404_maps_to_not_found():
    """Every other way a browse can fail must stay distinguishable from absence."""
    for outcome in BrowseOutcome:
        status = status_for(outcome)
        if outcome is BrowseOutcome.NOT_FOUND:
            assert status is FetchStatus.NOT_FOUND, f"{outcome} should be NOT_FOUND"
        else:
            assert status is not FetchStatus.NOT_FOUND, f"{outcome} was mapped to NOT_FOUND"


def test_a_login_wall_carries_a_named_block_signal():
    result = to_fetch_result(_report(outcome=BrowseOutcome.LOGIN_WALL))

    assert result.status is FetchStatus.BLOCKED, f"got {result.status}"
    assert result.block_signal == "browse_login_wall", f"got {result.block_signal!r}"


def test_a_user_stop_is_blocked_and_says_who_stopped_it():
    result = to_fetch_result(_report(outcome=BrowseOutcome.STOPPED))

    assert result.status is FetchStatus.BLOCKED, f"got {result.status}"
    assert result.block_signal == "browse_stopped_by_user", f"got {result.block_signal!r}"


# -- the synthetic result -------------------------------------------------------


def test_the_harvested_result_admits_which_tier_produced_it():
    """Claiming the stealth tier returned these bytes would be a small lie."""
    result = to_fetch_result(_report())

    assert result.tier is FetchTier.BROWSE, f"got {result.tier}"
    assert result.ok, "a good extraction did not produce a parseable result"
    assert result.html == PAGE


def test_a_result_with_no_document_is_an_error_not_an_ok():
    result = to_fetch_result(_report(html=""))

    assert not result.ok, "an empty harvest was reported as a usable document"
    assert result.status is FetchStatus.ERROR, f"got {result.status}"


# -- weighting ------------------------------------------------------------------


def test_a_browse_derived_fact_is_discounted_against_a_direct_fetch():
    assert discounted(0.8) < 0.8, "browse evidence was not discounted at all"
    assert discounted(0.8) == 0.8 * BROWSE_CONFIDENCE_MULTIPLIER


def test_the_discount_never_leaves_the_range_the_journal_expects():
    assert discounted(1.0) <= 1.0
    assert discounted(-5.0) == 0.0, "a negative confidence escaped the clamp"
