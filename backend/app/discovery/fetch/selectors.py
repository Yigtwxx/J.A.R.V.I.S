"""Thin helpers over Scrapling's Selector API.

Scrapling 0.4 exposes ``.css()`` returning a list-like ``Selectors`` and has no
``css_first``; ``.re_first()`` matches against *text content*, not raw markup, so
embedded-JSON extraction has to regex ``html_content`` directly. These helpers
hide both quirks so every extractor reads the same way, and they never raise —
a malformed document yields ``None``, not an exception mid-search.
"""

from __future__ import annotations

import json
import re
from typing import Any

_JSON_LD_SELECTOR = 'script[type="application/ld+json"]'


def css_first(page: Any, selector: str) -> Any | None:
    """First element matching ``selector``, or None."""
    if page is None:
        return None
    try:
        found = page.css(selector)
    except Exception:
        return None
    return found[0] if found else None


def css_text(page: Any, selector: str) -> str | None:
    """Text of the first match. ``selector`` should end in ``::text``."""
    if page is None:
        return None
    try:
        value = page.css(selector).get()
    except Exception:
        return None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def css_attr(page: Any, selector: str, attribute: str) -> str | None:
    """Attribute of the first element matching ``selector``."""
    element = css_first(page, selector)
    if element is None:
        return None
    try:
        value = element.attrib.get(attribute)
    except Exception:
        return None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def css_all_attr(page: Any, selector: str, attribute: str) -> list[str]:
    """Every value of ``attribute`` across all matches, de-duplicated, order preserved."""
    if page is None:
        return []
    try:
        elements = page.css(selector)
    except Exception:
        return []
    out: list[str] = []
    for element in elements:
        try:
            value = element.attrib.get(attribute)
        except Exception:
            continue
        if value:
            text = str(value).strip()
            if text and text not in out:
                out.append(text)
    return out


def meta_content(page: Any, *names: str) -> str | None:
    """First non-empty ``<meta>`` content among ``names``.

    Accepts both ``property=`` (OpenGraph) and ``name=`` (Twitter cards, standard
    meta) spellings, because sites are inconsistent about which they use.
    """
    for name in names:
        escaped = name.replace('"', '\\"')
        for selector in (f'meta[property="{escaped}"]', f'meta[name="{escaped}"]'):
            value = css_attr(page, selector, "content")
            if value:
                return value
    return None


def canonical_url(page: Any) -> str | None:
    """``<link rel=canonical>`` href, falling back to ``og:url``."""
    return css_attr(page, 'link[rel="canonical"]', "href") or meta_content(page, "og:url")


def json_ld_objects(page: Any) -> list[dict[str, Any]]:
    """Every JSON-LD object on the page, with ``@graph`` arrays flattened.

    Malformed blocks are skipped rather than aborting: one broken script tag must
    not cost us the rest of the page.
    """
    out: list[dict[str, Any]] = []
    if page is None:
        return out
    try:
        blocks = page.css(_JSON_LD_SELECTOR)
    except Exception:
        return out

    for block in blocks:
        raw = _element_text(block)
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            continue
        _flatten_json_ld(parsed, out)
    return out


def _flatten_json_ld(node: Any, out: list[dict[str, Any]]) -> None:
    if isinstance(node, list):
        for item in node:
            _flatten_json_ld(item, out)
        return
    if not isinstance(node, dict):
        return
    graph = node.get("@graph")
    if isinstance(graph, list):
        for item in graph:
            _flatten_json_ld(item, out)
    out.append(node)


def json_ld_of_type(page: Any, *types: str) -> dict[str, Any] | None:
    """First JSON-LD object whose ``@type`` matches (case-insensitively)."""
    wanted = {t.lower() for t in types}
    for obj in json_ld_objects(page):
        raw_type = obj.get("@type")
        candidates = raw_type if isinstance(raw_type, list) else [raw_type]
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.lower() in wanted:
                return obj
    return None


def embedded_json(html: str | None, pattern: str) -> Any | None:
    """Extract and parse a JSON blob out of raw markup.

    ``pattern`` must expose exactly one capture group containing the JSON. Used for
    ``ytInitialData``, TikTok's ``__UNIVERSAL_DATA_FOR_REHYDRATION__``, and friends
    — always parsed with ``json.loads``, never regexed field-by-field.
    """
    if not html:
        return None
    match = re.search(pattern, html, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except (ValueError, TypeError, IndexError):
        return None


def script_json(page: Any, selector: str) -> Any | None:
    """Parse the body of a ``<script>`` tag selected by ``selector`` as JSON."""
    element = css_first(page, selector)
    if element is None:
        return None
    raw = _element_text(element)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


def dig(data: Any, path: str, default: Any = None) -> Any:
    """Walk a dotted path through nested dicts/lists.

    ``dig(d, "data.user.stats.followerCount")``. List indices are written as plain
    integers: ``"items.0.name"``. Returns ``default`` on any miss.
    """
    current = data
    for part in path.split("."):
        if current is None:
            return default
        if isinstance(current, list):
            if not part.lstrip("-").isdigit():
                return default
            index = int(part)
            if -len(current) <= index < len(current):
                current = current[index]
                continue
            return default
        if isinstance(current, dict):
            if part not in current:
                return default
            current = current[part]
            continue
        return default
    return default if current is None else current


def _element_text(element: Any) -> str:
    """Best-effort raw text of an element across Scrapling versions."""
    for attribute in ("html_content", "text"):
        try:
            value = getattr(element, attribute, None)
        except Exception:
            continue
        if value:
            text = str(value).strip()
            # html_content includes the surrounding tag; strip it for script bodies.
            if attribute == "html_content" and text.startswith("<"):
                inner = re.sub(r"^<[^>]+>|</[^>]+>$", "", text).strip()
                if inner:
                    return inner
                continue
            if text:
                return text
    try:
        return str(element.get_all_text(strip=True) or "").strip()
    except Exception:
        return ""
