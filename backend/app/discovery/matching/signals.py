"""The named signals that make up a confidence score.

Scoring is **additive with caps**, not multiplicative, for one reason: every point
must be independently attributable to a sentence a human can read. A multiplied
score is impossible to explain, and an unexplainable confidence number in an OSINT
tool is worse than no number at all.

Weights are ordered by how hard the signal is to fake or coincide with:

* A **reciprocal link** (A links to B and B links back) is the strongest keyless
  evidence that exists — it requires control of both accounts.
* A shared **avatar file hash** is strong but not conclusive (people reuse stock
  images), hence the `generic_image` counter-signal.
* A **name match** is weak on its own. Thousands of people share a name; that is
  the entire reason this pipeline exists.
"""

from __future__ import annotations

from typing import Final

# Positive signals: (code, points, human-readable template)
POSITIVE: Final[dict[str, tuple[float, str]]] = {
    "user_confirmed": (35.0, "you confirmed this account belongs to the target"),
    "reciprocal_link": (30.0, "this profile and {other} link to each other"),
    "rel_me_verified": (28.0, "bidirectional rel=me verification with {other}"),
    "personal_site_backlink": (25.0, "the personal site {other} links here and this profile links back"),
    "outbound_link_match": (22.0, "links to {other}, which is already confirmed"),
    "exact_username_anchor": (18.0, "username is identical to the confirmed handle '{other}'"),
    "display_name_exact": (16.0, "display name contains every part of the target's name"),
    "cv_document": (15.0, "a CV/resume document ties this identity to {other}"),
    "email_local_match": (14.0, "username matches the local part of the confirmed email"),
    "reverse_image_hit": (14.0, "the same profile picture was found on {other}"),
    "avatar_sha256_identical": (12.0, "byte-identical profile picture to {other}"),
    "employer_match": (12.0, "employer matches the confirmed employer '{other}'"),
    "registry_record": (12.0, "a company/scholarly registry ties this name to {other}"),
    "location_match": (10.0, "location matches the confirmed location '{other}'"),
    "school_match": (10.0, "school matches the confirmed school '{other}'"),
    "archived_profile_existed": (10.0, "the archive shows this account existed on {other}"),
    "username_variant_anchor": (9.0, "username is a close variant of the confirmed handle '{other}'"),
    "avatar_phash_near": (8.0, "visually near-identical profile picture to {other}"),
    "bio_contains_name": (8.0, "the bio contains the target's name"),
    "archive_bio_match": (8.0, "the archived bio matches known details"),
    "display_name_partial": (7.0, "display name contains part of the target's name"),
    "cross_platform_handle_recurrence": (6.0, "the same handle appears on {other}"),
    "serp_corroboration": (5.0, "returned by {other} for the target's name"),
    "verified_badge": (5.0, "the platform marks this account as verified"),
}

# Negative signals.
NEGATIVE: Final[dict[str, tuple[float, str]]] = {
    "user_rejected": (-60.0, "you said this account is NOT the target"),
    "name_mismatch": (-18.0, "the display name shares nothing with the target's name"),
    "name_conflict": (-16.0, "'{other}' shares a surname but is a different given name"),
    "unverified_existence": (-15.0, "the page loaded but nothing structurally confirms this handle"),
    "conflicting_location": (-12.0, "location '{other}' conflicts with the confirmed location"),
    "conflicting_employer": (-10.0, "employer '{other}' conflicts with the confirmed employer"),
    "generic_handle": (-8.0, "the handle is a common word rather than a personal handle"),
    "generic_image": (-8.0, "the profile picture is a stock/shared image used by several identities"),
    "extended_platform_uncorroborated": (-6.0, "niche platform hit with no independent corroboration"),
    "stale_profile": (-5.0, "no activity for over five years and nothing corroborates it"),
    "blocked_existence": (-5.0, "the platform refused us, so this could not be verified"),
}

# Signals that may fire more than once, with a ceiling on the total they can add.
CAPPED: Final[dict[str, float]] = {
    "cross_platform_handle_recurrence": 18.0,
    "serp_corroboration": 10.0,
    "reverse_image_hit": 28.0,
    "outbound_link_match": 44.0,
}

BAND_THRESHOLDS: Final[tuple[tuple[int, str], ...]] = (
    (80, "confirmed"),
    (60, "likely"),
    (40, "possible"),
    (20, "weak"),
    (0, "rejected"),
)


def points_for(code: str) -> float:
    """Signed weight of a signal. Unknown codes contribute nothing."""
    if code in POSITIVE:
        return POSITIVE[code][0]
    if code in NEGATIVE:
        return NEGATIVE[code][0]
    return 0.0


def text_for(code: str, other: str = "") -> str:
    """Render the human-readable reason for a signal."""
    template = POSITIVE.get(code, NEGATIVE.get(code, (0.0, code)))[1]
    try:
        return template.format(other=other or "another source")
    except (KeyError, IndexError):
        return template


def cap_for(code: str) -> float | None:
    return CAPPED.get(code)
