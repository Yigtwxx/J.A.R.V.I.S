"""Adapters that feed the discovery pipeline into the pre-existing services.

Five working services predate the discovery rewrite and speak the old flat shape,
so every translation lives here and each gains one entry point. Two rules are encoded here rather than in the callers, because getting either
wrong reintroduces the bug the rewrite exists to kill:

* **A refusal is not an absence.** ``blocked``/``error`` platforms are carried
  into the report with their ``status_detail``, are excluded from the social
  score instead of depressing it, and never raise a watch alert for a "removed"
  account. We were refused; the account did not disappear.
* **Avatars are compared as files, never as faces.** What touches ``data/avatars``
  here is export or the user-facing face-match tool; the identity scoring path
  imports none of it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.discovery.analysis.diff import diff_snapshots, snapshot_of
from app.discovery.media.store import AvatarStore

AVATAR_URL_PREFIX = "/api/media/avatars/"

# A "removed" account is only real when we actually reached the platform. When we
# were refused, the account is simply invisible to us this round — alerting on it
# would fire a false alarm every time a site rate-limits or captchas us.
UNREACHED_STATUSES = frozenset({"blocked", "error"})

# Discovery platform key -> the key SocialScoreService already knows.
_SCORE_ALIASES = {"x": "twitter"}


# -- Shape-agnostic accessors (ProfileCandidate | SocialProfile | plain dict) --


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _status(profile: Any) -> str:
    """Normalised status string, whichever shape the profile arrived in."""
    raw = _attr(profile, "status")
    if raw is None:
        raw = _attr(profile, "platform_status")
    return str(raw) if raw is not None else "error"


def _confidence(profile: Any) -> int:
    value = _attr(profile, "confidence")
    if value is None:
        value = _attr(_attr(profile, "score"), "value", 0)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _band(profile: Any) -> str:
    band = _attr(profile, "band") or _attr(_attr(profile, "score"), "band")
    return str(band) if band else "possible"


def is_found(profile: Any) -> bool:
    """Only a reached, existing account. Blocked and not_found both fail this."""
    return _status(profile) == "found"


# -- Avatar files --


def sha_from_avatar_url(url: str | None) -> str | None:
    """``/api/media/avatars/<sha>.jpg`` -> ``<sha>``, or None if not a stored avatar."""
    if not url or AVATAR_URL_PREFIX not in url:
        return None
    return Path(url.rsplit("/", 1)[-1]).stem or None


def avatar_path(url: str | None, *, root: Path | None = None) -> Path | None:
    """Map a public avatar URL onto its file, via the ``AvatarStore`` allow-list
    and containment check. A missing or unsafe name yields None, never an error."""
    if not url or AVATAR_URL_PREFIX not in url:
        return None
    return AvatarStore(root).resolve(url.rsplit("/", 1)[-1])


# -- Report export --


@dataclass(slots=True)
class DiscoveryReportData:
    """Every new discovery section, flattened into plain JSON-safe rows."""

    social: list[dict[str, Any]] = field(default_factory=list)
    pictures: list[dict[str, Any]] = field(default_factory=list)
    work: list[dict[str, Any]] = field(default_factory=list)
    education: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)

    @property
    def has_any(self) -> bool:
        groups = (self.social, self.pictures, self.work, self.education, self.evidence, self.notices)
        return any(groups)


_WORK_FIELDS = ("organization", "role", "start", "end", "is_current", "source_url", "confidence")
_EDUCATION_FIELDS = ("institution", "degree", "field_of_study", "start", "end", "source_url", "confidence")
_EVIDENCE_FIELDS = ("kind", "value", "source_domain", "source_url", "confidence")


def _rows(container: Any, key: str, fields: Sequence[str]) -> list[dict[str, Any]]:
    items = _attr(container, key) or []
    if not isinstance(items, Sequence) or isinstance(items, str):
        return []
    return [{f: _attr(item, f) for f in fields} for item in items]


def build_report_data(profile: Any, *, avatar_root: Path | None = None) -> DiscoveryReportData:
    """Collect the discovery sections of a profile payload for export.

    Blocked and not_found platforms are deliberately kept: an export listing only
    successes reads as "nothing exists there" — the silently-empty failure the
    rewrite replaced."""
    social = [
        {
            "platform": _attr(p, "platform") or "",
            "username": _attr(p, "username"),
            "url": _attr(p, "url"),
            "status": _status(p),
            "status_detail": _attr(p, "status_detail"),
            "confidence": _confidence(p),
            "band": _band(p),
        }
        for p in (_attr(profile, "social_profiles") or [])
    ]

    pictures: list[dict[str, Any]] = []
    for pic in _attr(profile, "profile_pictures") or []:
        url = _attr(pic, "url")
        path = avatar_path(url, root=avatar_root)
        pictures.append(
            {
                "url": url,
                "platform": _attr(pic, "platform") or "",
                "sha256": _attr(pic, "sha256") or sha_from_avatar_url(url),
                "is_primary": bool(_attr(pic, "is_primary")),
                "path": str(path) if path else None,
            }
        )

    return DiscoveryReportData(
        social=social,
        pictures=pictures,
        work=_rows(profile, "work_history", _WORK_FIELDS),
        education=_rows(profile, "education", _EDUCATION_FIELDS),
        evidence=_rows(profile, "evidence", _EVIDENCE_FIELDS),
        notices=[str(n) for n in (_attr(_attr(profile, "discovery"), "notices") or [])],
    )


# -- Watch / version history snapshots --


def profile_snapshot(profiles: Sequence[Any]) -> dict[str, dict[str, Any]]:
    """Flat, comparable snapshot of the live accounts. ``ProfileCandidate`` goes
    through :func:`snapshot_of`; ``SocialProfile`` is flattened the same way, with
    the avatar hash recovered from the stored URL so change detection stays on
    file content and not on a CDN URL that rewrites itself weekly."""
    if profiles and hasattr(profiles[0], "is_live"):
        return snapshot_of(profiles)

    snapshot: dict[str, dict[str, Any]] = {}
    for p in profiles:
        if not is_found(p):
            continue
        platform, username = str(_attr(p, "platform") or ""), str(_attr(p, "username") or "")
        snapshot[f"{platform}:{username.lower()}"] = {
            "platform": platform,
            "username": username,
            "url": _attr(p, "url"),
            "display_name": _attr(p, "display_name"),
            "bio": _attr(p, "bio"),
            "avatar_sha256": _attr(p, "sha256") or sha_from_avatar_url(_attr(p, "avatar_url")),
            "score": _confidence(p),
        }
    return snapshot


def status_index(profiles: Sequence[Any]) -> dict[str, str]:
    """Current status keyed by both ``platform:username`` and bare ``platform``."""
    index: dict[str, str] = {}
    for p in profiles:
        platform = str(_attr(p, "platform") or "")
        username = str(_attr(p, "username") or "")
        status = _status(p)
        index[f"{platform}:{username.lower()}"] = status
        index.setdefault(platform, status)
    return index


def watch_alerts(
    previous: Mapping[str, dict[str, Any]],
    current: Mapping[str, dict[str, Any]],
    *,
    statuses: Mapping[str, str] | None = None,
    since: str | None = None,
) -> list[dict[str, Any]]:
    """Changes worth waking someone up for: new, removed, changed avatar or bio.

    A platform going ``found`` -> ``blocked`` is NOT an alert. The account did
    not disappear, we were refused — and because a blocked candidate is not live
    it drops out of the snapshot and would otherwise look identical to a
    deletion, firing a false alarm every time a site rate-limits us.
    """
    diff = diff_snapshots(dict(previous), dict(current), since=since)
    lookup = dict(statuses or {})
    alerts: list[dict[str, Any]] = [d.as_dict() for d in diff.added + diff.changed]

    for delta in diff.removed:
        key = f"{delta.platform}:{delta.username.lower()}"
        status = lookup.get(key) or lookup.get(delta.platform)
        if status in UNREACHED_STATUSES:
            continue
        alerts.append(delta.as_dict())

    return alerts


# -- Social score --


def to_score_inputs(profiles: Sequence[Any]) -> tuple[dict[str, Any] | None, dict[str, list[dict[str, Any]]]]:
    """Map profiles onto ``SocialScoreService.calculate_score`` arguments.

    Only ``found`` profiles are emitted. A blocked platform contributes nothing and
    — critically — subtracts nothing: absence of proof is not proof of absence, so a
    rate-limited scan must not score lower than the same person scanned an hour ago."""
    github_data: dict[str, Any] | None = None
    grouped: dict[str, list[dict[str, Any]]] = {}

    for p in profiles:
        if not is_found(p):
            continue
        platform = str(_attr(p, "platform") or "").lower()
        platform = _SCORE_ALIASES.get(platform, platform)
        if not platform:
            continue
        links, bio = _attr(p, "outbound_links") or [], _attr(p, "bio") or ""
        row = {"url": _attr(p, "url"), "username": _attr(p, "username"), "bio": bio, "confidence": _confidence(p)}
        grouped.setdefault(platform, []).append(row)

        if platform == "github" and github_data is None:
            # The score service reads GitHub API field names; `posts` is the
            # pipeline's generic count, which for GitHub is the repo count.
            github_data = {
                "followers": _attr(p, "followers") or 0,
                "public_repos": _attr(p, "posts") or 0,
                "last_active": _attr(p, "last_activity"),
                "bio": _attr(p, "bio"),
                "blog": links[0] if links else None,
            }

    return github_data, grouped


# -- Face matching (user-facing tool only) --


def face_match_inputs(profile: Any, *, avatar_root: Path | None = None, limit: int = 8) -> list[tuple[str, str]]:
    """``(label, local file path)`` pairs for the manual face-comparison tool.

    Biometric identification of individuals is out of scope for the discovery
    pipeline: this is only ever reached from ``/api/face-match``. The ``sha256`` /
    ``dhash`` signals in ``app/discovery/matching/scoring.py`` are *file* comparisons
    — "the same image file appears on both accounts" — computed without any face
    model, and neither scoring nor clustering imports this."""
    pictures = _attr(profile, "profile_pictures")
    if pictures is None and isinstance(profile, Sequence) and not isinstance(profile, str):
        pictures = profile

    pairs: list[tuple[str, str]] = []
    for pic in pictures or []:
        path = avatar_path(_attr(pic, "url"), root=avatar_root)
        if path is None:
            continue
        pairs.append((str(_attr(pic, "platform") or "unknown"), str(path)))
        if len(pairs) >= limit:
            break
    return pairs
