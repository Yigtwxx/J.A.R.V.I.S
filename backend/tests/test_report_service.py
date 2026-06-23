"""Faz 3.1 / 4.3 — exports carry the new intel sections, provenance citations,
and the public-source / authorized-use stamp (JSON, CSV, PDF)."""

import json

from app.services.report_service import report_service


def _profile() -> dict:
    return {
        "name": "Jane Doe",
        "description": "Researcher",
        "location_country": "Germany",
        "domain_intel": [{
            "domain": "janedoe.io", "registrar": "GANDI",
            "created": "2015-01-01", "confidence": 0.8,
            "source_url": "https://rdap.org/domain/janedoe.io",
            "retrieved_at": "2026-06-20T00:00:00Z",
        }],
        "sanctions_hits": [{
            "name": "Jane Doe", "list_name": "OFAC SDN", "program": "UKRAINE",
            "match_score": 0.9, "source_url": "https://sanctionssearch.ofac.treas.gov/",
        }],
        "scholarly_records": [{
            "title": "On Graphs", "year": 2021, "venue": "IEEE",
            "source_url": "https://example.org/p1", "confidence": 0.75,
        }],
        "relationships": [{
            "from": "Jane Doe", "to": "Acme", "type": "affiliation",
            "source_url": "https://opencorporates.com/acme",
        }],
        "timeline": [{
            "date": "2021-01-01T00:00:00Z", "event": "GitHub commit: fix",
            "source_url": "https://github.com/jane",
        }],
        "subject_confidence": 0.42,
        "claims": [{
            "field": "domain", "value": "janedoe.io", "corroboration_count": 1,
            "citations": [{
                "url": "https://rdap.org/domain/janedoe.io", "title": "GANDI",
                "retrieved_at": "2026-06-20T00:00:00Z", "confidence": 0.8,
            }],
        }],
        "sources": [{"title": "Src", "url": "https://src", "snippet": "x"}],
        "ai_response": "Report body.",
    }


def test_export_json_includes_intel_and_stamp():
    data = json.loads(report_service.export_json(_profile()))
    assert data["meta"]["provenance"] == "Public-source OSINT"
    assert data["meta"]["authorized_use"] == "Authorized use only"
    depth = data["intelligence_depth"]
    assert depth["domain_intel"] and depth["sanctions_hits"]
    assert depth["scholarly_records"] and depth["relationships"]
    assert depth["subject_confidence"] == 0.42
    assert data["claims"][0]["citations"][0]["url"].startswith("https://")


def test_export_csv_includes_intel_and_stamp():
    csv_out = report_service.export_csv(_profile())
    assert "Sanctions: Jane Doe" in csv_out
    assert "Publication: On Graphs" in csv_out
    assert "Domain: janedoe.io" in csv_out
    assert "Provenance: domain" in csv_out
    # Faz 4.3 provenance / authorization stamp
    assert "Public-source OSINT" in csv_out
    assert "Authorized use only" in csv_out


def test_export_pdf_generates_valid_bytes():
    """The PDF must build end-to-end with every new section present (no crash)."""
    pdf = report_service.export_pdf(_profile())
    assert isinstance(pdf, (bytes, bytearray))
    assert bytes(pdf[:4]) == b"%PDF"
    assert len(pdf) > 1000


def test_exports_never_crash_on_empty_profile():
    """Degrade gracefully when none of the new intel fields are present."""
    minimal = {"name": "Nobody", "ai_response": ""}
    assert json.loads(report_service.export_json(minimal))["meta"]["provenance"]
    assert "Public-source OSINT" in report_service.export_csv(minimal)
    assert bytes(report_service.export_pdf(minimal)[:4]) == b"%PDF"
