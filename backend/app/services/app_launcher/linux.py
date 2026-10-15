"""Discovering and launching applications on Linux.

Applications are ``.desktop`` entries, found through the XDG variables rather
than hard-coded paths, plus the Flatpak and Snap export directories that the XDG
variables often miss.

Parsing them needs three non-default ``configparser`` flags, each for a concrete
reason: ``interpolation=None`` because ``Exec=firefox %U`` is a syntax error to
the default interpolator, ``strict=False`` because real files do repeat keys, and
``optionxform=str`` to keep locale suffixes like ``Name[tr]`` distinguishable.

Launching prefers ``gio launch``, which applies the ``Exec`` field codes and
startup notification the way the desktop expects. The parsed-argv fallback sets
``start_new_session`` so the application does not die with the web worker.
"""

from __future__ import annotations

import configparser
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

from app.services.app_launcher.models import AppEntry, AppLaunchError

# Field codes the spec defines for Exec; they are placeholders for files and
# URLs we are not passing, so they must be removed before exec.
_FIELD_CODES = re.compile(r"%[fFuUdDnNickvm]")

_EXTRA_ROOTS: tuple[str, ...] = (
    "/var/lib/flatpak/exports/share/applications",
    "~/.local/share/flatpak/exports/share/applications",
    "/var/lib/snapd/desktop/applications",
)


def enumerate_apps() -> list[AppEntry]:
    entries: list[AppEntry] = []
    seen: set[str] = set()
    for root in _roots():
        try:
            children = sorted(root.glob("*.desktop"))
        except OSError:
            continue
        for path in children:
            if path.name in seen:
                continue
            seen.add(path.name)
            entry = _entry_for(path)
            if entry is not None:
                entries.append(entry)
    return entries


def launch(entry: AppEntry) -> None:
    gio = shutil.which("gio")
    if gio:
        _run([gio, "launch", entry.target], entry.name)
        return
    gtk_launch = shutil.which("gtk-launch")
    if gtk_launch:
        _run([gtk_launch, Path(entry.target).name], entry.name)
        return

    argv = _exec_argv(entry.target)
    if not argv:
        raise AppLaunchError(f"No way to start {entry.name}: neither gio nor a usable Exec line was found.")
    try:
        subprocess.Popen(  # noqa: S603 - argv list, shell=False, parsed from a discovered file
            argv,
            shell=False,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise AppLaunchError(f"Could not start {entry.name}: {exc}") from exc


def _roots() -> list[Path]:
    """Application directories, derived from XDG rather than assumed."""
    data_home = os.environ.get("XDG_DATA_HOME") or "~/.local/share"
    data_dirs = (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":")
    candidates = [Path(data_home).expanduser() / "applications"]
    candidates += [Path(directory).expanduser() / "applications" for directory in data_dirs if directory]
    candidates += [Path(extra).expanduser() for extra in _EXTRA_ROOTS]
    return [path for path in candidates if path.is_dir()]


def _entry_for(path: Path) -> AppEntry | None:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str  # type: ignore[method-assign] - keep Name[tr] distinct from name[tr]
    try:
        parser.read(path, encoding="utf-8")
        section = parser["Desktop Entry"]
    except (OSError, configparser.Error, KeyError, UnicodeDecodeError):
        return None

    if section.get("Type", "").strip() != "Application":
        return None
    if section.get("NoDisplay", "").strip().lower() == "true":
        return None
    if section.get("Hidden", "").strip().lower() == "true":
        return None
    # `TryExec` is the entry's own statement that it may not really be installed.
    try_exec = section.get("TryExec", "").strip()
    if try_exec and not shutil.which(try_exec):
        return None

    name = section.get("Name", "").strip() or path.stem
    return AppEntry.build(
        name=name,
        kind="desktop",
        target=str(path),
        source="xdg",
        aliases=(path.stem,),
    )


def _exec_argv(desktop_path: str) -> list[str]:
    """The ``Exec`` line with field codes removed, split for ``Popen``."""
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str  # type: ignore[method-assign]
    try:
        parser.read(desktop_path, encoding="utf-8")
        raw = parser["Desktop Entry"].get("Exec", "")
    except (OSError, configparser.Error, KeyError, UnicodeDecodeError):
        return []
    cleaned = _FIELD_CODES.sub("", raw).replace("%%", "%")
    try:
        return [token for token in shlex.split(cleaned) if token]
    except ValueError:
        return []


def _run(argv: list[str], app_name: str) -> None:
    try:
        completed = subprocess.run(  # noqa: S603 - argv list, shell=False
            argv, shell=False, capture_output=True, text=True, timeout=20
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AppLaunchError(f"Could not start {app_name}: {exc}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or "").strip() or f"exit code {completed.returncode}"
        raise AppLaunchError(f"The desktop refused to start {app_name}: {detail}")


def describe_unavailable() -> str:
    return "No .desktop entries were found in the XDG application directories."
