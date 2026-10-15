"""Discovering and launching applications on macOS.

Applications are bundles, so discovery is a shallow directory scan plus a plist
read - no subprocess, no indexing service required.

``/System/Applications`` is not optional: since Catalina, Apple's own
applications live there rather than in ``/Applications``, so a scan that omits it
silently loses Mail, Music and Calendar.

Launching goes through ``open -b <bundle id>`` in preference to ``open -a
<name>``, because a bundle id survives the application being renamed or moved
out of the standard folders. Both forms are argument lists, never a shell string.
"""

from __future__ import annotations

import plistlib
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

from app.services.app_launcher.models import AppEntry, AppLaunchError

_ROOTS: tuple[str, ...] = (
    "/Applications",
    "/Applications/Utilities",
    "/System/Applications",
    "/System/Applications/Utilities",
    "~/Applications",
)

_MAX_DEPTH = 2
"""Bundles nest one level under a vendor folder; deeper is bundle internals."""


def enumerate_apps() -> list[AppEntry]:
    entries: list[AppEntry] = []
    seen: set[str] = set()
    for root in _ROOTS:
        base = Path(root).expanduser()
        if not base.is_dir():
            continue
        for bundle in _bundles(base, depth=_MAX_DEPTH):
            if str(bundle) in seen:
                continue
            seen.add(str(bundle))
            entry = _entry_for(bundle)
            if entry is not None:
                entries.append(entry)
    return entries


def launch(entry: AppEntry) -> None:
    """``open`` hands off to LaunchServices and exits immediately."""
    opener = shutil.which("open")
    if not opener:
        raise AppLaunchError("The `open` command is unavailable, so no application can be started.")
    # `-b` when we know the bundle id, `-a` when all we have is a path.
    flag = "-b" if entry.kind == "bundle" and not entry.target.startswith("/") else "-a"
    try:
        completed = subprocess.run(  # noqa: S603 - argv list, shell=False, target is discovered
            [opener, flag, entry.target],
            shell=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AppLaunchError(f"Could not start {entry.name}: {exc}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or "").strip() or f"exit code {completed.returncode}"
        raise AppLaunchError(f"macOS refused to start {entry.name}: {detail}")


def _bundles(base: Path, *, depth: int) -> Iterator[Path]:
    """``*.app`` bundles at most ``depth`` levels below ``base``."""
    if depth <= 0:
        return
    try:
        children = list(base.iterdir())
    except OSError:
        return
    for child in children:
        if child.suffix == ".app":
            yield child
        elif child.is_dir():
            yield from _bundles(child, depth=depth - 1)


def _entry_for(bundle: Path) -> AppEntry | None:
    """Read the bundle's identity. A malformed plist costs one app, not the scan."""
    name = bundle.stem
    bundle_id = ""
    try:
        with (bundle / "Contents" / "Info.plist").open("rb") as handle:
            info = plistlib.load(handle)
        bundle_id = str(info.get("CFBundleIdentifier") or "")
        name = str(info.get("CFBundleDisplayName") or info.get("CFBundleName") or bundle.stem)
    except (OSError, plistlib.InvalidFileException, ValueError, AttributeError):
        bundle_id = ""
    if not name:
        return None
    return AppEntry.build(
        name=name,
        kind="bundle",
        target=bundle_id or str(bundle),
        source="applications",
        aliases=(bundle.stem,),
    )


def describe_unavailable() -> str:
    return "No applications were found in /Applications or ~/Applications."
