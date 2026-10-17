"""
Shared pure utility functions for pipeline steps.
Moved from search_orchestration_service so steps can import them without
creating circular dependencies.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from app.schemas.profile import BREACH_IDENTIFIER_KEYS


def _parse_snippet_date(snippet: str) -> datetime | None:
    """Extract a datetime from a Yahoo search result snippet (best-effort)."""
    if not snippet:
        return None
    now = datetime.now(UTC)
    s = snippet.lower()

    for pattern, unit in [
        (r"(\d+)\s+hour[s]?\s+ago", "hours"),
        (r"(\d+)\s+day[s]?\s+ago", "days"),
        (r"(\d+)\s+week[s]?\s+ago", "weeks"),
        (r"(\d+)\s+month[s]?\s+ago", "months"),
        (r"(\d+)\s+year[s]?\s+ago", "years"),
    ]:
        m = re.search(pattern, s)
        if m:
            n = int(m.group(1))
            delta = {
                "hours": timedelta(hours=n),
                "days": timedelta(days=n),
                "weeks": timedelta(weeks=n),
                "months": timedelta(days=n * 30),
                "years": timedelta(days=n * 365),
            }[unit]
            return now - delta

    if "yesterday" in s:
        return now - timedelta(days=1)

    month_map = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }
    m = re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})", s)
    if m:
        try:
            return datetime(int(m.group(3)), month_map[m.group(1)[:3]], int(m.group(2)), tzinfo=UTC)
        except ValueError:
            pass

    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", snippet)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=UTC)
        except ValueError:
            pass

    return None


def _format_last_activity(
    github_data: dict | None,
    social_profiles: dict | None = None,
) -> str | None:
    """Return human-readable 'last seen' label from the most recent signal."""
    candidates: list[datetime] = []

    if github_data:
        last_active = github_data.get("last_active")
        if last_active:
            try:
                dt = (
                    datetime.fromisoformat(last_active.replace("Z", "+00:00"))
                    if isinstance(last_active, str)
                    else last_active
                )
                candidates.append(dt)
            except (ValueError, TypeError):
                pass

    if social_profiles:
        for items in social_profiles.values():
            for item in items:
                dt = _parse_snippet_date(item.get("bio", ""))
                if dt:
                    candidates.append(dt)

    if not candidates:
        return None

    days = (datetime.now(UTC) - max(candidates)).days
    if days == 0:
        return "Active today"
    if days <= 7:
        return f"Active {days}d ago"
    if days <= 30:
        return f"Active {days // 7}w ago"
    if days <= 365:
        return f"Active {days // 30}mo ago"
    return f"Active {days // 365}yr ago"


def _join_urls(profiles: dict, platform: str) -> str | None:
    """Join real profile URLs from social_profiles[platform], skipping [SEARCH] fallbacks."""
    items = profiles.get(platform, [])
    result = ", ".join(p["url"] for p in items if p.get("url") and p.get("bio") != "[SEARCH]")
    return result or None


def _join_bios(profiles: dict, platform: str) -> str | None:
    """Join bios from social_profiles[platform]."""
    items = profiles.get(platform, [])
    result = ", ".join(p.get("bio", "") for p in items if p.get("url"))
    return result or None


# ---------------------------------------------------------------------------
# Response sanitizers
#
# Several SearchResponse fields are populated straight from LLM-extracted JSON,
# and the schema validators for them are strict (an email must contain '@', a
# network connection must be a dict with a 'name', ...). A single malformed item
# in a model's output would otherwise raise at the final assembly step and throw
# away a search that already ran for minutes.
#
# Every sanitizer here drops the bad item and keeps the rest. The pydantic
# validators stay in place — they still guard the profile-creation and DB read
# paths, where the input is not LLM output.
# ---------------------------------------------------------------------------


def sanitize_str_list(value: object) -> list[str]:
    """Coerce an LLM-produced list into a list of non-empty strings."""
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, (int, float, bool)):
            text = str(item)
        elif isinstance(item, dict):
            # Models sometimes answer [{"name": "X"}] where a plain string was asked for.
            candidate = item.get("name") or item.get("title") or item.get("value")
            text = str(candidate).strip() if candidate else ""
        else:
            text = ""
        if text:
            result.append(text)
    return result


def sanitize_email_list(value: object) -> list[str]:
    """Keep only entries that look like email addresses (schema requires '@')."""
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and "@" in item and item.strip()]


def sanitize_phone_list(value: object) -> list[str]:
    """Keep only strings long enough to be a phone number (schema requires >= 3 chars)."""
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and len(item.strip()) >= 3]


def sanitize_network_connections(value: object) -> list[dict[str, str]]:
    """Keep dicts carrying a name; force every value to str (the schema is dict[str, str]).

    A null value — common in LLM JSON, e.g. {"name": "X", "role": null} — would
    otherwise fail validation, so null-valued keys are dropped rather than kept.
    """
    if not isinstance(value, list):
        return []
    result: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not name or not str(name).strip():
            continue
        result.append({str(k): str(v) for k, v in item.items() if v is not None})
    return result


def sanitize_breach_list(value: object) -> list[dict[str, Any]]:
    """Keep dict entries that carry at least one identifying key.

    Mirrors ProfileDataMixin.validate_data_breaches so anything that survives
    here is guaranteed to pass validation.
    """
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict) and (item.keys() & BREACH_IDENTIFIER_KEYS)]
