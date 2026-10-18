"""Turning what the user typed into exactly one installed application.

The old implementation was a hand-written `APP_ALIASES` table mapping a slug to
an argv list. It could not work: `"spotify": ["spotify"]` needs `spotify` on
PATH (it is not, on any machine — the Store alias directory is not on PATH), and
`"browser": ["start", "msedge"]` names a `cmd.exe` builtin that `shell=False` can
never find. Discord was absent entirely.

The replacement discovers what is actually installed and matches against that, so
a fresh clone on someone else's machine finds their applications rather than the
author's. This module pins the matching half, which is pure and needs no machine.

The load-bearing rule is the last one: when several applications match comparably
well, the resolver returns candidates instead of picking. Launching the wrong
desktop application is a far worse failure than asking one more question.
"""

from __future__ import annotations

import pytest

from app.services.app_launcher.matching import resolve, suggest
from app.services.app_launcher.models import AppEntry


def _entry(name: str, *, kind: str = "shortcut", aliases: tuple[str, ...] = ()) -> AppEntry:
    return AppEntry.build(name=name, kind=kind, target=f"C:/fake/{name}.lnk", source="test", aliases=aliases)


CATALOGUE: tuple[AppEntry, ...] = (
    _entry("Spotify"),
    _entry("Discord"),
    _entry("Visual Studio Code", aliases=("code", "vscode")),
    _entry("Visual Studio 2022"),
    _entry("Google Chrome"),
    _entry("Steam"),
)


def test_resolve_exact_name_returns_that_application() -> None:
    result = resolve("Spotify", CATALOGUE)

    assert result.entry is not None, "an exact name must resolve"
    assert result.entry.name == "Spotify", f"expected Spotify, got {result.entry.name}"


@pytest.mark.parametrize("query", ["spotify", "SPOTIFY", "  Spotify  "])
def test_resolve_ignores_case_and_surrounding_space(query: str) -> None:
    result = resolve(query, CATALOGUE)

    assert result.entry is not None and result.entry.name == "Spotify", f"{query!r} must resolve to Spotify"


def test_resolve_matches_a_turkish_typed_name() -> None:
    """`fold_ascii` is reused precisely because `.lower()` mangles Turkish."""
    result = resolve("SPOTİFY", (*CATALOGUE, _entry("Işık Player")))

    assert result.entry is not None and result.entry.name == "Spotify", (
        f"dotted capital I must fold to i, got {result.entry and result.entry.name}"
    )


def test_resolve_matches_a_curated_alias() -> None:
    result = resolve("vscode", CATALOGUE)

    assert result.entry is not None and result.entry.name == "Visual Studio Code", (
        f"an alias must win before fuzzier steps, got {result.entry and result.entry.name}"
    )


def test_resolve_matches_a_unique_prefix() -> None:
    result = resolve("disc", CATALOGUE)

    assert result.entry is not None and result.entry.name == "Discord", (
        f"a unique prefix is unambiguous, got {result.entry and result.entry.name}"
    )


def test_resolve_returns_candidates_when_the_query_is_ambiguous() -> None:
    """Two applications start with "visual studio"; picking one would be a guess."""
    result = resolve("visual studio", CATALOGUE)

    assert result.entry is None, f"an ambiguous query must not launch anything, got {result.entry}"
    names = {c.name for c in result.candidates}
    assert names == {"Visual Studio Code", "Visual Studio 2022"}, f"both candidates must be offered, got {names}"


def test_resolve_prefers_an_exact_name_over_a_longer_one_that_contains_it() -> None:
    """ "Steam" is exact here even though other names could contain the word."""
    catalogue = (*CATALOGUE, _entry("Steam Link"), _entry("SteamVR"))

    result = resolve("steam", catalogue)

    assert result.entry is not None and result.entry.name == "Steam", (
        f"an exact hit must beat prefix matches, got {result.entry and result.entry.name}"
    )


def test_resolve_matches_tokens_in_any_order() -> None:
    result = resolve("chrome google", CATALOGUE)

    assert result.entry is not None and result.entry.name == "Google Chrome", (
        f"token-subset matching must ignore word order, got {result.entry and result.entry.name}"
    )


def test_resolve_finds_nothing_for_an_application_that_is_not_installed() -> None:
    result = resolve("photoshop", CATALOGUE)

    assert result.entry is None, f"an absent application must not resolve to something else, got {result.entry}"
    assert result.candidates == (), "there is nothing to offer either"


@pytest.mark.parametrize("query", ["", "   "])
def test_resolve_rejects_an_empty_query(query: str) -> None:
    result = resolve(query, CATALOGUE)

    assert result.entry is None and result.candidates == (), "an empty query resolves to nothing"


def test_resolve_ignores_a_trailing_executable_suffix() -> None:
    """Users type what they see in Task Manager."""
    result = resolve("spotify.exe", CATALOGUE)

    assert result.entry is not None and result.entry.name == "Spotify", (
        f"a .exe suffix must not defeat the match, got {result.entry and result.entry.name}"
    )


def test_the_same_application_from_two_sources_is_not_ambiguous() -> None:
    """Discovery finds Discord in the Start Menu and in App Paths; that is one app."""
    catalogue = (_entry("Discord", kind="shortcut"), _entry("Discord", kind="executable"))

    result = resolve("discord", catalogue)

    assert result.entry is not None, f"one application discovered twice must still resolve, got {result.candidates}"
    assert result.entry.kind == "shortcut", f"the more reliable source must win, got {result.entry.kind}"


def test_a_bare_executable_name_folds_into_the_application_it_belongs_to() -> None:
    """`App Paths` names an executable; the Start Menu names the application.

    Discovery reads both, so Chrome arrives twice: as "Google Chrome" from the
    Start Menu and as "chrome" from `App Paths`. They are one application, and
    the human name is the one worth showing. Folding also stops the executable
    stem from winning the exact rung and displaying "chrome" in the panel.
    """
    from app.services.app_launcher.matching import merge_executable_aliases

    merged = merge_executable_aliases(
        [
            _entry("Google Chrome", kind="shortcut"),
            _entry("chrome", kind="executable"),
        ]
    )

    assert len(merged) == 1, f"one application must survive, got {[e.name for e in merged]}"
    assert merged[0].name == "Google Chrome", f"the human name must win, got {merged[0].name}"
    assert "chrome" in merged[0].aliases, f"the executable stem must remain matchable, got {merged[0].aliases}"


def test_an_ambiguous_executable_name_is_kept_separate() -> None:
    """ "notepad" is a subset of both Notepad and Notepad++ - folding would guess."""
    from app.services.app_launcher.matching import merge_executable_aliases

    merged = merge_executable_aliases(
        [
            _entry("Notepad", kind="shortcut"),
            _entry("Notepad++", kind="shortcut"),
            _entry("notepad", kind="executable"),
        ]
    )

    assert len(merged) == 3, f"an ambiguous stem must not be folded into either, got {[e.name for e in merged]}"


def test_an_executable_with_no_application_of_its_own_is_kept() -> None:
    """Plenty of software registers an executable and ships no Start Menu entry."""
    from app.services.app_launcher.matching import merge_executable_aliases

    merged = merge_executable_aliases([_entry("Spotify", kind="shortcut"), _entry("ffmpeg", kind="executable")])

    assert {e.name for e in merged} == {"Spotify", "ffmpeg"}, "a standalone executable must stay discoverable"


def test_a_well_known_nickname_resolves_to_the_installed_application() -> None:
    """ "vscode" is what people type; no vendor ships an application by that name."""
    result = resolve("vscode", (_entry("Visual Studio Code"), _entry("Visual Studio 2022")))

    assert result.entry is not None and result.entry.name == "Visual Studio Code", (
        f"a nickname must beat the ambiguous prefix, got {result.entry and result.entry.name}"
    )


def test_a_nickname_does_not_invent_an_application_that_is_absent() -> None:
    """The table is an accuracy aid over discovery, never a source of truth."""
    result = resolve("vscode", (_entry("Spotify"),))

    assert result.entry is None and result.candidates == (), (
        "a nickname for software that is not installed must resolve to nothing"
    )


def test_suggest_collapses_an_application_the_start_menu_lists_twice() -> None:
    """One Start Menu tree routinely holds the same shortcut at two depths.

    Antigravity installs a loose `Antigravity.lnk` *and* a second copy inside its
    own `Antigravity` folder, so discovery honestly reports two
    entries with the same name and the same source. The panel renders one row per
    entry keyed on those two fields, so a duplicate is not a cosmetic repeat — it
    is a React key collision.
    """
    duplicated = (
        AppEntry.build(
            name="Antigravity",
            kind="shortcut",
            target="C:/fake/Programs/Antigravity.lnk",
            source="start-menu:user",
        ),
        AppEntry.build(
            name="Antigravity",
            kind="shortcut",
            target="C:/fake/Programs/Antigravity/Antigravity.lnk",
            source="start-menu:user",
        ),
    )

    names = [entry.name for entry in suggest("", duplicated)]

    assert names == ["Antigravity"], f"an empty query must collapse duplicates too, got {names}"


def test_suggest_returns_one_entry_per_application_for_every_query() -> None:
    """The filtered and unfiltered branches must not disagree about duplicates."""
    catalogue = (
        *CATALOGUE,
        _entry("Spotify", kind="executable"),
        _entry("Discord", kind="executable"),
    )

    for query in ("", "spotify", "disc"):
        names = [entry.name for entry in suggest(query, catalogue)]
        assert len(names) == len(set(names)), f"query {query!r} returned duplicate names: {names}"
