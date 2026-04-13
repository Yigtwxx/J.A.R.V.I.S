"""
ReportService — generates exportable intelligence reports in PDF, JSON, and CSV formats.

Produces classified-style dossier documents from profile search results.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime
from typing import Any


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
            "sources": profile.get("sources", []),
        }
        return json.dumps(export_data, ensure_ascii=False, indent=2, default=str)

    # -- CSV Export ---------------------------------------------------------

    @staticmethod
    def export_csv(profile: dict[str, Any]) -> str:
        """Return CSV string with key profile fields (Maltego/i2 compatible)."""
        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow([
            "Field", "Value", "Category", "Confidence", "Source",
        ])

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
            writer.writerow([
                f"Connection: {conn.get('name', 'N/A')}",
                f"{conn.get('role', '')} ({conn.get('relation', '')})",
                "Network", "Medium", "AI Analysis",
            ])

        # Company records
        for company in profile.get("company_records", []):
            writer.writerow([
                f"Company: {company.get('company_name', 'N/A')}",
                f"{company.get('role', '')} ({company.get('status', '')})",
                "Corporate", company.get("confidence", "Medium"),
                company.get("source_name", "Registry"),
            ])

        # Breaches
        for breach in profile.get("data_breaches", []):
            writer.writerow([
                f"Breach: {breach.get('Name', breach.get('name', 'N/A'))}",
                breach.get("BreachDate", breach.get("breach_date", "")),
                "Security", "High",
                breach.get("Domain", breach.get("domain", "")),
            ])

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
                _field(pdf, comp.get("company_name", "N/A"),
                       f"{comp.get('role', '')} | {comp.get('status', '')} | {comp.get('source_name', '')}")
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
            clean = re.sub(r'!\[.*?\]\(.*?\)\s*', '', ai_response).strip()
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

        # Footer on all pages
        for page_num in range(1, pdf.pages_count + 1):
            pdf.page = page_num
            pdf.set_y(-15)
            pdf.set_font("Helvetica", "I", 8)
            pdf.set_text_color(100, 100, 120)
            pdf.cell(0, 10, f"J.A.R.V.I.S Intelligence Platform | Page {page_num}/{pdf.pages_count} | {generated}", align="C")

        return bytes(pdf.output())


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

_SOCIAL_FIELDS = [
    "github_url", "instagram_url", "twitter_url", "linkedin_url",
    "spotify_url", "tiktok_url", "snapchat_url", "tumblr_url",
    "youtube_url", "reddit_url", "facebook_url", "pinterest_url",
    "medium_url", "threads_url", "steam_url",
    "tinder_mention", "bumble_mention", "discord_mention",
]


def _extract_social_urls(profile: dict) -> dict[str, str]:
    return {k: profile[k] for k in _SOCIAL_FIELDS if profile.get(k)}


def _safe(text: str) -> str:
    """Replace characters that latin-1 (fpdf default) can't encode."""
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _set_page_bg(pdf: "FPDF") -> None:
    pdf.set_fill_color(20, 20, 32)
    pdf.rect(0, 0, 210, 297, "F")


def _section_header(pdf: "FPDF", title: str) -> None:
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


def _field(pdf: "FPDF", label: str, value: str) -> None:
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


# Singleton
report_service = ReportService()
