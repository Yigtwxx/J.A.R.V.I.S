"""Turning a typed name into exactly one installed application.

A ladder of increasingly forgiving rules, first hit wins, evaluated over the
applications discovery actually found. The user's text never becomes part of a
command — it only ever selects an entry whose launch target we produced
ourselves.

The last rule is the important one: when a rung matches several *different*
applications, this returns them as candidates instead of choosing. Opening the
wrong desktop application is a much worse outcome than one more round trip.
"""

from __future__ import annotations

import difflib
from collections.abc import Sequence

from app.discovery.identity.normalize import name_tokens
from app.services.app_launcher.models import AppEntry, MatchResult, normalize_app_name

_FUZZY_CUTOFF = 0.8
"""difflib ratio below which a suggestion is too speculative to offer."""

MAX_CANDIDATES = 6
"""Enough to choose from, few enough to read."""

# Names people type that no vendor actually ships. These only ever *add* a way to
# reach software that discovery already found - a nickname for something that is
# not installed still resolves to nothing - so the table stays honest on a
# machine that has none of it.
_NICKNAMES: dict[str, tuple[str, ...]] = {
    "vscode": ("visual studio code",),
    "vs code": ("visual studio code",),
    "chrome": ("google chrome",),
    "edge": ("microsoft edge",),
    "word": ("microsoft word",),
    "excel": ("microsoft excel",),
    "powerpoint": ("microsoft powerpoint",),
    "outlook": ("microsoft outlook",),
    "teams": ("microsoft teams",),
    "explorer": ("file explorer",),
    "terminal": ("windows terminal",),
    "photoshop": ("adobe photoshop",),
    "premiere": ("adobe premiere pro",),
    "intellij": ("intellij idea",),
}


def resolve(query: str, entries: Sequence[AppEntry]) -> MatchResult:
    """Best single match for ``query``, or the candidates that tied."""
    needle = normalize_app_name(query)
    if not needle or not entries:
        return MatchResult()

    for reason, matches in (
        ("exact", [e for e in entries if needle in e.keys]),
        ("nickname", _by_nickname(needle, entries)),
        ("prefix", [e for e in entries if any(key.startswith(needle) for key in e.keys)]),
        ("tokens", [e for e in entries if _covers_tokens(needle, e)]),
        ("substring", [e for e in entries if any(needle in key for key in e.keys)]),
        ("fuzzy", _fuzzy(needle, entries)),
    ):
        if not matches:
            continue
        return _decide(matches, reason)

    return MatchResult()


def suggest(query: str, entries: Sequence[AppEntry], *, limit: int = 12) -> list[AppEntry]:
    """Applications worth showing while the user is still typing.

    Deliberately looser than :func:`resolve` and never authoritative: an empty
    query lists everything, because that is what a user opening the panel wants
    to see.

    Both branches dedupe. The panel keys its rows on the fields it is given, and
    one Start Menu tree really does hold the same shortcut at two depths, so an
    undeduped list is a duplicate React key rather than a cosmetic repeat.
    """
    needle = normalize_app_name(query)
    if not needle:
        return sorted(_dedupe(entries), key=_display_order)[:limit]
    hits = [
        entry
        for entry in entries
        if any(key.startswith(needle) for key in entry.keys) or any(needle in key for key in entry.keys)
    ]
    return sorted(_dedupe(hits), key=_display_order)[:limit]


def _decide(matches: list[AppEntry], reason: str) -> MatchResult:
    """One winner if the matches name a single application, else the candidates."""
    unique = _dedupe(matches)
    if len(unique) == 1:
        return MatchResult(entry=unique[0], reason=reason)
    return MatchResult(candidates=tuple(sorted(unique, key=_display_order)[:MAX_CANDIDATES]), reason=reason)


def _dedupe(matches: Sequence[AppEntry]) -> list[AppEntry]:
    """Collapse the same application discovered by several sources.

    Discovery deliberately reads more than one source, so Discord shows up as a
    Start Menu shortcut *and* an App Paths executable. That is one application
    with two ways in, not an ambiguous query — keeping the more reliable source
    is the whole point of `AppEntry.rank`.
    """
    best: dict[str, AppEntry] = {}
    for entry in matches:
        current = best.get(entry.normalized)
        if current is None or entry.rank < current.rank:
            best[entry.normalized] = entry
    return list(best.values())


def _covers_tokens(needle: str, entry: AppEntry) -> bool:
    """Every word the user typed appears in the name, in any order."""
    wanted = set(name_tokens(needle))
    if not wanted:
        return False
    return any(wanted <= set(name_tokens(key)) for key in entry.keys)


def _fuzzy(needle: str, entries: Sequence[AppEntry]) -> list[AppEntry]:
    """Typo tolerance, last resort. Keyed on the primary name only."""
    by_key = {entry.normalized: entry for entry in entries if entry.normalized}
    close = difflib.get_close_matches(needle, list(by_key), n=MAX_CANDIDATES, cutoff=_FUZZY_CUTOFF)
    return [by_key[key] for key in close]


def _display_order(entry: AppEntry) -> tuple[int, str]:
    return (entry.rank, entry.normalized)


def _by_nickname(needle: str, entries: Sequence[AppEntry]) -> list[AppEntry]:
    """Exact hits for a known nickname of ``needle``, if that software is installed."""
    wanted = _NICKNAMES.get(needle)
    if not wanted:
        return []
    return [entry for entry in entries if any(name in entry.keys for name in wanted)]


def merge_executable_aliases(entries: Sequence[AppEntry]) -> list[AppEntry]:
    """Fold a bare executable name into the application it clearly belongs to.

    Discovery reads several sources on purpose, so Chrome arrives as "Google
    Chrome" from the Start Menu *and* as "chrome" from the registry's executable
    table. They are one application; the human name is the one worth showing, and
    leaving the stem as its own entry lets it win the exact rung and display
    "chrome" in the panel.

    Folded only when the stem's words are contained in exactly **one** better
    source. "notepad" sits inside both Notepad and Notepad++, so it stays put
    rather than being guessed into one of them.
    """
    named = [entry for entry in entries if entry.rank == 0]
    out: list[AppEntry] = []
    absorbed: dict[int, list[str]] = {}

    for entry in entries:
        if entry.rank == 0 or not entry.normalized:
            continue
        stem = set(name_tokens(entry.normalized))
        if not stem:
            continue
        hosts = [index for index, host in enumerate(named) if stem <= set(name_tokens(host.normalized))]
        if len(hosts) == 1:
            absorbed.setdefault(hosts[0], []).append(entry.normalized)

    folded = {alias for aliases in absorbed.values() for alias in aliases}
    for index, host in enumerate(named):
        extra = absorbed.get(index, [])
        out.append(
            AppEntry(
                name=host.name,
                normalized=host.normalized,
                kind=host.kind,
                target=host.target,
                source=host.source,
                aliases=tuple(dict.fromkeys((*host.aliases, *extra))),
            )
            if extra
            else host
        )
    out.extend(e for e in entries if e.rank != 0 and e.normalized not in folded)
    return out
