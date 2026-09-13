"""API schemas for the discovery pipeline.

Two shapes here exist specifically to fix failures of the old contract:

* ``SocialProfile`` replaces fifteen comma-joined ``*_url`` strings. A profile now
  carries its own status, so "we were blocked" is expressible; the old shape could
  only say "empty", which read identically to "nothing exists".
* ``ProfilePicture`` exists at all. There was previously no picture field —
  avatars were prefixed into the AI text as markdown, so a dead URL rendered as a
  broken image inside the biography.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

PlatformStatusLiteral = Literal["found", "not_found", "blocked", "error", "unsupported"]
MatchBandLiteral = Literal["confirmed", "likely", "possible", "weak", "rejected"]


class MatchReason(BaseModel):
    """One named contribution to a confidence score, in plain language."""

    code: str
    text: str
    points: float


class ProfilePicture(BaseModel):
    """A downloaded avatar, served from our own storage.

    The URL is local because Instagram and TikTok hand out signed CDN links that
    expire within hours — storing those produces broken images a day later.
    """

    url: str
    platform: str
    source_url: str | None = None
    width: int | None = None
    height: int | None = None
    sha256: str | None = None
    dhash: str | None = None
    is_primary: bool = False


class SocialProfile(BaseModel):
    """One account, with its verdict and the reasoning behind it."""

    platform: str
    url: str | None = None
    username: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    bio: str | None = None
    followers: int | None = None
    following: int | None = None
    posts: int | None = None
    verified: bool | None = None
    last_activity: str | None = None
    status: PlatformStatusLiteral
    status_detail: str | None = None
    """Why, in human terms: "HTTP 999 auth wall", "captcha after stealth escalation"."""

    confidence: int = Field(default=0, ge=0, le=100)
    band: MatchBandLiteral = "possible"
    reasons: list[MatchReason] = Field(default_factory=list)
    outbound_links: list[str] = Field(default_factory=list)
    checked_at: str | None = None


class WorkRecord(BaseModel):
    organization: str
    organization_normalized: str | None = None
    role: str | None = None
    start: str | None = None
    end: str | None = None
    is_current: bool | None = None
    source_url: str
    extractor: str
    confidence: int = Field(default=0, ge=0, le=100)


class EducationRecord(BaseModel):
    institution: str
    institution_normalized: str | None = None
    degree: str | None = None
    field_of_study: str | None = None
    start: str | None = None
    end: str | None = None
    source_url: str
    extractor: str
    confidence: int = Field(default=0, ge=0, le=100)


class EvidenceItem(BaseModel):
    """One recorded fact with its provenance."""

    kind: str
    subject: str
    value: str
    platform: str | None = None
    source_url: str
    source_domain: str
    source_kind: str
    extractor: str
    confidence: float = Field(ge=0.0, le=1.0)
    observed_at: str
    round: int = 0
    fingerprint: str


class ContactOut(BaseModel):
    """One public contact detail, with the page that published it.

    The flat `email_addresses` / `phone_numbers` lists are kept as a derived
    projection for the legacy consumers, but they are not the source of truth: a
    bare string cannot say which page said so, how sure we are, or whether two
    independent sites agreed. Invariant 4 applies to a phone number exactly as it
    applies to a sentence in the biography.
    """

    kind: Literal["email", "phone"]
    value: str
    """Normalised: lower-cased address, or E.164 where the region was known."""
    display: str | None = None
    """As written on the page — the form a reader can find again."""
    source_url: str
    source_domain: str
    extractor: str
    confidence: float = Field(ge=0.0, le=1.0)
    corroborations: int = Field(default=1, ge=1)
    """Distinct source domains asserting this value."""
    observed_at: str
    fingerprint: str


class NarrativeClaim(BaseModel):
    """One sentence of the biography, tied to the evidence that supports it.

    A claim with no fingerprints never reaches the response — that is what stops
    the model inventing a fluent sentence about the wrong person.
    """

    text: str
    evidence_fingerprints: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    confidence: int = Field(default=0, ge=0, le=100)


class GraphNode(BaseModel):
    id: str
    type: str
    label: str
    platform: str | None = None
    confidence: int = 0
    url: str | None = None


class GraphEdge(BaseModel):
    source: str
    target: str
    kind: str
    weight: float = 1.0
    evidence_fingerprints: list[str] = Field(default_factory=list)


class RelationshipGraph(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


class TimelineEvent(BaseModel):
    when: str
    kind: str
    label: str
    source_url: str
    confidence: int = 50
    platform: str | None = None


class DiscoveryQuestionRecord(BaseModel):
    """A question we asked mid-search and what came back."""

    question_id: str
    kind: str
    text: str
    answer: str | None = None
    skipped: bool = False
    timed_out: bool = False
    unknown: bool = False
    asked_at: str


class DiscoverySummary(BaseModel):
    """How the search ran, so a thin result is explainable rather than mysterious."""

    session_id: str
    entity_type: Literal["person", "company", "place"] = "person"
    rounds: int = 0
    termination_reason: str = ""
    evidence_total: int = 0
    evidence_reused: int = 0
    questions: list[DiscoveryQuestionRecord] = Field(default_factory=list)
    platform_status: dict[str, PlatformStatusLiteral] = Field(default_factory=dict)
    engine_status: dict[str, str] = Field(default_factory=dict)
    fetch_stats: dict[str, Any] = Field(default_factory=dict)
    notices: list[str] = Field(default_factory=list)
    """Honest caveats: blocked platforms, disabled stealth, reused prior evidence."""

    duration_ms: int = 0


class SessionStartResponse(BaseModel):
    session_id: str
    target_key: str
    stream_url: str
    answer_url: str
    status: str = "running"


class AnswerRequest(BaseModel):
    question_id: str
    option_ids: list[str] = Field(default_factory=list)
    text: str | None = Field(default=None, max_length=500)
    skipped: bool = False
    unknown: bool = False
    """Set by the "I don't know" button. Semantically identical to a timeout:
    it adds nothing and — critically — penalises nothing."""


class AnswerAck(BaseModel):
    accepted: bool
    session_status: str
    detail: str | None = None


class PlatformInfo(BaseModel):
    """One selectable platform, as the picker needs to render it."""

    key: str
    display: str
    category: str
    entity_types: list[str]
    expected_reliability: float
    requires_stealth: bool
    """True when the platform only answers to a real browser. Those are the slow
    ones, so the picker can say why deselecting them speeds a search up."""

    supported: bool = True
    """False when no anonymous route can tell a real account from an invented one.

    Such a platform is served, not hidden: the picker has to be able to say why it
    cannot be chosen. Dropping it from the catalogue would answer the question by
    disappearance, and a user who ticked Spotify yesterday would simply find it
    gone."""

    unsupported_reason: str | None = None
    """The one-line why, straight from the registry. `None` when supported."""

    discovery_only: bool = False
    """True when the platform is dorked and reported but never probed.

    A weaker caveat than `supported=False`, and a different one: the account is
    findable, it just cannot be *confirmed* by asking the platform. Spotify is
    the case — every handle answers 200, real or invented — so a hit there comes
    from a search engine or a link, or not at all. Conflating the two is what
    made a Spotify profile URL we already held get reported as no account."""

    discovery_only_reason: str | None = None
    """The one-line why, straight from the registry. `None` when probeable."""


class PlatformCatalog(BaseModel):
    """The CORE catalogue. EXTENDED is deliberately absent: it is a single
    on/off switch, not 120 checkboxes."""

    platforms: list[PlatformInfo]
    extended_count: int
    extended_min_depth: int
    """Depth at which the long tail unlocks on its own, so the UI can say so."""


# -- Search brief ---------------------------------------------------------------


class KnownProfileOut(BaseModel):
    """A profile URL the parser recognised, echoed back so the UI can show it."""

    platform: str
    username: str
    canonical_url: str
    raw_url: str


class ReferenceAvatarOut(BaseModel):
    """The reference picture, identified by its own digest.

    Two file fingerprints and nothing else — no face template exists, and the UI
    is expected to say so rather than promising face recognition.
    """

    sha256: str
    dhash: str
    preview_url: str
    source: Literal["upload", "known_profile"] = "upload"


class SearchBriefIn(BaseModel):
    """The structured half of a search request.

    Every field is optional. A brief narrows a search; it never has to be
    complete, and an empty one leaves the search exactly as it was.
    """

    name: str | None = Field(default=None, max_length=200)
    gender: Literal["male", "female", "unknown"] = "unknown"
    known_profiles: list[str] = Field(
        default_factory=list,
        description=(
            "Profile URLs the user already knows. Each pins its platform: that platform is not searched "
            "and returns exactly the given account. Anything that is not a recognised profile URL is a 422."
        ),
    )
    usernames: list[str] = Field(default_factory=list, max_length=10)
    location: str | None = Field(default=None, max_length=120)
    employer: str | None = Field(default=None, max_length=120)
    school: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=254)
    domain: str | None = Field(default=None, max_length=253)
    reference_image_id: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
        description="sha256 returned by POST /api/search/brief/avatar.",
    )

    @field_validator("known_profiles")
    @classmethod
    def _validate_known_profiles(cls, value: list[str]) -> list[str]:
        """Reject anything the URL matcher does not recognise as a profile.

        Loudly, not silently. A URL we cannot place would otherwise be dropped on
        the floor, and the user would watch the search ignore the one fact they
        were most sure about.
        """
        from app.config import get_settings
        from app.discovery.platforms.urlmatch import match_profile_url

        cleaned = [item.strip() for item in value if item and item.strip()]
        if not cleaned:
            return []
        limit = get_settings().discovery_brief_max_known_profiles
        if len(cleaned) > limit:
            raise ValueError(f"at most {limit} known profile(s) per search")
        unrecognised = [url for url in cleaned if match_profile_url(url) is None]
        if unrecognised:
            raise ValueError(f"not recognised as profile URL(s): {', '.join(unrecognised[:3])}")
        return list(dict.fromkeys(cleaned))


class SearchBriefOut(BaseModel):
    """A parsed brief, as the editable chip renders it."""

    name: str
    gender: Literal["male", "female", "unknown"]
    known_profiles: list[KnownProfileOut] = Field(default_factory=list)
    usernames: list[str] = Field(default_factory=list)
    location: str | None = None
    employer: str | None = None
    school: str | None = None
    email: str | None = None
    domain: str | None = None
    reference_avatar: ReferenceAvatarOut | None = None
    unparsed: list[str] = Field(default_factory=list)
    """What the parser could not place. Shown to the user rather than guessed at."""

    is_empty: bool = True
    """True when the brief carries nothing beyond the name, so the UI can hide the chip."""


class BriefParseRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=600)
    entity_type: Literal["person", "company", "place"] = "person"


class ReferenceAvatarResponse(BaseModel):
    """What an uploaded reference photo became."""

    sha256: str
    dhash: str
    preview_url: str
    width: int | None = None
    height: int | None = None
    bytes_len: int
    content_type: str
