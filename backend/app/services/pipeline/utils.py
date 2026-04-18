"""
Shared pure utility functions for pipeline steps.
Moved from search_orchestration_service so steps can import them without
creating circular dependencies.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta


def _parse_snippet_date(snippet: str) -> datetime | None:
    """Extract a datetime from a Yahoo search result snippet (best-effort)."""
    if not snippet:
        return None
    now = datetime.now(UTC)
    s = snippet.lower()

    for pattern, unit in [
        (r'(\d+)\s+hour[s]?\s+ago',  'hours'),
        (r'(\d+)\s+day[s]?\s+ago',   'days'),
        (r'(\d+)\s+week[s]?\s+ago',  'weeks'),
        (r'(\d+)\s+month[s]?\s+ago', 'months'),
        (r'(\d+)\s+year[s]?\s+ago',  'years'),
    ]:
        m = re.search(pattern, s)
        if m:
            n = int(m.group(1))
            delta = {
                'hours': timedelta(hours=n), 'days': timedelta(days=n),
                'weeks': timedelta(weeks=n), 'months': timedelta(days=n * 30),
                'years': timedelta(days=n * 365),
            }[unit]
            return now - delta

    if 'yesterday' in s:
        return now - timedelta(days=1)

    month_map = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
        'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
    }
    m = re.search(
        r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})', s
    )
    if m:
        try:
            return datetime(int(m.group(3)), month_map[m.group(1)[:3]], int(m.group(2)), tzinfo=UTC)
        except ValueError:
            pass

    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', snippet)
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
        last_active = github_data.get('last_active')
        if last_active:
            try:
                dt = (
                    datetime.fromisoformat(last_active.replace('Z', '+00:00'))
                    if isinstance(last_active, str)
                    else last_active
                )
                candidates.append(dt)
            except (ValueError, TypeError):
                pass

    if social_profiles:
        for items in social_profiles.values():
            for item in items:
                dt = _parse_snippet_date(item.get('bio', ''))
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
    result = ", ".join(
        p['url'] for p in items
        if p.get('url') and p.get('bio') != '[SEARCH]'
    )
    return result or None


def _join_bios(profiles: dict, platform: str) -> str | None:
    """Join bios from social_profiles[platform]."""
    items = profiles.get(platform, [])
    result = ", ".join(p.get('bio', '') for p in items if p.get('url'))
    return result or None
