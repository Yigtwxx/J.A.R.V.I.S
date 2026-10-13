"""
ReportService â€” generates exportable intelligence reports in PDF, JSON, and CSV formats.

Produces classified-style dossier documents from profile search results.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.services.discovery_integration import build_report_data

if TYPE_CHECKING:  # pragma: no cover - fpdf is imported lazily inside export_pdf
    from fpdf import FPDF


class ReportService:
    """Generates export-ready intelligence reports."""

    # -- JSON Export --------------------------------------------------------

    @staticmethod
    def export_json(profile: dict[str, Any]) -> str:
        """Return a pretty-printed JSON string of the full profile."""
        export_data = {
            "meta": {
                "generated_at": datetime.now(UTC).isoformat(),
                "generator": "J.A.R.V.I.S Intelligence Platform",
                "version": "1.0.0",
                "provenance": "Public-source OSINT",
                "authorized_use": "Authorized use only",
            },
            "target": {
                "name": profile.get("name"),
                "description": profile.get("description"),
                "location_country": profile.get("location_country"),
                "location_city": profile.get("location_city"),
            },
            "social_media": _extract_social_urls(profile),
            "contact": {
                "email_addresses": profile.get("email_addresses", []),
                "phone_numbers": profile.get("phone_numbers", []),
            },
            "network_connections": profile.get("network_connections", []),
            "similar_profiles": profile.get("similar_profiles", []),
            "company_records": profile.get("company_records", []),
            "data_breaches": profile.get("data_breaches", []),
            "cross_validation_issues": profile.get("cross_validation_issues", []),
            "scores": {
                "social_media_score": profile.get("social_media_score"),
                "score_breakdown": profile.get("social_media_score_breakdown"),
                "last_activity": profile.get("last_activity_summary"),
                "platform_activity": profile.get("platform_activity"),
            },
            "sentiment_analysis": profile.get("sentiment_analysis"),
            "face_match_results": profile.get("face_match_results"),
            "ai_analysis": profile.get("ai_response"),
            "intelligence_depth": {
                "domain_intel": profile.get("domain_intel", []),
                "archive_snapshots": profile.get("archive_snapshots", []),
                "scholarly_records": profile.get("scholarly_records", []),
                "sanctions_hits": profile.get("sanctions_hits", []),
                "relationships": profile.get("relationships", []),
                "timeline": profile.get("timeline", []),
                "subject_confidence": profile.get("subject_confidence"),
                "alternative_candidates": profile.get("alternative_candidates", []),
            },
            "claims": profile.get("claims", []),
            "sources": profile.get("sources", []),
            "discovery": _discovery_json(profile),
        }
        return json.dumps(export_data, ensure_ascii=False, indent=2, default=str)

    # -- CSV Export ---------------------------------------------------------

    @staticmethod
    def export_csv(profile: dict[str, Any]) -> str:
        """Return CSV string with key profile fields (Maltego/i2 compatible)."""
        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow(
            [
                "Field",
                "Value",
                "Category",
                "Confidence",
                "Source",
            ]
        )

        name = profile.get("name", "Unknown")

        # Basic info
        writer.writerow(["Name", name, "Identity", "High", "AI Analysis"])
        if profile.get("description"):
            writer.writerow(["Description", profile["description"], "Identity", "Medium", "AI Analysis"])
        if profile.get("location_country"):
            writer.writerow(["Country", profile["location_country"], "Location", "Medium", "AI Analysis"])
        if profile.get("location_city"):
            writer.writerow(["City", profile["location_city"], "Location", "Medium", "AI Analysis"])

        # Social URLs
        for platform, url in _extract_social_urls(profile).items():
            if url:
                writer.writerow([platform, url, "Social Media", "High", "Web Scraping"])

        # Contact
        for email in profile.get("email_addresses", []):
            writer.writerow(["Email", email, "Contact", "Medium", "AI Analysis"])
        for phone in profile.get("phone_numbers", []):
            writer.writerow(["Phone", phone, "Contact", "Medium", "AI Analysis"])

        # Network connections
        for conn in profile.get("network_connections", []):
            writer.writerow(
                [
                    f"Connection: {conn.get('name', 'N/A')}",
                    f"{conn.get('role', '')} ({conn.get('relation', '')})",
                    "Network",
                    "Medium",
                    "AI Analysis",
                ]
            )

        # Company records
        for company in profile.get("company_records", []):
            writer.writerow(
                [
                    f"Company: {company.get('company_name', 'N/A')}",
                    f"{company.get('role', '')} ({company.get('status', '')})",
                    "Corporate",
                    company.get("confidence", "Medium"),
                    company.get("source_name", "Registry"),
                ]
            )

        # Breaches
        for breach in profile.get("data_breaches", []):
            writer.writerow(
                [
                    f"Breach: {breach.get('Name', breach.get('name', 'N/A'))}",
                    breach.get("BreachDate", breach.get("breach_date", "")),
                    "Security",
                    "High",
                    breach.get("Domain", breach.get("domain", "")),
                ]
            )

        # Sanctions screening (informational â€” possible name matches)
        for hit in profile.get("sanctions_hits", []):
            writer.writerow(
                [
                    f"Sanctions: {hit.get('name', 'N/A')}",
                    f"{hit.get('list_name', '')} ({hit.get('program', '')})",
                    "Sanctions",
                    hit.get("match_score", ""),
                    hit.get("source_url", ""),
                ]
            )

        # Scholarly publications
        for rec in profile.get("scholarly_records", []):
            writer.writerow(
                [
                    f"Publication: {rec.get('title', 'N/A')}",
                    str(rec.get("year", "")),
                    "Scholarly",
                    rec.get("confidence", ""),
                    rec.get("source_url", ""),
                ]
            )

        # Domain / infrastructure intel
        for dom in profile.get("domain_intel", []):
            writer.writerow(
                [
                    f"Domain: {dom.get('domain', 'N/A')}",
                    dom.get("registrar", "") or "",
                    "Infrastructure",
                    dom.get("confidence", ""),
                    dom.get("source_url", ""),
                ]
            )

        # Relationships (typed edges)
        for rel in profile.get("relationships", []):
            writer.writerow(
                [
                    f"Relationship: {rel.get('from', '')} -> {rel.get('to', '')}",
                    rel.get("type", ""),
                    "Relationship",
                    "",
                    rel.get("source_url", ""),
                ]
            )

        # Provenance â€” public-source citations behind structured claims (Faz 3.1)
        for claim in profile.get("claims", []):
            citations = claim.get("citations", []) or []
            first = citations[0] if citations else {}
            writer.writerow(
                [
                    f"Provenance: {claim.get('field', '')}",
                    claim.get("value", ""),
                    "Provenance",
                    first.get("retrieved_at", ""),
                    first.get("url", ""),
                ]
            )

        # Discovery pipeline rows — every platform outcome, refusals included.
        _discovery_csv(writer, profile)

        # Provenance / authorization stamp (Faz 4.3)
        stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        writer.writerow([])
        writer.writerow(
            [
                "# Public-source OSINT",
                f"Generated {stamp}",
                "Authorized use only",
                "",
                "",
            ]
        )

        return output.getvalue()

    # -- PDF Export ---------------------------------------------------------

    @staticmethod
    def export_pdf(profile: dict[str, Any]) -> bytes:
        """Generate a classified-style PDF dossier. Returns raw PDF bytes."""
        from fpdf import FPDF

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=20)

        name = profile.get("name", "Unknown Target")
        generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

        # --- Cover Page ---
        pdf.add_page()
        pdf.set_fill_color(15, 15, 25)
        pdf.rect(0, 0, 210, 297, "F")

        pdf.set_text_color(0, 230, 230)
        pdf.set_font("Helvetica", "B", 32)
        pdf.ln(60)
        pdf.cell(0, 15, "J.A.R.V.I.S", ln=True, align="C")

        pdf.set_font("Helvetica", "", 14)
        pdf.set_text_color(150, 150, 170)
        pdf.cell(0, 10, "INTELLIGENCE DOSSIER", ln=True, align="C")

        pdf.ln(20)
        pdf.set_draw_color(0, 230, 230)
        pdf.line(40, pdf.get_y(), 170, pdf.get_y())
        pdf.ln(15)

        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 22)
        pdf.cell(0, 12, _safe(name), ln=True, align="C")

        pdf.ln(10)
        pdf.set_font("Helvetica", "", 11)
        pdf.set_text_color(150, 150, 170)
        pdf.cell(0, 8, f"Generated: {generated}", ln=True, align="C")
        pdf.cell(0, 8, "Classification: CONFIDENTIAL", ln=True, align="C")
        pdf.cell(0, 8, "Source: Public-source OSINT", ln=True, align="C")
        pdf.cell(0, 8, "AUTHORIZED USE ONLY", ln=True, align="C")

        # --- Content Pages ---
        pdf.add_page()
        _set_page_bg(pdf)

        # Section 1: Profile Summary
        _section_header(pdf, "1. PROFILE SUMMARY")
        _field(pdf, "Name", name)
        if profile.get("description"):
            _field(pdf, "Description", profile["description"])
        if profile.get("location_country"):
            _field(pdf, "Country", profile["location_country"])
        if profile.get("location_city"):
            _field(pdf, "City", profile["location_city"])
        if profile.get("social_media_score"):
            _field(pdf, "Digital Impact Score", f"{profile['social_media_score']}/100")
        if profile.get("last_activity_summary"):
            _field(pdf, "Last Activity", profile["last_activity_summary"])
        pdf.ln(5)

        # Section 2: Social Media Presence
        social = _extract_social_urls(profile)
        active = {k: v for k, v in social.items() if v}
        if active:
            _section_header(pdf, "2. SOCIAL MEDIA PRESENCE")
            for platform, url in active.items():
                _field(pdf, platform.replace("_url", "").replace("_mention", "").capitalize(), url)
            pdf.ln(5)

        # Section 3: Contact Information
        emails = profile.get("email_addresses", [])
        phones = profile.get("phone_numbers", [])
        if emails or phones:
            _section_header(pdf, "3. CONTACT INFORMATION")
            for email in emails:
                _field(pdf, "Email", email)
            for phone in phones:
                _field(pdf, "Phone", phone)
            pdf.ln(5)

        # Section 4: Network Connections
        connections = profile.get("network_connections", [])
        if connections:
            _section_header(pdf, "4. NETWORK CONNECTIONS")
            for conn in connections:
                _field(pdf, conn.get("name", "N/A"), f"{conn.get('role', '')} - {conn.get('relation', '')}")
            pdf.ln(5)

        # Section 5: Company Records
        companies = profile.get("company_records", [])
        if companies:
            _section_header(pdf, "5. CORPORATE AFFILIATIONS")
            for comp in companies:
                _field(
                    pdf,
                    comp.get("company_name", "N/A"),
                    f"{comp.get('role', '')} | {comp.get('status', '')} | {comp.get('source_name', '')}",
                )
            pdf.ln(5)

        # Section 6: Security - Breaches
        breaches = profile.get("data_breaches", [])
        if breaches:
            _section_header(pdf, "6. DATA BREACH EXPOSURE")
            for b in breaches:
                breach_name = b.get("Name", b.get("name", "Unknown"))
                breach_date = b.get("BreachDate", b.get("breach_date", "N/A"))
                _field(pdf, breach_name, f"Date: {breach_date}")
            pdf.ln(5)

        # Section 7: Cross-Validation Issues
        issues = profile.get("cross_validation_issues", [])
        if issues:
            _section_header(pdf, "7. CROSS-VALIDATION ISSUES")
            for issue in issues:
                pdf.set_text_color(255, 180, 50)
                pdf.set_font("Helvetica", "", 10)
                pdf.multi_cell(0, 6, f"  ! {_safe(str(issue))}")
            pdf.set_text_color(220, 220, 220)
            pdf.ln(5)

        # Section 8: Sentiment Analysis
        sentiment = profile.get("sentiment_analysis")
        if sentiment:
            _section_header(pdf, "8. SENTIMENT ANALYSIS")
            _field(pdf, "Positive", f"{sentiment.get('positive', 0)}%")
            _field(pdf, "Neutral", f"{sentiment.get('neutral', 0)}%")
            _field(pdf, "Negative", f"{sentiment.get('negative', 0)}%")
            _field(pdf, "Dominant Emotion", sentiment.get("dominant_emotion", "N/A"))
            pdf.ln(5)

        # Section 9: AI Intelligence Report
        ai_response = profile.get("ai_response", "")
        if ai_response:
            _section_header(pdf, "9. AI INTELLIGENCE REPORT")
            # Strip image markdown from AI response
            import re

            clean = re.sub(r"!\[.*?\]\(.*?\)\s*", "", ai_response).strip()
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(200, 200, 210)
            # Truncate very long responses for PDF
            if len(clean) > 5000:
                clean = clean[:5000] + "\n\n[... Report truncated for PDF format ...]"
            pdf.multi_cell(0, 5, _safe(clean))
            pdf.ln(5)

        # Section 10: Sources
        sources = profile.get("sources", [])
        if sources:
            _section_header(pdf, "10. INTELLIGENCE SOURCES")
            for i, src in enumerate(sources[:20], 1):
                _field(pdf, f"[{i}] {src.get('title', 'N/A')[:60]}", src.get("url", ""))
            pdf.ln(5)

        # Section 11: Sanctions / Watchlist Screening (informational)
        sanctions = profile.get("sanctions_hits", [])
        if sanctions:
            _section_header(pdf, "11. SANCTIONS / WATCHLIST SCREENING")
            pdf.set_font("Helvetica", "I", 9)
            pdf.set_text_color(255, 180, 50)
            pdf.multi_cell(0, 5, _safe("Informational only - possible name matches, verification required."))
            pdf.set_x(pdf.l_margin)  # multi_cell leaves x at the right margin
            pdf.set_text_color(220, 220, 220)
            for hit in sanctions[:20]:
                score = hit.get("match_score")
                score_str = f" ({round(score * 100)}%)" if isinstance(score, (int, float)) else ""
                _field(pdf, hit.get("name", "N/A"), f"{hit.get('list_name', '')} | {hit.get('program', '')}{score_str}")
            pdf.ln(5)

        # Section 12: Scholarly Publications
        scholarly = profile.get("scholarly_records", [])
        if scholarly:
            _section_header(pdf, "12. SCHOLARLY PUBLICATIONS")
            for rec in scholarly[:20]:
                _field(pdf, str(rec.get("title", "N/A"))[:70], f"{rec.get('year', '')} | {rec.get('venue', '')}")
            pdf.ln(5)

        # Section 13: Domain / Infrastructure Intel
        domains = profile.get("domain_intel", [])
        if domains:
            _section_header(pdf, "13. DOMAIN / INFRASTRUCTURE INTEL")
            for dom in domains[:15]:
                _field(
                    pdf,
                    dom.get("domain", "N/A"),
                    f"Registrar: {dom.get('registrar', 'N/A')} | Created: {dom.get('created', 'N/A')}",
                )
            pdf.ln(5)

        # Section 14: Activity Timeline
        timeline = profile.get("timeline", [])
        if timeline:
            _section_header(pdf, "14. ACTIVITY TIMELINE")
            for ev in timeline[:25]:
                _field(pdf, str(ev.get("date", ""))[:10], str(ev.get("event", "")))
            pdf.ln(5)

        # Section 15: Provenance Appendix â€” public sources behind each claim (Faz 3.1)
        claims = profile.get("claims", [])
        if claims:
            _section_header(pdf, "15. PROVENANCE APPENDIX")
            for claim in claims[:40]:
                pdf.set_x(pdf.l_margin)  # multi_cell leaves x at the right margin
                pdf.set_font("Helvetica", "B", 9)
                pdf.set_text_color(0, 200, 200)
                pdf.multi_cell(0, 5, _safe(f"{claim.get('field', '')}: {claim.get('value', '')}"))
                pdf.set_font("Helvetica", "", 8)
                pdf.set_text_color(180, 180, 200)
                for c in (claim.get("citations", []) or [])[:5]:
                    conf = c.get("confidence")
                    conf_str = f" | conf {round(conf * 100)}%" if isinstance(conf, (int, float)) else ""
                    pdf.set_x(pdf.l_margin)
                    pdf.multi_cell(0, 5, _safe(f"   - {c.get('url', '')} ({c.get('retrieved_at', '')}{conf_str})"))
            pdf.ln(5)

        # Sections 16-21: discovery pipeline output (statuses, avatars, work,
        # evidence, namesakes, caveats).
        _discovery_pdf(pdf, profile)

        # Footer on all pages
        for page_num in range(1, pdf.pages_count + 1):
            pdf.page = page_num
            pdf.set_y(-15)
            pdf.set_font("Helvetica", "I", 8)
            pdf.set_text_color(100, 100, 120)
            pdf.cell(
                0, 10, f"J.A.R.V.I.S Intelligence Platform | Page {page_num}/{pdf.pages_count} | {generated}", align="C"
            )

        return bytes(pdf.output())


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

_SOCIAL_FIELDS = [
    "github_url",
    "instagram_url",
    "twitter_url",
    "linkedin_url",
    "spotify_url",
    "tiktok_url",
    "snapchat_url",
    "tumblr_url",
    "youtube_url",
    "reddit_url",
    "facebook_url",
    "pinterest_url",
    "threads_url",
    "steam_url",
    "tinder_mention",
    "bumble_mention",
    "discord_mention",
]


def _extract_social_urls(profile: dict) -> dict[str, str]:
    return {k: profile[k] for k in _SOCIAL_FIELDS if profile.get(k)}


def _safe(text: str) -> str:
    """Replace characters that latin-1 (fpdf default) can't encode."""
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _set_page_bg(pdf: FPDF) -> None:
    pdf.set_fill_color(20, 20, 32)
    pdf.rect(0, 0, 210, 297, "F")


def _section_header(pdf: FPDF, title: str) -> None:
    # Check remaining space, add page if needed
    if pdf.get_y() > 250:
        pdf.add_page()
        _set_page_bg(pdf)
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(0, 230, 230)
    pdf.cell(0, 10, _safe(title), ln=True)
    pdf.set_draw_color(0, 230, 230)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(3)


def _field(pdf: FPDF, label: str, value: str) -> None:
    if pdf.get_y() > 270:
        pdf.add_page()
        _set_page_bg(pdf)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(0, 200, 200)
    pdf.cell(50, 6, _safe(label + ":"), ln=False)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(220, 220, 220)
    # Handle long values with multi_cell
    if len(str(value)) > 80:
        pdf.ln()
        pdf.set_x(15)
        pdf.multi_cell(180, 5, _safe(str(value)))
    else:
        pdf.cell(0, 6, _safe(str(value)[:120]), ln=True)


# ---------------------------------------------------------------------------
# Discovery pipeline sections
#
# A `blocked` or `not_found` platform is rendered here with its status_detail
# rather than skipped. Dropping it would make a refusal indistinguishable from
# "no such account", which is the silently-empty failure this pipeline replaced.
# ---------------------------------------------------------------------------


def _discovery_json(profile: dict[str, Any]) -> dict[str, Any]:
    """Discovery sections for the JSON export. Local avatar paths are stripped:
    an exported dossier should not carry our filesystem layout."""
    data = build_report_data(profile)
    return {
        "social_profiles": data.social,
        "profile_pictures": [{k: v for k, v in pic.items() if k != "path"} for pic in data.pictures],
        "work_history": data.work,
        "education": data.education,
        "evidence": data.evidence,
        "notices": data.notices,
    }


def _discovery_csv(writer: Any, profile: dict[str, Any]) -> None:
    """Append the discovery rows to an in-progress CSV export."""
    data = build_report_data(profile)

    for row in data.social:
        writer.writerow(
            [
                f"Profile: {row['platform']}",
                row.get("url") or row.get("username") or "",
                f"Social Media ({row['status']})",
                f"{row['confidence']} ({row['band']})",
                row.get("status_detail") or "",
            ]
        )
    for row in data.work:
        writer.writerow(
            [
                f"Work: {row.get('organization', '')}",
                f"{row.get('role') or ''} {row.get('start') or ''}-{row.get('end') or ''}".strip(),
                "Employment",
                row.get("confidence", ""),
                row.get("source_url", ""),
            ]
        )
    for row in data.education:
        writer.writerow(
            [
                f"Education: {row.get('institution', '')}",
                f"{row.get('degree') or ''} {row.get('field_of_study') or ''}".strip(),
                "Education",
                row.get("confidence", ""),
                row.get("source_url", ""),
            ]
        )
    for row in data.evidence:
        writer.writerow(
            [
                f"Evidence: {row.get('kind', '')}",
                str(row.get("value", ""))[:200],
                "Evidence",
                row.get("confidence", ""),
                row.get("source_url", ""),
            ]
        )
    for notice in data.notices:
        writer.writerow(["Notice", notice, "Search caveat", "", ""])


def _discovery_pdf(pdf: FPDF, profile: dict[str, Any]) -> None:
    """Render the discovery sections into an in-progress PDF dossier."""
    data = build_report_data(profile)

    if data.social:
        _section_header(pdf, "16. PLATFORM STATUS")
        for row in data.social:
            detail = f" - {row['status_detail']}" if row.get("status_detail") else ""
            _field(
                pdf,
                f"{row['platform']} [{row['status']}]",
                f"{row.get('url') or row.get('username') or 'n/a'} | {row['confidence']}% ({row['band']}){detail}",
            )
        pdf.ln(5)

    if any(pic.get("path") for pic in data.pictures):
        _section_header(pdf, "17. PROFILE PICTURES")
        _pictures_grid(pdf, data.pictures)

    if data.work or data.education:
        _section_header(pdf, "18. WORK & EDUCATION")
        for row in data.work:
            _field(
                pdf,
                str(row.get("organization", ""))[:40],
                f"{row.get('role') or 'n/a'} | {row.get('start') or '?'}-{row.get('end') or 'present'} | {row.get('source_url', '')}",
            )
        for row in data.education:
            _field(
                pdf,
                str(row.get("institution", ""))[:40],
                f"{row.get('degree') or 'n/a'} {row.get('field_of_study') or ''} | {row.get('start') or '?'}-{row.get('end') or '?'} | {row.get('source_url', '')}",
            )
        pdf.ln(5)

    if data.evidence:
        _section_header(pdf, "19. EVIDENCE APPENDIX")
        for row in data.evidence[:60]:
            conf = row.get("confidence")
            conf_str = f"{round(conf * 100)}%" if isinstance(conf, (int, float)) else str(conf or "")
            _field(
                pdf,
                str(row.get("kind", ""))[:30],
                f"{str(row.get('value', ''))[:90]} | {row.get('source_domain', '')} | {conf_str}",
            )
        pdf.ln(5)

    if data.notices:
        _section_header(pdf, "20. SEARCH NOTICES")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(255, 180, 50)
        for notice in data.notices:
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 5, _safe(f"  ! {notice}"))
        pdf.set_text_color(220, 220, 220)
        pdf.ln(5)


def _pictures_grid(pdf: FPDF, pictures: list[dict[str, Any]]) -> None:
    """Embed the downloaded avatar files, five per row.

    A picture that will not decode is skipped: a corrupt or truncated file in
    `data/avatars` must cost the reader one thumbnail, not the whole export.
    """
    size, gap = 28.0, 6.0
    x, y = float(pdf.l_margin), pdf.get_y()
    drawn = False

    for pic in pictures:
        path = pic.get("path")
        if not path:
            continue
        if x + size > 195:
            x, y = float(pdf.l_margin), y + size + 8
        if y + size > 260:
            pdf.add_page()
            _set_page_bg(pdf)
            x, y = float(pdf.l_margin), pdf.get_y()
        try:
            pdf.image(path, x=x, y=y, w=size, h=size)
        except Exception:  # noqa: BLE001 - any decode failure just drops one thumbnail
            continue
        pdf.set_xy(x, y + size + 1)
        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(180, 180, 200)
        pdf.cell(size, 4, _safe(str(pic.get("platform", ""))[:14]))
        x += size + gap
        drawn = True

    pdf.set_y(y + size + 10 if drawn else y)
    pdf.set_x(pdf.l_margin)


# Singleton
report_service = ReportService()
