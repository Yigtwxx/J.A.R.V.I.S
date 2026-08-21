"""What changed about a target since the last search.

Re-running a search on someone answers a different question than running it the
first time. The first run asks "who is this"; the second asks "what moved". This
module answers the second, by comparing two flat snapshots keyed on
``platform:username``.

Avatar changes are detected on ``avatar_sha256``, never on the avatar URL. CDNs
rewrite image URLs on every deploy, so a URL comparison reports a changed picture
roughly every week regardless of whether the picture changed. The content hash
only moves when the bytes do.

The snapshot shape here is deliberately flat JSON so it can be persisted next to
the existing ``ChangeReport`` machinery in ``app.services.version_history_service``
without a schema of its own.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.discovery.matching.candidate import ProfileCandidate

NO_CHANGES = "No changes since the previous search."

# Field -> the change label reported when it differs. Order fixes the order the
# deltas are emitted in, so a diff is reproducible.
_TRACKED: tuple[tuple[str, str], ...] = (
    ("display_name", "name_changed"),
    ("bio", "bio_changed"),
    ("avatar_sha256", "avatar_changed"),
)


@dataclass(frozen=True, slots=True)
class ProfileDelta:
    """One account-level change."""

    platform: str
    username: str
    change: str
    """``added`` | ``removed`` | ``bio_changed`` | ``avatar_changed`` | ``name_changed``."""

    before: str | None = None
    after: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "username": self.username,
            "change": self.change,
            "before": self.before,
            "after": self.after,
        }


@dataclass(frozen=True, slots=True)
class DiscoveryDiff:
    """Everything that moved between two searches, plus a one-line summary."""

    added: tuple[ProfileDelta, ...]
    removed: tuple[ProfileDelta, ...]
    changed: tuple[ProfileDelta, ...]
    summary: str

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed or self.changed)

    def as_dict(self) -> dict[str, Any]:
        return {
            "added": [d.as_dict() for d in self.added],
            "removed": [d.as_dict() for d in self.removed],
            "changed": [d.as_dict() for d in self.changed],
            "summary": self.summary,
            "has_changes": self.has_changes,
        }


def snapshot_of(profiles: Sequence[ProfileCandidate]) -> dict[str, dict[str, Any]]:
    """Flatten the live accounts into a comparable, JSON-serialisable snapshot."""
    return {
        profile.key: {
            "platform": profile.platform,
            "username": profile.username,
            "url": profile.url,
            "display_name": profile.display_name,
            "bio": profile.bio,
            "avatar_sha256": profile.avatar_sha256,
            "score": profile.score.value,
        }
        for profile in profiles
        if profile.is_live
    }


def _identity(key: str, row: dict[str, Any]) -> tuple[str, str]:
    """Platform and username, falling back to the key when the row is sparse."""
    platform, _, username = key.partition(":")
    return str(row.get("platform") or platform), str(row.get("username") or username)


def _summarize(added: int, removed: int, changed: int, since: str | None) -> str:
    """One human sentence. Never a template with zeroes left in it."""
    if not (added or removed or changed):
        return NO_CHANGES
    parts: list[str] = []
    if added:
        parts.append(f"{added} new account{'s' if added != 1 else ''}")
    if removed:
        parts.append(f"{removed} removed")
    if changed:
        parts.append(f"{changed} changed")
    tail = f" since {since}" if since else ""
    return f"{', '.join(parts)}{tail}."


def diff_snapshots(
    previous: dict[str, dict[str, Any]],
    current: dict[str, dict[str, Any]],
    *,
    since: str | None = None,
) -> DiscoveryDiff:
    """Compare two snapshots produced by :func:`snapshot_of`.

    Args:
        previous: The stored snapshot from the earlier search.
        current: The snapshot just produced.
        since: Optional date label for the summary, e.g. ``"2026-06-01"``.
    """
    added: list[ProfileDelta] = []
    removed: list[ProfileDelta] = []
    changed: list[ProfileDelta] = []

    for key in sorted(set(current) - set(previous)):
        platform, username = _identity(key, current[key])
        added.append(ProfileDelta(platform=platform, username=username, change="added", after=current[key].get("url")))

    for key in sorted(set(previous) - set(current)):
        platform, username = _identity(key, previous[key])
        removed.append(
            ProfileDelta(platform=platform, username=username, change="removed", before=previous[key].get("url"))
        )

    for key in sorted(set(previous) & set(current)):
        before_row, after_row = previous[key], current[key]
        platform, username = _identity(key, after_row)
        for field_name, label in _TRACKED:
            before, after = before_row.get(field_name), after_row.get(field_name)
            # A field that disappeared is a gap in this run's data, not a change
            # in the person. Reporting "bio removed" every time a scrape is
            # blocked would bury the changes that are real.
            if before == after or after in (None, ""):
                continue
            changed.append(
                ProfileDelta(
                    platform=platform,
                    username=username,
                    change=label,
                    before=str(before) if before is not None else None,
                    after=str(after),
                )
            )

    return DiscoveryDiff(
        added=tuple(added),
        removed=tuple(removed),
        changed=tuple(changed),
        summary=_summarize(len(added), len(removed), len(changed), since),
    )
