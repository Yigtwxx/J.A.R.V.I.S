"""Faz 3.3 — the version diff surfaces new intel (domain/sanction/etc.) via
timestamp-free signatures, and does NOT churn on `retrieved_at` changes."""

from datetime import UTC, datetime, timedelta

from app.services import version_history_service as vh


def _snap(domains, retrieved="2026-06-20T00:00:00Z") -> dict:
    return {
        "name": "Jane Doe",
        "domain_intel": [
            {
                "domain": d,
                "source_url": f"https://rdap.org/domain/{d}",
                "retrieved_at": retrieved,
                "confidence": 0.8,
            }
            for d in domains
        ],
    }


def _backdate(snapshot, hours: int, db_session) -> None:
    """SQLite func.now() is second-precision; force an earlier captured_at so the
    snapshot ordering in generate_change_report is deterministic."""
    snapshot.captured_at = datetime.now(UTC) - timedelta(hours=hours)
    db_session.flush()


def test_new_domain_surfaces_in_diff(db_session):
    first = vh.save_snapshot(db_session, "jane doe", _snap(["example.com"]))
    _backdate(first, 1, db_session)
    vh.save_snapshot(db_session, "jane doe", _snap(["example.com", "newco.io"]))

    report = vh.generate_change_report(db_session, "jane doe")
    assert report is not None and report.has_changes
    changed = {c.field: c for c in report.changes}
    assert "domain_intel_sig" in changed
    assert "newco.io" in (changed["domain_intel_sig"].new_value or "")


def test_timestamp_only_change_produces_no_diff(db_session):
    first = vh.save_snapshot(
        db_session, "jane doe", _snap(["example.com"], retrieved="2026-06-19T00:00:00Z")
    )
    _backdate(first, 1, db_session)
    vh.save_snapshot(
        db_session, "jane doe", _snap(["example.com"], retrieved="2026-06-20T11:11:11Z")
    )

    report = vh.generate_change_report(db_session, "jane doe")
    assert report is not None
    fields = {c.field for c in report.changes}
    # retrieved_at-only churn must NOT register as a meaningful change
    assert "domain_intel_sig" not in fields


def test_intel_signatures_are_timestamp_free():
    a = vh._intel_signatures(lambda k: _snap(["a.com"], retrieved="2020-01-01").get(k))
    b = vh._intel_signatures(lambda k: _snap(["a.com"], retrieved="2026-12-31").get(k))
    assert a["domain_intel_sig"] == b["domain_intel_sig"] == "a.com"
