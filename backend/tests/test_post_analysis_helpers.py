"""Tests for post_analysis_runner pure helpers (claims/timeline/disambiguation/relationships)."""

from app.services.pipeline.post_analysis_runner import (
    _assess_disambiguation,
    _build_claims,
    _build_relationships,
    _build_timeline,
    _collect_social_urls,
)


def test_build_claims_sources_only():
    claims = _build_claims(
        structured_data={"name": "X"},
        company_records=[{"company_name": "Acme", "source_url": "https://oc/x",
                          "source_name": "OC", "confidence": 0.8}],
        data_breaches=[{"Title": "LinkedIn", "Source": "XON", "TargetEmail": "a@b.com"}],
        sanctions_hits=[{"name": "John X", "source_url": "https://ofac", "list_name": "OFAC SDN",
                         "match_score": 0.9}],
        scholarly_records=[{"title": "Paper", "source_url": "https://s2", "venue": "V",
                            "confidence": 0.7}],
        all_issues=[],
    )
    fields = {c["field"] for c in claims}
    assert {"company", "sanctions", "publication", "breach"} <= fields
    # every claim carries at least one citation with a URL
    for c in claims:
        assert c["citations"] and c["citations"][0]["url"]


def test_build_claims_conflict_lowers_corroboration():
    claims = _build_claims(
        {"name": "X"},
        [{"company_name": "Acme", "source_url": "https://oc/x", "confidence": 0.8}],
        [], [], [],
        all_issues=["Conflicting data about Acme across sources"],
    )
    company = [c for c in claims if c["field"] == "company"][0]
    assert company["corroboration_count"] == 0


def test_build_timeline_sorted_with_sources():
    tl = _build_timeline(
        github_data={"profile_url": "https://gh/u", "recent_commits": [
            {"date": "2021-01-01T00:00:00Z", "message": "fix bug", "repo": "r"}]},
        data_breaches=[{"BreachDate": "2019", "Title": "LinkedIn"}],
        company_records=[],
        archive_snapshots=[{"timestamp": "2020-01-01T00:00:00Z", "url": "http://x",
                            "snapshot_url": "https://web.archive.org/web/2020/x"}],
    )
    assert len(tl) == 3
    keys = [e["date"] for e in tl]
    assert keys == sorted(keys, key=lambda d: "".join(ch for ch in d if ch.isdigit())[:8])
    assert all("source_url" in e for e in tl)


def test_assess_disambiguation_high_confidence():
    sources = [
        {"title": "John Smith profile", "snippet": "about john smith", "url": "u1"},
        {"title": "John Smith news", "snippet": "john smith again", "url": "u2"},
    ]
    conf, alts = _assess_disambiguation("John Smith", sources, {})
    assert conf == 1.0
    assert alts == []


def test_assess_disambiguation_low_confidence_surfaces_alternatives():
    sources = [
        {"title": "Maria Gonzalez wins award", "snippet": "unrelated", "url": "u1"},
        {"title": "Robert Brown keynote", "snippet": "unrelated", "url": "u2"},
    ]
    conf, alts = _assess_disambiguation("John Smith", sources, {})
    assert conf == 0.0
    assert len(alts) >= 1
    assert all(a["source_url"] for a in alts)


def test_assess_disambiguation_no_sources():
    assert _assess_disambiguation("John Smith", [], {}) == (None, [])


def test_assess_disambiguation_social_namesake_lowers_confidence():
    """Strong web match but a divergent same-name social account must still warn."""
    sources = [
        {"title": "Yigit Erdogan profile", "snippet": "about yigit erdogan", "url": "u1"},
        {"title": "Yigit Erdogan talk", "snippet": "yigit erdogan again", "url": "u2"},
    ]
    github = {"login": "yigtwx", "name": "Yigit Erdogan", "location": "Istanbul"}
    social = {
        "instagram": [{"url": "https://instagram.com/yigtwx", "bio": "dev, Istanbul"}],
        "twitter": [{"url": "https://twitter.com/cooldoctor99", "bio": "surgeon in Berlin"}],
    }
    conf, alts = _assess_disambiguation("Yigit Erdogan", sources, {}, social, github)
    assert conf is not None and conf < 0.6, f"expected a warning-triggering confidence, got {conf}"
    assert any("twitter" in (a["name"].lower()) for a in alts), "divergent twitter account should surface"
    assert all(a["source_url"] or a["name"] for a in alts)


def test_assess_disambiguation_single_identity_unchanged():
    """When social profiles all match the anchor, only the web signal applies."""
    sources = [
        {"title": "Yigit Erdogan profile", "snippet": "about yigit erdogan", "url": "u1"},
    ]
    github = {"login": "yigtwx", "name": "Yigit Erdogan", "location": "Istanbul"}
    social = {
        "instagram": [{"url": "https://instagram.com/yigtwx", "bio": "dev"}],
        "twitter": [{"url": "https://twitter.com/yigtwx", "bio": "dev"}],
    }
    conf, alts = _assess_disambiguation("Yigit Erdogan", sources, {}, social, github)
    assert conf == 1.0, f"single consistent identity should keep web confidence, got {conf}"
    assert alts == []


def test_build_relationships_typed_edges():
    rels = _build_relationships(
        structured_data={"name": "Subject", "network_connections": [
            {"name": "Ally", "relation": "colleague"}]},
        company_records=[{"company_name": "Acme", "role": "CEO", "source_url": "https://oc/x"}],
        sanctions_hits=[{"name": "BadCo", "list_name": "OFAC SDN", "source_url": "https://ofac"}],
    )
    types = {r["type"] for r in rels}
    assert "colleague" in types
    assert "CEO" in types
    assert any(t.startswith("sanctions:") for t in types)
    assert all("from" in r and "to" in r for r in rels)


def test_collect_social_urls():
    urls = _collect_social_urls(
        {"instagram": [{"url": "https://ig/x"}], "twitter": ["https://tw/y"]},
        {"profile_url": "https://github.com/u"},
    )
    assert "https://github.com/u" in urls
    assert "https://ig/x" in urls
    assert "https://tw/y" in urls
