"""What the pipeline asks a human, and what it does with the reply.

THE "I DON'T KNOW" RULE
----------------------
Every question carries an implicit unknown option, surfaced with the reserved id
``__unknown__`` (and a skip option, ``__skip__``). An ``unknown`` answer, a
``skipped`` answer and a ``timed_out`` answer all mean exactly one thing: **we
still don't know**. They add no evidence and they apply no penalty, so
:func:`apply_answer` returns ``[]`` for all three.

:attr:`Answer.is_negative` is True only when the user picked the explicit "no"
option, ``__no__``. Treating silence as denial is the single most destructive
thing this layer could do: a user who walks away from the screen, or who simply
does not recognise a handle, would then demolish correct findings the evidence
already supports. Absence of an answer is not a "no", exactly as absence of
proof is not proof of absence elsewhere in this pipeline.

The generators below are deterministic rather than LLM-driven, so a given state
always produces the same question and every branch is unit-testable.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from app.discovery.types import EvidenceKind, MatchBand, PlatformStatus

UNKNOWN_OPTION_ID, SKIP_OPTION_ID = "__unknown__", "__skip__"
YES_OPTION_ID, NO_OPTION_ID = "__yes__", "__no__"

_FACT_KINDS: tuple[EvidenceKind, ...] = (EvidenceKind.EMPLOYER, EvidenceKind.SCHOOL)
_STRONG_BANDS: tuple[MatchBand, ...] = (MatchBand.LIKELY, MatchBand.CONFIRMED)
_UNSURE_LOW, _UNSURE_HIGH = 0.35, 0.60
_LOW_EVIDENCE, _MAX_OPTIONS = 3, 5


class QuestionKind(StrEnum):
    CONFIRM_PROFILE = "confirm_profile"
    CONFIRM_FACT = "confirm_fact"
    DISAMBIGUATE = "disambiguate"
    CONFIRM_AVATAR = "confirm_avatar"
    PROVIDE_HINT = "provide_hint"
    CHOOSE_DIRECTION = "choose_direction"


@dataclass(frozen=True, slots=True)
class QuestionOption:
    id: str
    label: str
    detail: str | None = None
    thumbnail_url: str | None = None


@dataclass(frozen=True, slots=True)
class Question:
    id: str
    kind: QuestionKind
    text: str
    options: tuple[QuestionOption, ...] = ()
    allow_free_text: bool = False
    allow_skip: bool = True
    allow_unknown: bool = True
    timeout_seconds: int = 120
    context: dict[str, Any] = field(default_factory=dict)
    semantic_hash: str = ""
    """``sha1(kind|subject)``: the identity of the *topic*, not of this instance."""

    def wire_options(self) -> list[dict[str, Any]]:
        """Options as the client sees them, with the implicit choices appended."""
        out = [asdict(opt) for opt in self.options]
        if self.allow_unknown:
            out.append(asdict(QuestionOption(UNKNOWN_OPTION_ID, "I don't know")))
        if self.allow_skip:
            out.append(asdict(QuestionOption(SKIP_OPTION_ID, "Skip")))
        return out


@dataclass(frozen=True, slots=True)
class Answer:
    question_id: str
    option_ids: tuple[str, ...] = ()
    text: str | None = None
    skipped: bool = False
    timed_out: bool = False
    unknown: bool = False

    @property
    def is_unresolved(self) -> bool:
        """ "We still don't know" — the three silences, collapsed into one test."""
        return self.skipped or self.timed_out or self.unknown or UNKNOWN_OPTION_ID in self.option_ids

    @property
    def is_negative(self) -> bool:
        """True ONLY for an explicit "no". Never for silence. See the module docstring."""
        return NO_OPTION_ID in self.option_ids and not (self.skipped or self.timed_out or self.unknown)

    @property
    def is_informative(self) -> bool:
        """The reply told us something we can act on."""
        useful = any(oid != SKIP_OPTION_ID for oid in self.option_ids) or bool((self.text or "").strip())
        return not self.is_unresolved and useful


def semantic_hash(kind: QuestionKind, subject: str) -> str:
    """Stable identity of a question topic. Same topic -> same hash -> asked once."""
    return hashlib.sha1(f"{kind}|{subject}".encode()).hexdigest()[:16]


def _question(
    kind: QuestionKind,
    subject: str,
    text: str,
    *,
    options: Sequence[QuestionOption] = (),
    allow_free_text: bool = False,
    context: dict[str, Any] | None = None,
) -> Question:
    digest = semantic_hash(kind, subject)
    opts, ctx = tuple(options), context or {}
    return Question(f"q_{digest}", kind, text, opts, allow_free_text, context=ctx, semantic_hash=digest)


# -- generators --------------------------------------------------------------
# `state` is duck-typed: the discovery loop owns the real object, this module only
# reads from it, and every attribute below is optional and defaulted. Read here:
# `clusters` (IdentityCluster, best first, [0] is the elected one), `candidates`
# (ProfileCandidate), `anchor` (Anchor), `round_no`, `questions_asked` (the set of
# semantic hashes already put to the user), `budget_questions_left`, `evidence`
# (Evidence) and `pictures` (StoredAvatar: .sha256 .dhash .local_url .platform
# .username).


def _read(state: Any, name: str, default: Any) -> Any:
    value = getattr(state, name, default)
    return default if value is None else value


def _disambiguate(state: Any) -> Question | None:
    """Two strong, differently-labelled identities: only a human can pick one."""
    strong = [c for c in _read(state, "clusters", []) if c.score.band in _STRONG_BANDS and c.label]
    if len(strong) < 2 or len({c.label for c in strong}) < 2:
        return None
    chosen = strong[:_MAX_OPTIONS]
    ids = [c.cluster_id for c in chosen]
    return _question(
        QuestionKind.DISAMBIGUATE,
        "|".join(sorted(ids)),
        "Several different people match this name. Which one are you looking for?",
        options=[QuestionOption(id=c.cluster_id, label=c.label) for c in chosen],
        context={"cluster_ids": ids},
    )


def _confirm_avatar(state: Any) -> Question | None:
    """The elected identity shows visually different faces — pick the real one."""
    keys = set(clusters[0].member_keys) if (clusters := _read(state, "clusters", [])) else set()
    distinct: dict[str, Any] = {}
    for pic in _read(state, "pictures", []):
        if not keys or f"{pic.platform}:{str(pic.username).lower()}" in keys:
            distinct.setdefault(pic.dhash, pic)
    if len(distinct) < 2:
        return None
    top = [distinct[d] for d in sorted(distinct)][:_MAX_OPTIONS]
    opts = [QuestionOption(id=p.sha256, label=f"{p.platform}/{p.username}", thumbnail_url=p.local_url) for p in top]
    return _question(
        QuestionKind.CONFIRM_AVATAR,
        "|".join(sorted(distinct)),
        "These profiles show different pictures. Which one is the person you mean?",
        options=opts,
        context={"sha256": [p.sha256 for p in top]},
    )


def _confirm_profile(state: Any) -> Question | None:
    """The best candidate is only "possible" (40-59) — one yes/no settles it."""
    live = [c for c in _read(state, "candidates", []) if c.is_live and not (c.user_confirmed or c.user_rejected)]
    if not live:
        return None
    top = max(live, key=lambda c: (c.score.value, c.platform, c.username))
    if top.score.band is not MatchBand.POSSIBLE:
        return None
    return _question(
        QuestionKind.CONFIRM_PROFILE,
        top.key,
        f"Is {top.url} the account you are looking for?",
        options=[
            QuestionOption(id=YES_OPTION_ID, label="Yes, that's them", detail=top.url),
            QuestionOption(id=NO_OPTION_ID, label="No, that's someone else"),
        ],
        context={"candidate_key": top.key, "platform": top.platform, "username": top.username},
    )


def _confirm_fact(state: Any) -> Question | None:
    """Employer/school claims that contradict each other, or that we half-believe."""
    for kind in _FACT_KINDS:
        items = [ev for ev in _read(state, "evidence", []) if ev.kind is kind and ev.value.strip()]
        values = sorted({ev.value.strip() for ev in items})
        if len(values) >= 2:
            prompt = f"Sources disagree about {kind}. Which one is right?"
        elif len(values) == 1 and any(_UNSURE_LOW <= ev.confidence <= _UNSURE_HIGH for ev in items):
            prompt = f"We are only half sure about this {kind}. Is it correct?"
        else:
            continue
        options = [QuestionOption(id=f"{kind}={v}", label=v) for v in values[:_MAX_OPTIONS]]
        options.append(QuestionOption(id=NO_OPTION_ID, label="None of these"))
        return _question(
            QuestionKind.CONFIRM_FACT,
            f"{kind}:{'|'.join(values)}",
            prompt,
            options=options,
            context={"kind": str(kind), "values": values},
        )
    return None


def _provide_hint(state: Any) -> Question | None:
    """Round 1 found almost nothing — one free-text hint is worth more rounds."""
    if int(_read(state, "round_no", 0)) != 1 or len(_read(state, "evidence", [])) >= _LOW_EVIDENCE:
        return None
    return _question(
        QuestionKind.PROVIDE_HINT,
        "low_evidence",
        "We found almost nothing. Any detail helps: a username, a city, an employer or a link.",
        allow_free_text=True,
    )


def _choose_direction(state: Any) -> Question | None:
    """Two platforms refused us; the user decides where the remaining effort goes."""
    candidates = _read(state, "candidates", [])
    blocked = sorted({c.platform for c in candidates if c.platform_status is PlatformStatus.BLOCKED})[:_MAX_OPTIONS]
    if len(blocked) < 2:
        return None
    return _question(
        QuestionKind.CHOOSE_DIRECTION,
        "|".join(blocked),
        "These platforms refused us. Which one should we spend the remaining effort on?",
        options=[QuestionOption(id=f"platform:{p}", label=p, detail="retry, slower and stealthier") for p in blocked],
        context={"blocked": blocked},
    )


_GENERATORS: tuple[Callable[[Any], Question | None], ...] = (
    _disambiguate,
    _confirm_avatar,
    _confirm_profile,
    _confirm_fact,
    _provide_hint,
    _choose_direction,
)


def maybe_ask(state: Any) -> Question | None:
    """First matching generator wins. At most one question per round."""
    if int(_read(state, "budget_questions_left", 0)) <= 0:
        return None
    asked: set[str] = set(_read(state, "questions_asked", set()))
    for generate in _GENERATORS:
        question = generate(state)
        if question is not None and question.semantic_hash not in asked:
            return question
    return None


def apply_answer(question: Question, answer: Answer) -> list[tuple[str, str]]:
    """Translate a reply into ``(effect, value)`` pairs the loop can act on.

    Returns ``[]`` for unknown, skipped and timed-out answers — no evidence and
    no penalty, because none of those three told us anything about the target.
    """
    if answer.is_unresolved:
        return []
    ids = [oid for oid in answer.option_ids if oid not in (SKIP_OPTION_ID, UNKNOWN_OPTION_ID)]
    context, kind = question.context, question.kind

    if kind is QuestionKind.PROVIDE_HINT:
        text = (answer.text or "").strip()
        return [("hint", text)] if text else []
    if kind is QuestionKind.DISAMBIGUATE:
        return [("set_anchor_cluster", oid) for oid in ids]
    if kind is QuestionKind.CONFIRM_AVATAR:
        return [("select_avatar", oid) for oid in ids]
    if kind is QuestionKind.CHOOSE_DIRECTION:
        return [("focus_platform", oid.split(":", 1)[1]) for oid in ids if oid.startswith("platform:")]
    if kind is QuestionKind.CONFIRM_PROFILE:
        key = str(context.get("candidate_key", ""))
        if not key or NO_OPTION_ID in ids:
            return [("reject_candidate", key)] if key and NO_OPTION_ID in ids else []
        return [("confirm_candidate", key)] if YES_OPTION_ID in ids else []
    if kind is QuestionKind.CONFIRM_FACT:
        if NO_OPTION_ID in ids:
            return [("reject_fact", f"{context.get('kind', '')}={v}") for v in context.get("values", [])]
        return [("add_fact", oid) for oid in ids if "=" in oid]
    return []
