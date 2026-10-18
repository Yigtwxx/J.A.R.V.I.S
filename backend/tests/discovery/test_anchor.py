"""Anchor construction, strengthening, and conflict detection.

The first two tests are the regression guard for a real production bug: the old
resolver read the GitHub handle from ``"login"``, but ``GitHubService`` emits it
under ``"username"``, so the anchor was always empty and disambiguation never ran.
"""

from __future__ import annotations

import pytest

from app.discovery.identity.anchor import (
    CONFIRMED_GITHUB_API,
    CONFIRMED_RECIPROCAL_LINK,
    CONFIRMED_USER_ANSWER,
    Anchor,
    build_anchor,
    conflicts,
    strengthen,
)
from app.discovery.types import EntityType


@pytest.mark.parametrize("key", ["username", "login"])
def test_build_anchor_reads_the_github_handle_from_either_key(key: str) -> None:
    anchor = build_anchor("Yiğit Erdoğan", EntityType.PERSON, github_data={key: "Yigtwxx"})
    assert anchor.handle == "yigtwxx", f"the handle must be read from {key!r}, got {anchor.handle!r}"
    assert anchor.handle_platform == "github", "the handle's platform must be recorded"
    assert anchor.confirmed_by == CONFIRMED_GITHUB_API, "a GitHub API handle is a confirmed handle"
    assert anchor.is_confident, "a confirmed GitHub handle must produce a confident anchor"


def test_build_anchor_folds_the_name_into_tokens() -> None:
    anchor = build_anchor("Yiğit Erdoğan", EntityType.PERSON)
    assert anchor.tokens == ("yigit", "erdogan"), f"name tokens must be ASCII-folded, got {anchor.tokens}"
    assert anchor.entity is EntityType.PERSON, "the entity type must be preserved"


def test_build_anchor_without_a_handle_is_not_confident() -> None:
    anchor = build_anchor("Yiğit Erdoğan", EntityType.PERSON)
    assert not anchor.is_confident, "a name alone is exactly what namesakes share and can never anchor"


def test_build_anchor_with_empty_github_handle_is_not_confident() -> None:
    anchor = build_anchor("Yiğit Erdoğan", EntityType.PERSON, github_data={"username": "", "company": "Getir"})
    assert anchor.handle == "", "an empty handle must stay empty"
    assert not anchor.is_confident, "attributes without a handle do not make an anchor confident"


def test_build_anchor_absorbs_github_attributes() -> None:
    anchor = build_anchor(
        "Yiğit Erdoğan",
        EntityType.PERSON,
        github_data={
            "username": "Yigtwxx",
            "name": "Yigit Erdogan Jr",
            "company": "@Getir A.Ş.",
            "location": "İstanbul, Türkiye",
            "email": "Yigit@Example.com",
            "blog": "https://www.yigit.dev/about",
        },
    )
    assert anchor.employer == "getir", f"the employer must be normalised, got {anchor.employer!r}"
    assert "istanbul" in anchor.location_tokens, f"location tokens missing: {anchor.location_tokens}"
    assert anchor.email == "yigit@example.com", f"the email must be lowercased, got {anchor.email!r}"
    assert anchor.domain == "yigit.dev", f"the blog host must become the domain, got {anchor.domain!r}"
    assert "jr" in anchor.tokens, f"the GitHub display name must extend the token set: {anchor.tokens}"


def test_strengthen_returns_a_new_object_and_does_not_mutate() -> None:
    original = build_anchor("Yiğit Erdoğan", EntityType.PERSON)
    stronger = strengthen(original, handle="Yigtwxx", platform="x", reason=CONFIRMED_USER_ANSWER)
    assert stronger is not original, "strengthen must return a new anchor, never the same object"
    assert original.handle == "", f"the original anchor must be untouched, got {original.handle!r}"
    assert stronger.handle == "yigtwxx", f"the new anchor must carry the handle, got {stronger.handle!r}"
    assert stronger.handle_platform == "x", "the new anchor must record the platform"
    assert stronger.confirmed_by == CONFIRMED_USER_ANSWER, "the new anchor must record why it is trusted"
    assert stronger.is_confident, "a handle plus a reason is a confident anchor"


def test_strengthen_ignores_an_empty_handle() -> None:
    original = build_anchor("Yiğit Erdoğan", EntityType.PERSON, github_data={"username": "Yigtwxx"})
    result = strengthen(original, handle="  ", platform="x", reason=CONFIRMED_RECIPROCAL_LINK)
    assert result.handle == "yigtwxx", "an empty claim must not erase a confirmed handle"
    assert result.confirmed_by == CONFIRMED_GITHUB_API, "the original confirmation must survive"


def test_strengthen_does_not_overwrite_a_confirmed_handle_with_a_different_one() -> None:
    original = build_anchor("Yiğit Erdoğan", EntityType.PERSON, github_data={"username": "Yigtwxx"})
    result = strengthen(original, handle="someoneelse", platform="x", reason=CONFIRMED_RECIPROCAL_LINK)
    assert result.handle == "yigtwxx", f"a weaker later claim must not displace the proof, got {result.handle!r}"


def test_conflicts_detects_two_different_confirmed_handles() -> None:
    a = build_anchor("Yiğit Erdoğan", EntityType.PERSON, github_data={"username": "Yigtwxx"})
    b = build_anchor("Yiğit Erdoğan", EntityType.PERSON, github_data={"login": "someoneelse"})
    assert conflicts(a, b), "two confirmed but different handles cannot be the same person"


def test_conflicts_accepts_the_same_confirmed_handle() -> None:
    a = build_anchor("Yiğit Erdoğan", EntityType.PERSON, github_data={"username": "Yigtwxx"})
    b = build_anchor("Yigit Erdogan", EntityType.PERSON, github_data={"login": "yigtwxx"})
    assert not conflicts(a, b), "the same handle spelled differently is the same person"


def test_conflicts_needs_both_employer_and_location_to_disagree() -> None:
    a = Anchor(name="A", tokens=("a",), entity=EntityType.PERSON, employer="getir", location_tokens=("istanbul",))
    b = Anchor(name="B", tokens=("b",), entity=EntityType.PERSON, employer="trendyol", location_tokens=("istanbul",))
    assert not conflicts(a, b), "people change jobs; a different employer alone is not a conflict"


def test_conflicts_on_disagreeing_employer_and_location() -> None:
    a = Anchor(name="A", tokens=("a",), entity=EntityType.PERSON, employer="getir", location_tokens=("istanbul",))
    b = Anchor(name="B", tokens=("b",), entity=EntityType.PERSON, employer="trendyol", location_tokens=("berlin",))
    assert conflicts(a, b), "a different employer AND a different city together are a conflict"


def test_conflicts_is_false_for_two_bare_anchors() -> None:
    a = build_anchor("Yiğit Erdoğan", EntityType.PERSON)
    b = build_anchor("Yiğit Erdoğan", EntityType.PERSON)
    assert not conflicts(a, b), "with no evidence at all there is nothing to conflict over"


def test_anchor_summary_mentions_the_handle() -> None:
    anchor = build_anchor("Yiğit Erdoğan", EntityType.PERSON, github_data={"username": "Yigtwxx"})
    assert "@yigtwxx" in anchor.summary(), f"the summary must surface the anchor handle: {anchor.summary()!r}"
