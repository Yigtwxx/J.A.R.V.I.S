"""What a discovered application is, and what resolving a name produced.

Kept in its own module so the platform back-ends and the matcher can share it
without importing each other.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.discovery.identity.normalize import fold_ascii

# Which discovery source to believe when the same application turns up twice.
# The native "this is how the desktop launches it" source ranks first: a Start
# Menu shortcut, a macOS bundle and a .desktop entry all go through the shell,
# which resolves Store packages and version-scoped installs that a raw path
# cannot. A bare executable path is the least reliable — it goes stale when the
# application updates.
_KIND_RANK: dict[str, int] = {
    "shortcut": 0,
    "bundle": 0,
    "desktop": 0,
    "packaged": 1,
    "executable": 2,
    "uri": 3,
}

# Suffixes a user types because that is what the OS shows them, and which say
# nothing about which application they mean.
_STRIPPED_SUFFIXES: tuple[str, ...] = (".exe", ".app", ".desktop", ".lnk")


def normalize_app_name(text: str) -> str:
    """Canonical matching key: ASCII-folded, de-suffixed, single-spaced.

    ``fold_ascii`` rather than ``str.lower()`` because Turkish is not optional
    here — ``"SPOTİFY".lower()`` leaves a combining dot behind and would never
    match ``spotify``.
    """
    folded = fold_ascii(text or "").strip()
    for suffix in _STRIPPED_SUFFIXES:
        if folded.endswith(suffix):
            folded = folded[: -len(suffix)]
            break
    return " ".join(folded.split())


@dataclass(frozen=True, slots=True)
class AppEntry:
    """One launchable application found on this machine."""

    name: str
    """What the user sees, in the system's own wording."""

    normalized: str
    kind: str
    """``shortcut`` | ``packaged`` | ``executable`` | ``bundle`` | ``desktop`` | ``uri``."""

    target: str
    """Exactly what gets handed to the OS. Never assembled from user input."""

    source: str
    """Where it was discovered, kept for diagnostics rather than logic."""

    aliases: tuple[str, ...] = field(default_factory=tuple)
    """Extra normalized keys, e.g. a package name behind a localised display name."""

    @classmethod
    def build(
        cls,
        *,
        name: str,
        kind: str,
        target: str,
        source: str,
        aliases: tuple[str, ...] = (),
    ) -> AppEntry:
        """Construct with the normalized keys derived, so callers cannot forget."""
        normalized_aliases = tuple(
            dict.fromkeys(key for key in (normalize_app_name(alias) for alias in aliases) if key)
        )
        return cls(
            name=name.strip(),
            normalized=normalize_app_name(name),
            kind=kind,
            target=target,
            source=source,
            aliases=normalized_aliases,
        )

    @property
    def rank(self) -> int:
        """Lower is more trustworthy. Used to break ties, never to filter."""
        return _KIND_RANK.get(self.kind, len(_KIND_RANK))

    @property
    def keys(self) -> tuple[str, ...]:
        """Every normalized string this entry answers to."""
        return (self.normalized, *self.aliases) if self.normalized else self.aliases


@dataclass(frozen=True, slots=True)
class MatchResult:
    """One application, or several that matched equally well — never a guess."""

    entry: AppEntry | None = None
    candidates: tuple[AppEntry, ...] = field(default_factory=tuple)
    reason: str = ""
    """Which rung of the ladder decided it, for the log and the API response."""

    @property
    def is_ambiguous(self) -> bool:
        return self.entry is None and bool(self.candidates)


class AppLaunchError(RuntimeError):
    """The application was identified but could not be started."""
