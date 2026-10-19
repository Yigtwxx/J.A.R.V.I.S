"""Single-identity election.

The requirement these tests enforce: the answer describes exactly ONE person.
The old pipeline poured every finding for a name into one bag and let the LLM
write a biography from all of it, producing a composite of several strangers.
A composite answer cannot even be evaluated, let alone corrected — so the elected
cluster must never contain a member of another cluster, and the per-platform cap
must trim within one identity rather than across several.
"""

from __future__ import annotations

from app.discovery.identity.anchor import Anchor, build_anchor
from app.discovery.identity.normalize import name_tokens
from app.discovery.matching.candidate import MatchScore, ProfileCandidate, ScoreReason
from app.discovery.matching.cluster import IdentityCluster, build_clusters, elect, limit_per_platform
from app.discovery.matching.scoring import ScoringContext, score_profile
from app.discovery.platforms.extract import ProfileData
from app.discovery.types import EntityType, ExistenceVerdict, MatchBand, PlatformTier


def _anchor(name: str = "Yigit Erdogan", handle: str = "", confirmed_by: str = "") -> Anchor:
    anchor = build_anchor(name, EntityType.PERSON)
    if handle:
        anchor.handle = handle
        anchor.confirmed_by = confirmed_by or "github_api"
    return anchor


def _candidate(
    platform: str,
    username: str,
    *,
    display_name: str | None = None,
    employer: str | None = None,
    location: str | None = None,
    links: list[str] | None = None,
    avatar_sha: str | None = None,
    score: int = 50,
    tier: PlatformTier = PlatformTier.CORE,
    verdict: ExistenceVerdict = ExistenceVerdict.EXISTS,
    user_confirmed: bool = False,
) -> ProfileCandidate:
    data = ProfileData(
        platform=platform,
        username=username,
        url=f"https://{platform}.example/{username}",
        display_name=display_name,
        employer=employer,
        location=location,
        outbound_links=list(links or []),
    )
    band = (
        MatchBand.CONFIRMED
        if score >= 80
        else MatchBand.LIKELY
        if score >= 60
        else MatchBand.POSSIBLE
        if score >= 40
        else MatchBand.WEAK
    )
    return ProfileCandidate(
        platform=platform,
        username=username,
        url=f"https://{platform}.example/{username}",
        verdict=verdict,
        tier=tier,
        data=data,
        avatar_sha256=avatar_sha,
        user_confirmed=user_confirmed,
        score=MatchScore(score, band, (ScoreReason("seed", "test seed", float(score)),)),
    )


def test_build_clusters_separates_three_different_people_with_the_same_name() -> None:
    """Three unrelated namesakes must not be merged into one identity."""
    anchor = _anchor()
    candidates = [
        # Person A — Istanbul, Getir, cross-linked GitHub <-> X.
        _candidate(
            "github", "yigitrdgn", employer="Getir", location="Istanbul", links=["https://x.com/yigitrdgn"], score=85
        ),
        _candidate(
            "x", "yigitrdgn", employer="Getir", location="Istanbul", links=["https://github.com/yigitrdgn"], score=80
        ),
        # Person B — Ankara, a different employer, a different handle.
        _candidate("instagram", "yigit_erd_official", employer="Aselsan", location="Ankara", score=55),
        # Person C — Izmir, another employer, another handle.
        _candidate("linkedin", "yigiterdoganmd", employer="Ege Universitesi", location="Izmir", score=50),
    ]
    ctx = ScoringContext(reciprocal_pairs={("github:yigitrdgn", "x:yigitrdgn")})

    clusters = build_clusters(candidates, anchor, (), ctx)

    assert len(clusters) == 3, (
        f"Expected 3 distinct identities, got {len(clusters)}: {[c.member_keys for c in clusters]}"
    )
    sizes = sorted(len(c.members) for c in clusters)
    assert sizes == [1, 1, 2], f"Expected one 2-member cluster and two singletons, got {sizes}"


def test_elected_cluster_contains_no_member_of_another_cluster() -> None:
    """The core invariant: the answer is built from one cluster and nothing else."""
    anchor = _anchor()
    candidates = [
        _candidate(
            "github", "yigitrdgn", employer="Getir", location="Istanbul", links=["https://x.com/yigitrdgn"], score=85
        ),
        _candidate(
            "x", "yigitrdgn", employer="Getir", location="Istanbul", links=["https://github.com/yigitrdgn"], score=80
        ),
        _candidate("instagram", "yigit_erd_official", employer="Aselsan", location="Ankara", score=55),
    ]
    ctx = ScoringContext(reciprocal_pairs={("github:yigitrdgn", "x:yigitrdgn")})

    winner, alternates = elect(build_clusters(candidates, anchor, (), ctx))

    assert winner is not None, "an identity must always be elected, even at low confidence"
    winner_keys = set(winner.member_keys)
    for alternate in alternates:
        overlap = winner_keys & set(alternate.member_keys)
        assert not overlap, f"elected cluster leaked members of an alternate identity: {overlap}"
    assert "instagram:yigit_erd_official" not in winner_keys, (
        "the Ankara/Aselsan account belongs to a different person and must stay out of the answer"
    )


def test_elect_always_returns_a_winner_even_when_confidence_is_low() -> None:
    """One coherent answer beats a merged blur, so a winner is chosen regardless."""
    anchor = _anchor()
    weak = [_candidate("tumblr", "someblog", score=15), _candidate("medium", "otherblog", score=12)]
    winner, alternates = elect(build_clusters(weak, anchor, (), ScoringContext()))
    assert winner is not None, "a low-confidence search must still name a single identity"
    assert len(alternates) >= 0


def test_elect_returns_none_when_there_are_no_live_candidates() -> None:
    anchor = _anchor()
    dead = [
        _candidate("github", "nope", verdict=ExistenceVerdict.NOT_FOUND),
        _candidate("linkedin", "nope", verdict=ExistenceVerdict.BLOCKED),
    ]
    winner, alternates = elect(build_clusters(dead, anchor, (), ScoringContext()))
    assert winner is None, "nothing live means no identity to elect"
    assert alternates == [], "no alternates either"


def test_reciprocal_link_merges_two_accounts() -> None:
    anchor = _anchor()
    candidates = [
        _candidate("github", "aaa", links=["https://x.com/bbb"]),
        _candidate("x", "bbb", links=["https://github.com/aaa"]),
    ]
    clusters = build_clusters(candidates, anchor, (), ScoringContext())
    assert len(clusters) == 1, f"mutually linked accounts are one identity, got {len(clusters)} clusters"


def test_shared_avatar_file_merges_accounts_but_a_stock_image_does_not() -> None:
    """A shared image file ties identities together — unless it is a stock photo."""
    anchor = _anchor()
    candidates = [
        _candidate("github", "aaa", avatar_sha="deadbeef"),
        _candidate("medium", "zzz", avatar_sha="deadbeef"),
    ]

    merged = build_clusters(
        candidates, anchor, (), ScoringContext(avatar_sha_index={"deadbeef": {"github:aaa", "medium:zzz"}})
    )
    assert len(merged) == 1, "the same avatar file is strong evidence of one identity"

    generic_ctx = ScoringContext(
        avatar_sha_index={"deadbeef": {"github:aaa", "medium:zzz"}},
        generic_images={"deadbeef"},
    )
    split = build_clusters(candidates, anchor, (), generic_ctx)
    assert len(split) == 2, "a stock/shared image must not merge two unrelated identities"


def test_conflicting_employer_and_location_beats_a_shared_handle() -> None:
    """A contradiction always wins over a weak agreement."""
    anchor = _anchor()
    candidates = [
        _candidate("github", "yigiterdogan", employer="Getir", location="Istanbul"),
        _candidate("medium", "yigiterdogan", employer="Aselsan", location="Ankara"),
    ]
    clusters = build_clusters(candidates, anchor, (), ScoringContext())
    assert len(clusters) == 2, (
        f"same handle but different employer AND city — two people, not one; got {[c.member_keys for c in clusters]}"
    )


def test_limit_per_platform_caps_accounts_and_keeps_the_best() -> None:
    """Max N accounts per platform, all from the elected identity."""
    anchor = _anchor()
    members = [
        _candidate("instagram", f"acct{i}", score=90 - i * 5, links=["https://github.com/anchor"]) for i in range(8)
    ] + [_candidate("github", "anchor", score=95)]
    ctx = ScoringContext(confirmed_urls={"https://github.com/anchor"})
    clusters = build_clusters(members, anchor, (), ctx)
    winner, _ = elect(clusters)
    assert winner is not None

    limited = limit_per_platform(winner, max_per_platform=5)
    instagram = [c for c in limited if c.platform == "instagram"]
    assert len(instagram) <= 5, f"at most 5 Instagram accounts, got {len(instagram)}"
    assert instagram[0].username == "acct0", "the highest-scoring account must survive the cap"


def test_limit_per_platform_never_returns_zero_for_a_present_platform() -> None:
    anchor = _anchor()
    cluster = build_clusters([_candidate("github", "solo")], anchor, (), ScoringContext())[0]
    assert len(limit_per_platform(cluster, max_per_platform=0)) == 1, (
        "a cap of 0 must still surface one account rather than hiding the platform"
    )


def test_cluster_label_distinguishes_same_name_identities() -> None:
    anchor = _anchor()
    candidates = [
        _candidate("github", "a1", employer="Getir", location="Istanbul"),
        _candidate("medium", "b2", employer="Aselsan", location="Ankara"),
    ]
    clusters = build_clusters(candidates, anchor, (), ScoringContext())
    labels = {c.label for c in clusters}
    assert len(labels) == len(clusters), f"each identity needs a distinguishing label, got {labels}"
    assert any("Istanbul" in label for label in labels), f"labels should carry the distinguishing detail: {labels}"


def test_build_clusters_is_deterministic() -> None:
    anchor = _anchor()
    candidates = [
        _candidate("github", "aaa", links=["https://x.com/bbb"]),
        _candidate("x", "bbb"),
        _candidate("medium", "ccc", employer="Getir", location="Istanbul"),
    ]
    first = [c.member_keys for c in build_clusters(candidates, anchor, (), ScoringContext())]
    second = [c.member_keys for c in build_clusters(candidates, anchor, (), ScoringContext())]
    assert first == second, f"clustering must be deterministic; {first} != {second}"


def test_user_rejection_keeps_an_account_out_of_the_elected_identity() -> None:
    anchor = _anchor()
    good = _candidate("github", "aaa", links=["https://x.com/bbb"], score=85)
    rejected = _candidate("x", "bbb", links=["https://github.com/aaa"], score=80)
    rejected.user_rejected = True

    clusters = build_clusters([good, rejected], anchor, (), ScoringContext())
    all_keys = {k for c in clusters for k in c.member_keys}
    assert "x:bbb" not in all_keys, "an account you rejected must not appear in any identity"


def test_score_profile_never_penalises_an_unanswered_question() -> None:
    """A timeout or "I don't know" is not a rejection — only an explicit no is."""
    anchor = _anchor(handle="yigitrdgn")
    candidate = _candidate("github", "yigitrdgn", display_name="Yigit Erdogan")

    score = score_profile(candidate, anchor, (), ScoringContext())
    codes = {r.code for r in score.reasons}
    assert "user_rejected" not in codes, "no explicit rejection was given, so no rejection penalty may apply"
    assert score.value > 0, f"a matching handle and name should score above zero, got {score.value}"


def test_score_profile_blocked_reduces_but_does_not_zero() -> None:
    """Absence of proof is not proof of absence."""
    anchor = _anchor(handle="yigitrdgn")
    blocked = _candidate("linkedin", "yigitrdgn", display_name="Yigit Erdogan", verdict=ExistenceVerdict.BLOCKED)
    blocked.verdict = ExistenceVerdict.BLOCKED

    score = score_profile(blocked, anchor, (), ScoringContext())
    codes = {r.code for r in score.reasons}
    assert "blocked_existence" in codes, "a refused check must be recorded as a reason"
    assert score.value > 0, f"being refused must not zero a candidate that otherwise matches, got {score.value}"


def test_score_profile_is_deterministic_and_ordered_by_magnitude() -> None:
    anchor = _anchor(handle="yigitrdgn")
    candidate = _candidate("github", "yigitrdgn", display_name="Yigit Erdogan", employer="Getir")
    anchor.employer = "Getir A.S."

    first = score_profile(candidate, anchor, (), ScoringContext())
    second = score_profile(candidate, anchor, (), ScoringContext())
    assert first.value == second.value, "scoring must be deterministic"
    assert [r.code for r in first.reasons] == [r.code for r in second.reasons], "reason order must be stable"

    magnitudes = [abs(r.points) for r in first.reasons]
    assert magnitudes == sorted(magnitudes, reverse=True), f"reasons must be ordered by impact, got {magnitudes}"


def test_score_profile_name_mismatch_is_forgiven_when_something_else_ties_it() -> None:
    """People use nicknames; a name mismatch only counts when nothing else connects."""
    anchor = _anchor(handle="yigitrdgn", confirmed_by="github_api")
    nickname = _candidate("instagram", "yigitrdgn", display_name="dark knight")

    score = score_profile(nickname, anchor, (), ScoringContext())
    codes = {r.code for r in score.reasons}
    assert "name_mismatch" not in codes, (
        "the handle matches the confirmed anchor, so a nickname display name is not a mismatch"
    )


def test_extended_platform_hit_is_penalised_without_corroboration() -> None:
    anchor = _anchor()
    niche = _candidate("duolingo", "yigit", tier=PlatformTier.EXTENDED, display_name="Yigit Erdogan")
    score = score_profile(niche, anchor, (), ScoringContext())
    assert "extended_platform_uncorroborated" in {r.code for r in score.reasons}, (
        "a niche-platform hit with nothing else backing it must be marked as uncorroborated"
    )


def test_anchor_tokens_fold_turkish_characters() -> None:
    """Sanity check that the anchor used across these tests folds Turkish properly."""
    anchor = build_anchor("Yağmur Özgan", EntityType.PERSON)
    assert anchor.tokens == name_tokens("Yagmur Ozgan"), f"Turkish folding failed: {anchor.tokens}"


def test_names_contradict_separates_shared_surname_namesakes() -> None:
    """The hard real-world case: same surname, different given name.

    Observed live — "Yilmaz Erdogan" and "Yigithan Erdogan" were merged into the
    "Yigit Erdogan" identity because they share the surname token, so neither a
    plain overlap ratio nor a zero-overlap mismatch check separated them.
    """
    from app.discovery.matching.cluster import names_contradict

    assert names_contradict("Yilmaz Erdogan", "Yigit Erdogan"), "different given names are different people"
    assert names_contradict("Yigithan Erdogan", "Yigit Erdogan"), "Yigithan is not Yigit"
    assert not names_contradict("Yigit Erdogan", "Yigit Erdogan (yigitrdgn)"), (
        "a subset relationship is one person written two ways"
    )
    assert not names_contradict("Yigit Erdogan", None), "an unknown name never contradicts"
    assert not names_contradict("Jane Doe", "John Smith"), (
        "no shared token at all is name_mismatch territory, not a same-surname conflict"
    )


def test_shared_surname_namesake_is_not_merged_into_the_elected_identity() -> None:
    anchor = _anchor()
    target = _candidate("github", "yigiterdogan", display_name="Yigit Erdogan", score=70)
    namesake = _candidate("pinterest", "yerdogan", display_name="Yilmaz Erdogan", score=30)

    clusters = build_clusters([target, namesake], anchor, (), ScoringContext())
    winner, _ = elect(clusters)

    assert winner is not None
    assert "pinterest:yerdogan" not in set(winner.member_keys), (
        "Yilmaz Erdogan shares only the surname and must stay out of Yigit Erdogan's profile"
    )


def test_shared_default_avatar_does_not_merge_two_identities() -> None:
    """A perceptual-hash match is never a merge edge on its own.

    Two unrelated accounts using a platform's default avatar produce an identical
    dhash; treating that as agreement fused two strangers into one identity.
    """
    anchor = _anchor()
    first = _candidate("github", "aaa", display_name="Ali Veli")
    second = _candidate("medium", "zzz", display_name="Ayse Fatma")
    first.avatar_dhash = second.avatar_dhash = "ffffffffffffffff"
    ctx = ScoringContext(avatar_dhash_index={"ffffffffffffffff": {"github:aaa", "medium:zzz"}})

    clusters = build_clusters([first, second], anchor, (), ctx)
    assert len(clusters) == 2, (
        f"a shared default avatar must not merge identities, got {[c.member_keys for c in clusters]}"
    )


def test_score_profile_penalises_a_shared_surname_namesake() -> None:
    anchor = _anchor()
    namesake = _candidate("pinterest", "yerdogan", display_name="Yilmaz Erdogan")
    score = score_profile(namesake, anchor, (), ScoringContext())
    codes = {r.code for r in score.reasons}
    assert "name_conflict" in codes, f"a different given name must be scored as a contradiction, got {codes}"
    assert "display_name_partial" not in codes, "a namesake must not also collect a partial-name bonus"


def test_breadth_alone_does_not_win_the_election() -> None:
    """A common surname is on many sites; that is not evidence it is the target.

    `cluster.score` is the subject confidence, and its largest term rewards being
    seen on many independent domains — precisely what a bare surname produces. On
    2026-08-29 a live search for "Yigit Erdogan" elected the handle `erdogan`
    across twelve platforms, every member scored out at 0-25, over a rival cluster
    whose members scored 54. Breadth beat attribution, and the answer described
    strangers.
    """
    wide = IdentityCluster(
        cluster_id="wide",
        members=[_candidate(f"p{i}", "erdogan", score=18) for i in range(12)],
    )
    wide.score = MatchScore(20, MatchBand.WEAK, ())

    focused = IdentityCluster(
        cluster_id="focused",
        members=[_candidate("facebook", "erdogan.yigit", score=54), _candidate("instagram", "erdogan.yigit", score=54)],
    )
    focused.score = MatchScore(5, MatchBand.REJECTED, ())

    winner, alternates = elect([wide, focused])

    assert winner.cluster_id == "focused", (
        f"the better-attributed identity must win, got {winner.cluster_id} "
        f"(alternates: {[c.cluster_id for c in alternates]})"
    )


def test_a_broad_and_well_attributed_cluster_still_wins() -> None:
    """Breadth still counts — it just cannot stand in for attribution."""
    broad = IdentityCluster(
        cluster_id="broad",
        members=[_candidate(f"p{i}", "yigtwxx", score=50) for i in range(8)],
    )
    broad.score = MatchScore(20, MatchBand.WEAK, ())

    narrow = IdentityCluster(cluster_id="narrow", members=[_candidate("x", "someone", score=55)])
    narrow.score = MatchScore(0, MatchBand.REJECTED, ())

    winner, _ = elect([broad, narrow])

    assert winner.cluster_id == "broad", "eight corroborating accounts must outrank one slightly better single hit"
