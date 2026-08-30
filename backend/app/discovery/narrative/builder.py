"""Assemble a biography from the elected cluster's evidence, and nothing else.

Two rules carry this module:

1. **The input is the elected cluster alone.** Never the full candidate pool.
   That single restriction is what makes the output describe one person: the
   model cannot blend a namesake's employer into the biography if the namesake's
   evidence was never in the prompt.
2. **Every sentence is verified after generation** by :mod:`grounding`. The model
   proposes; the evidence disposes.

When the model is unreachable, or when every claim it proposed was rejected, the
report does not degrade to silence — a deterministic template builds the same
biography straight from the structured records, each sentence still carrying the
fingerprints it rests on. The LLM is an enrichment here, not a dependency.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from app.discovery.evidence.model import Evidence
from app.discovery.identity.normalize import fold_ascii
from app.discovery.identity.workedu import EducationRecord, WorkRecord
from app.discovery.matching.candidate import ProfileCandidate
from app.discovery.matching.cluster import IdentityCluster
from app.discovery.narrative.grounding import Claim, GroundingReport, build_evidence_index, verify_claims
from app.discovery.types import MatchBand
from app.services.llm_json import stream_json_items
from app.utils.logger import logger

ATTRIBUTABLE_BANDS: frozenset[MatchBand] = frozenset({MatchBand.POSSIBLE, MatchBand.LIKELY, MatchBand.CONFIRMED})
"""Bands the answer may attribute to the target.

`weak` (20-39) is the score of an account that shares a name fragment and nothing
else. Naming one in the biography reads as a finding while the notice beside it
says nothing was established, so both sides use this one definition.
"""

NOTHING_ESTABLISHED = "No verified information could be established for this target."
"""Returned verbatim when there is genuinely nothing. Filler is worse than nothing."""

MAX_EVIDENCE_LINES = 60
"""Prompt budget. Evidence is pre-sorted by confidence, so the cut keeps the best."""

CLAIMS_ARRAY_KEY = "claims"
"""The array `stream_json_items` cuts objects out of. Named once, used twice."""

DEFAULT_STREAM_BUDGET_S = 120.0
"""Used when no caller imposes one — the runner always does."""

_MAX_CLAIM_TOKENS = 8192
"""A generous ceiling on purpose: qwen3.5 is a hybrid reasoning model and will
happily spend thousands of tokens deliberating over a dozen evidence lines. Too
small a budget and it is still thinking when it is cut off, which reaches us as
an empty answer. If it still runs out, the deterministic template below produces
a correct, grounded biography — so this is a quality knob, never a correctness
one."""

_SYSTEM = (
    "You are an OSINT analyst writing from a fixed evidence list. "
    "You state facts that appear in the evidence and nothing else. "
    "You never speculate, never infer, and never add background knowledge of your own."
)


@dataclass(frozen=True, slots=True)
class Narrative:
    """The biography, plus the full audit trail that produced it."""

    text: str
    claims: tuple[Claim, ...]
    grounding: GroundingReport
    used_llm: bool
    language: str = "en"
    truncated: bool = False
    """The budget ran out mid-write and only the verified prefix is here.

    Meaningful only because claims are streamed: each one is grounded on its own
    before it is published, so an interrupted biography is a shorter true one
    rather than a sentence cut in half. `narrative_notices` says so out loud."""


class NarrativeBuilder:
    """Builds one grounded biography per elected cluster."""

    def __init__(self, *, enabled: bool = True) -> None:
        self._enabled = enabled

    async def build(
        self,
        *,
        cluster: IdentityCluster,
        profiles: Sequence[ProfileCandidate],
        work: Sequence[WorkRecord],
        education: Sequence[EducationRecord],
        subject_name: str,
        entity_type: str = "person",
    ) -> Narrative:
        """Write the biography for ``cluster``, with nothing watching.

        A thin delegation on purpose. Two entry points would mean two LLM calls
        with two prompts, and this module already carries the scar of a blocking
        route and a session route serving different biographies for one input.
        """
        return await self.stream(
            cluster=cluster,
            profiles=profiles,
            work=work,
            education=education,
            subject_name=subject_name,
            entity_type=entity_type,
        )

    async def stream(
        self,
        *,
        cluster: IdentityCluster,
        profiles: Sequence[ProfileCandidate],
        work: Sequence[WorkRecord],
        education: Sequence[EducationRecord],
        subject_name: str,
        entity_type: str = "person",
        budget_s: float | None = None,
        on_claim: Callable[[Claim, str], Awaitable[None]] | None = None,
    ) -> Narrative:
        """Write the biography, handing each sentence to ``on_claim`` as it lands.

        ``on_claim`` receives only sentences that have already passed the
        grounding gate, so a sentence on the wire is a sentence in the result.
        Its second argument is ``"model"`` or ``"template"`` — the reader is
        entitled to know which of the two wrote what they are looking at.

        ``profiles`` is expected to already be a subset of the elected cluster's
        members; anything outside it is dropped here as a second line of defence,
        because a profile from another cluster in this prompt is exactly the bug
        this whole module exists to prevent.
        """
        members = _cluster_members(cluster, profiles)
        evidence = _rank_evidence(cluster.evidence)

        if not evidence and not members and not work and not education:
            empty = GroundingReport(accepted=(), rejected=())
            return Narrative(text=NOTHING_ESTABLISHED, claims=(), grounding=empty, used_llm=False)

        report = await self._llm_claims(
            evidence=evidence,
            members=members,
            work=work,
            education=education,
            subject_name=subject_name,
            entity_type=entity_type,
            budget_s=budget_s if budget_s is not None else DEFAULT_STREAM_BUDGET_S,
            on_claim=on_claim,
        )
        if report is not None and report.accepted:
            return Narrative(
                text=" ".join(claim.text for claim in report.accepted),
                claims=report.accepted,
                grounding=report,
                used_llm=True,
            )

        # Either the daemon was unreachable or every proposed claim was rejected.
        # Both mean the same thing to the reader: fall back to the template, which
        # can only restate structured records and therefore cannot hallucinate.
        fallback = _template_claims(
            subject_name=subject_name,
            members=members,
            work=work,
            education=education,
            evidence=evidence,
        )
        if not fallback:
            return Narrative(
                text=NOTHING_ESTABLISHED,
                claims=(),
                grounding=report or GroundingReport(accepted=(), rejected=()),
                used_llm=False,
            )
        # Emitted in one burst rather than streamed: `_template_claims` is a
        # synchronous pure function over records already in memory, so revealing
        # it a word at a time would be an animation pretending to be generation.
        # There is no conflict with claims already published — this branch is
        # only reached when the model's were all rejected, and a rejected claim
        # never reaches `on_claim`.
        if on_claim is not None:
            for claim in fallback:
                await on_claim(claim, "template")
        merged = GroundingReport(accepted=fallback, rejected=report.rejected if report else ())
        return Narrative(
            text=" ".join(claim.text for claim in fallback),
            claims=fallback,
            grounding=merged,
            used_llm=False,
        )

    async def _llm_claims(
        self,
        *,
        evidence: Sequence[Evidence],
        members: Sequence[ProfileCandidate],
        work: Sequence[WorkRecord],
        education: Sequence[EducationRecord],
        subject_name: str,
        entity_type: str,
        budget_s: float,
        on_claim: Callable[[Claim, str], Awaitable[None]] | None,
    ) -> GroundingReport | None:
        """Stream claims and verify each one as it lands. None when unavailable.

        `verify_claims` is called with a one-element list rather than through a
        new singular helper. It carries no state between claims — every branch
        reads only that claim and the read-only evidence index — so the verdict
        is identical either way, and a second entry point into the
        anti-hallucination gate is how the two would drift apart.
        """
        if not self._enabled or not evidence:
            return None

        lines, index = build_evidence_index(evidence)
        prompt = _build_prompt(
            lines=lines,
            members=members,
            work=work,
            education=education,
            subject_name=subject_name,
            entity_type=entity_type,
        )

        accepted: list[Claim] = []
        rejected: list[tuple[str, str]] = []
        proposed = 0
        async for raw in stream_json_items(
            prompt,
            array_key=CLAIMS_ARRAY_KEY,
            budget_s=budget_s,
            system=_SYSTEM,
            max_output_tokens=_MAX_CLAIM_TOKENS,
        ):
            proposed += 1
            verdict = verify_claims([raw], index)
            accepted.extend(verdict.accepted)
            rejected.extend(verdict.rejected)
            if verdict.accepted and on_claim is not None:
                await on_claim(verdict.accepted[0], "model")

        if proposed == 0:
            # Unreachable daemon, an empty array, a reply the scanner never found
            # an array in: all three mean the same thing to the caller, which is
            # to fall through to the template.
            return None
        # One line after the stream closes, not one per rejection: a model having
        # a bad run would otherwise write a page of warnings.
        if rejected:
            logger.log_warning(f"narrative: dropped {len(rejected)} ungrounded claim(s) of {proposed} proposed")
        return GroundingReport(accepted=tuple(accepted), rejected=tuple(rejected))


def _cluster_members(cluster: IdentityCluster, profiles: Sequence[ProfileCandidate]) -> list[ProfileCandidate]:
    """Members the biography may speak for: live, elected, and not scored out.

    `elect` always returns a winner, so an all-but-hopeless run still produces a
    cluster. Watched live on 2026-08-29: every engine refused us, the winning
    cluster was the bare surname `erdogan` on twelve platforms with every member
    in the `rejected` band, and the biography opened "Yigit Erdogan is linked to
    12 confirmed account(s)" over a list of strangers. The scorer had already said
    no; nothing downstream was listening.
    """
    allowed = {member.key for member in cluster.members}
    chosen = [p for p in profiles if p.key in allowed and p.is_live] or list(cluster.live_members)
    return [p for p in chosen if p.score.band in ATTRIBUTABLE_BANDS]


def _rank_evidence(evidence: Sequence[Evidence]) -> list[Evidence]:
    """Highest-confidence evidence first, capped to the prompt budget."""
    ordered = sorted(evidence, key=lambda e: (-e.confidence, str(e.kind), e.subject, e.value))
    return ordered[:MAX_EVIDENCE_LINES]


def _build_prompt(
    *,
    lines: Sequence[str],
    members: Sequence[ProfileCandidate],
    work: Sequence[WorkRecord],
    education: Sequence[EducationRecord],
    subject_name: str,
    entity_type: str,
) -> str:
    accounts = ", ".join(f"{m.platform}:{m.username}" for m in members) or "none"
    employers = ", ".join(w.organization for w in work) or "none recorded"
    schools = ", ".join(e.institution for e in education) or "none recorded"
    evidence_block = "\n".join(lines)
    return (
        f'Subject: "{subject_name}" (entity type: {entity_type}).\n'
        f"Confirmed accounts: {accounts}.\n"
        f"Recorded employers: {employers}.\n"
        f"Recorded education: {schools}.\n\n"
        f"Numbered evidence:\n{evidence_block}\n\n"
        "Write short factual sentences about this subject. Rules:\n"
        "1. Every sentence must be supported by at least one numbered evidence line.\n"
        '2. Cite the ids you used in evidence_ids, e.g. ["E7", "E12"].\n'
        "3. Never state a name, organisation, place, number or year that does not "
        "appear verbatim in the evidence you cite.\n"
        "4. Omit anything the evidence does not support. Fewer sentences is correct; "
        "speculation is not.\n"
        "5. Write in English, third person, present tense. No praise, no adjectives of quality.\n\n"
        'Return JSON: {"claims": [{"text": "...", "evidence_ids": ["E1"]}]}'
    )


def _template_claims(
    *,
    subject_name: str,
    members: Sequence[ProfileCandidate],
    work: Sequence[WorkRecord],
    education: Sequence[EducationRecord],
    evidence: Sequence[Evidence],
) -> tuple[Claim, ...]:
    """Deterministic biography built straight from structured records.

    Each sentence is emitted only when evidence supporting it exists, and carries
    that evidence's fingerprints — so a fallback claim is exactly as auditable as
    an LLM one.
    """
    claims: list[Claim] = []

    def add(text: str, backing: Sequence[Evidence]) -> None:
        supporting = [item for item in backing if item.fingerprint]
        if not supporting:
            return
        mean = sum(item.confidence for item in supporting) / len(supporting)
        claims.append(
            Claim(
                text=text,
                evidence_fingerprints=tuple(dict.fromkeys(item.fingerprint for item in supporting)),
                source_urls=tuple(dict.fromkeys(item.source_url for item in supporting if item.source_url)),
                confidence=round(100 * mean),
            )
        )

    if members:
        accounts = ", ".join(f"{m.platform} (@{m.username})" for m in members[:8])
        backing = _evidence_for_members(members, evidence) or list(evidence[:1])
        # "confirmed" is the scorer's word and this sentence cannot borrow it —
        # members here range from `weak` to `confirmed`. Say what is true of all
        # of them: they were attributed to this identity.
        add(f"{subject_name} is linked to {len(members)} account(s): {accounts}.", backing)

    for record in work[:3]:
        backing = _evidence_matching(evidence, record.organization)
        role = f" as {record.role}" if record.role else ""
        add(f"{subject_name} is associated with {record.organization}{role}.", backing)

    for record in education[:3]:
        add(
            f"{subject_name} is associated with {record.institution}.", _evidence_matching(evidence, record.institution)
        )

    locations = [m.location for m in members if m.location]
    if locations:
        add(f"{subject_name} is reported to be located in {locations[0]}.", _evidence_matching(evidence, locations[0]))

    return tuple(claims)


def _evidence_for_members(members: Sequence[ProfileCandidate], evidence: Sequence[Evidence]) -> list[Evidence]:
    keys = {m.key for m in members}
    platforms = {m.platform for m in members}
    return [item for item in evidence if item.subject in keys or item.platform in platforms]


def _evidence_matching(evidence: Sequence[Evidence], value: str) -> list[Evidence]:
    """Evidence whose subject or value mentions ``value``, ASCII-folded both ways."""
    needle = fold_ascii(value).strip()
    if not needle:
        return []
    return [item for item in evidence if needle in fold_ascii(f"{item.subject} {item.value}")]
