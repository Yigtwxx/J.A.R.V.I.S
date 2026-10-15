"""Discovering and launching applications on Windows.

Everything here is stdlib. Three sources are read, in descending order of how
reliably they name a *human* application:

1. **Start Menu shortcuts** - the same list the Start menu shows, so the file
   name is already the display name the user knows.
2. **Packaged (Store/MSIX) applications** - from the per-user package repository
   in the registry, which needs no elevation and no PowerShell.
3. **App Paths** - the classic "this executable is registered" table.

Launching is always ``os.startfile``, which is ``ShellExecuteW`` - the code path
Explorer uses on double click. That matters more than it sounds:

* **Shortcut bodies are never parsed.** A stdlib MS-SHLLINK parser resolves only
  about half of them (the rest carry a shell-namespace ID list with no readable
  path), and reading all 159 shortcuts on one real machine cost 3.3 seconds cold
  against 5 ms for the directory walk. ``os.startfile`` on the shortcut itself
  resolves every shape, including the ones a parser cannot.
* **Store applications have no usable executable.** Spotify installs as MSIX:
  the classic ``Spotify.exe`` under APPDATA does not exist, the WindowsApps entry
  is a zero-byte reparse point, and its ``spotify:`` protocol has no
  ``shell/open/command`` at all. Only shell activation starts it.
* **Version-scoped installs go stale.** Discord's registered handler pointed at
  ``app-1.0.9254`` while ``app-1.0.9255`` was the installed build. A shortcut
  survives the update; a captured path does not.
"""

from __future__ import annotations

import ctypes
import os
import winreg
from collections.abc import Iterator
from pathlib import Path

from app.services.app_launcher.models import AppEntry, AppLaunchError
from app.utils.logger import logger

_SHORTCUT_SUFFIXES: frozenset[str] = frozenset({".lnk", ".url"})

_APP_PATHS_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
_PACKAGES_KEY = (
    r"Software\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\Repository\Packages"
)

# Start Menu items that are installer plumbing rather than an application the
# user would ever ask for by name.
_SKIPPED_NAMES: frozenset[str] = frozenset(
    {"desktop.ini", "uninstall", "uninstaller", "readme", "changelog", "license", "documentation", "help"}
)


def enumerate_apps() -> list[AppEntry]:
    """Every launchable application this user can see, best source first."""
    entries: list[AppEntry] = []
    entries.extend(_start_menu_entries())
    entries.extend(_packaged_entries())
    entries.extend(_app_paths_entries())
    return entries


def launch(entry: AppEntry) -> None:
    """Hand the target to the shell. Raises ``AppLaunchError`` if it will not start."""
    try:
        os.startfile(entry.target)  # noqa: S606 - a discovered target, never user text
    except OSError as exc:
        raise AppLaunchError(f"Windows refused to start {entry.name}: {exc}") from exc


# -- source 1: the Start Menu --------------------------------------------------


def _start_menu_roots() -> list[tuple[str, Path]]:
    """Both Start Menu trees with the scope that names them, from the environment.

    The scope is spelled out rather than read back off the path: both trees end in
    ``Microsoft/Windows/Start Menu/Programs``, so every directory name in reach of
    the root is identical for the two of them and could never tell them apart.
    """
    roots: list[tuple[str, Path]] = []
    for variable, scope in (("APPDATA", "user"), ("PROGRAMDATA", "machine")):
        base = os.environ.get(variable)
        if not base:
            continue
        candidate = Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        if candidate.is_dir():
            roots.append((scope, candidate))
    return roots


def _start_menu_entries() -> Iterator[AppEntry]:
    for scope, root in _start_menu_roots():
        for path in _walk_shortcuts(root):
            name = path.stem.strip()
            if not name or name.casefold() in _SKIPPED_NAMES:
                continue
            yield AppEntry.build(
                name=name,
                kind="shortcut",
                target=str(path),
                source=f"start-menu:{scope}",
            )


def _walk_shortcuts(root: Path) -> Iterator[Path]:
    """Shortcut files under ``root``. A directory we cannot read is skipped, not fatal."""
    for dirpath, _dirnames, filenames in os.walk(root, onerror=lambda _err: None):
        for filename in filenames:
            path = Path(dirpath) / filename
            if path.suffix.lower() in _SHORTCUT_SUFFIXES:
                yield path


# -- source 2: packaged (Store / MSIX) applications ----------------------------


def _packaged_entries() -> Iterator[AppEntry]:
    """Store applications, addressed by AUMID through the Apps folder.

    Read from the per-user repository rather than ``Get-AppxPackage``: the
    registry answers in about 13 ms where PowerShell costs 700 ms and a whole
    process, and the WindowsApps directory is not readable at all.
    """
    try:
        packages = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _PACKAGES_KEY)
    except OSError:
        return
    with packages:
        for package_key in _subkeys(packages):
            try:
                with winreg.OpenKey(packages, package_key) as package:
                    package_id = _value(package, "PackageID") or package_key
                    family = _package_family(package_id)
                    if not family:
                        continue
                    display = _resolve_indirect(_value(package, "DisplayName"))
                    for app_id in _subkeys(package):
                        yield from _packaged_app(package, package_id, family, app_id, display)
            except OSError:
                continue


def _packaged_app(
    package: winreg.HKEYType,
    package_id: str,
    family: str,
    app_id: str,
    package_display: str,
) -> Iterator[AppEntry]:
    """One application inside a package, if it declares itself as one."""
    try:
        with winreg.OpenKey(package, rf"{app_id}\Capabilities") as capabilities:
            app_display = _resolve_indirect(_value(capabilities, "ApplicationName"))
    except OSError:
        app_display = ""

    name = app_display or package_display
    if not name:
        return
    # The package name is kept as an alias because display names arrive
    # localised - "Microsoft Haber" on a Turkish system - and a user may well
    # type the English one they already know.
    yield AppEntry.build(
        name=name,
        kind="packaged",
        target=f"shell:AppsFolder\\{family}!{app_id}",
        source="appmodel",
        aliases=(package_id.split("_", 1)[0], app_id),
    )


def _package_family(package_id: str) -> str:
    """``Name_version_arch__hash`` to ``Name_hash``, the family half of an AUMID."""
    parts = package_id.split("_")
    if len(parts) < 2 or not parts[0] or not parts[-1]:
        return ""
    return f"{parts[0]}_{parts[-1]}"


def _resolve_indirect(raw: str) -> str:
    """Resolve an ``@{package?ms-resource://...}`` display name to real text.

    Packaged applications store their names as MRT indirect strings. Left
    unresolved they are unreadable and, worse, unmatchable - the user would have
    to type a resource path. ``SHLoadIndirectString`` is the documented way to
    expand them and reaches us through ctypes, so this stays stdlib-only.
    """
    if not raw.startswith("@{"):
        return raw
    try:
        buffer = ctypes.create_unicode_buffer(1024)
        shlwapi = ctypes.WinDLL("shlwapi")
        shlwapi.SHLoadIndirectString(raw, buffer, len(buffer), None)
        return buffer.value or ""
    except OSError:
        return ""


# -- source 3: App Paths -------------------------------------------------------


def _app_paths_entries() -> Iterator[AppEntry]:
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            root = winreg.OpenKey(hive, _APP_PATHS_KEY, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
        except OSError:
            continue
        with root:
            for key_name in _subkeys(root):
                try:
                    with winreg.OpenKey(root, key_name) as entry:
                        target = _value(entry, "")
                except OSError:
                    continue
                # Several keys register a DLL, or carry no default value at all.
                if not target or not target.lower().endswith(".exe"):
                    continue
                yield AppEntry.build(
                    name=Path(key_name).stem,
                    kind="executable",
                    # Values are quoted often and 8.3-shortened sometimes.
                    target=os.path.realpath(target.strip('"')),
                    source="app-paths",
                )


# -- registry helpers ----------------------------------------------------------


def _subkeys(key: winreg.HKEYType) -> list[str]:
    try:
        count, _values, _written = winreg.QueryInfoKey(key)
    except OSError:
        return []
    names: list[str] = []
    for index in range(count):
        try:
            names.append(winreg.EnumKey(key, index))
        except OSError:
            break
    return names


def _value(key: winreg.HKEYType, name: str) -> str:
    try:
        raw, _kind = winreg.QueryValueEx(key, name)
    except OSError:
        return ""
    return raw.strip() if isinstance(raw, str) else ""


def describe_unavailable() -> str:
    """Why discovery found nothing, in the case where it finds nothing."""
    if not _start_menu_roots():
        return (
            "No Start Menu was found for this user. The backend may be running "
            "without a desktop session (a service, or a container)."
        )
    logger.log_warning("App discovery found no applications despite a readable Start Menu", broadcast=False)
    return "No applications were discovered on this machine."
