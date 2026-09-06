"""Evidence grounding: the lock that keeps a biography describing ONE person.

The old pipeline handed every finding matching a name straight to the LLM and
asked for a biography. The model obliged, fluently, and produced a single
paragraph blending three strangers who happened to share a name — the Istanbul
engineer's employer, the Ankara doctor's degree, the third man's city. A
composite answer is worse than a wrong one: a wrong answer can be corrected,
a composite one cannot even be evaluated, because no single fact in it is
false, only their conjunction.

Grounding makes that structurally impossible rather than merely discouraged. The
model no longer writes prose; it proposes *claims*, each citing the evidence ids
it rests on. Every claim is then checked against the stored evidence it cited,
and a sentence that cannot be traced back is dropped — not softened, not
hedged, not prefixed with "possibly". Dropped.

The check is deliberately blunt: every proper noun, number and year in the claim
must occur in the cited evidence. That will occasionally reject a true sentence
whose phrasing wandered. That trade is correct here — a missing fact costs the
reader one line, an invented employer costs them the whole report's credibility
and quietly corroborates the wrong person in later rounds.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.discovery.evidence.model import Evidence
from app.discovery.identity.normalize import fold_ascii
from app.discovery.identity.workedu import is_grounded

MIN_CLAIM_LENGTH = 8
"""Shorter than this is not a sentence — it is a fragment the model gave up on."""

_EVIDENCE_ID = re.compile(r"^E\d+$")


@dataclass(frozen=True, slots=True)
class Claim:
    """One sentence of the biography, with the evidence that permits it."""

    text: str
    evidence_fingerprints: tuple[str, ...]
    source_urls: tuple[str, ...]
    confidence: int
    """0-100, the mean confidence of the evidence this claim rests on."""


@dataclass(frozen=True, slots=True)
class GroundingReport:
    """The verdict on a batch of proposed claims, including what was thrown away."""

    accepted: tuple[Claim, ...]
    rejected: tuple[tuple[str, str], ...]
    """``(claim text, reason)`` — kept so a rejected claim is auditable, not invisible."""

    @property
    def acceptance_rate(self) -> float:
        total = len(self.accepted) + len(self.rejected)
        return round(len(self.accepted) / total, 4) if total else 0.0


def build_evidence_index(evidence: Sequence[Evidence]) -> tuple[list[str], dict[str, Evidence]]:
    """Return ``(numbered prompt lines, id -> Evidence)``.

    Ids are positional (``E1``, ``E2``, ...) so the model can cite them cheaply
    and so a citation is verifiable without trusting anything the model wrote.
    """
    lines: list[str] = []
    index: dict[str, Evidence] = {}
    for position, item in enumerate(evidence, start=1):
        evidence_id = f"E{position}"
        index[evidence_id] = item
        domain = item.source_domain or "unknown"
        lines.append(
            f'[{evidence_id}] {item.subject} = "{item.value}"  (source: {domain}, confidence {item.confidence:.2f})'
        )
    return lines, index


def _cited_evidence(raw_ids: Any, index: dict[str, Evidence]) -> tuple[list[Evidence], str | None]:
    """Resolve the model's cited ids. Returns ``(evidence, rejection reason)``."""
    if not isinstance(raw_ids, list | tuple):
        return [], "cites no evidence id"
    ids = [str(value).strip().upper() for value in raw_ids if str(value).strip()]
    if not ids:
        return [], "cites no evidence id"

    # A mis-numbered citation is far more common than an invented fact, and
    # throwing the whole sentence away for one bad id discarded claims that the
    # remaining citations fully supported. Drop what does not resolve, keep what
    # does, and reject only when nothing is left — the grounding gate below still
    # has to pass against exactly the evidence that survived here.
    resolved: list[Evidence] = []
    unknown: list[str] = []
    for evidence_id in ids:
        if not _EVIDENCE_ID.match(evidence_id) or evidence_id not in index:
            unknown.append(evidence_id)
            continue
        resolved.append(index[evidence_id])
    if not resolved:
        return [], f"cites unknown evidence id {unknown[0]!r}"
    return resolved, None


def _cited_text(evidence: Sequence[Evidence]) -> str:
    """The searchable surface of the cited evidence: its subjects and values.

    ``source_url`` is deliberately excluded — a domain name appearing in a URL is
    not the source *asserting* anything, and letting it ground a claim would make
    "works at Getir" verifiable by any page hosted on getir.com.
    """
    return " ".join(f"{item.subject} {item.value}" for item in evidence)


def verify_claims(raw_claims: Sequence[dict[str, Any]], index: dict[str, Evidence]) -> GroundingReport:
    """Accept only the claims that the cited evidence actually supports.

    A claim is rejected when it cites nothing, cites an id that does not exist,
    is too short to be a sentence, or names an entity/number that appears nowhere
    in the evidence it cited. The reason is always recorded.
    """
    accepted: list[Claim] = []
    rejected: list[tuple[str, str]] = []

    for raw in raw_claims:
        if not isinstance(raw, dict):
            rejected.append((str(raw), "claim is not an object"))
            continue

        text = str(raw.get("text") or "").strip()
        if len(text) < MIN_CLAIM_LENGTH:
            rejected.append((text, f"claim is empty or shorter than {MIN_CLAIM_LENGTH} characters"))
            continue

        cited, reason = _cited_evidence(raw.get("evidence_ids"), index)
        if reason is not None:
            rejected.append((text, reason))
            continue

        # The anti-hallucination gate. `is_grounded` folds both sides to ASCII
        # first, so "İstanbul Teknik Üniversitesi" matches evidence spelling it
        # "Istanbul Teknik Universitesi" — Turkish diacritics are a spelling
        # difference, never a fabrication.
        if not is_grounded(text, _cited_text(cited)):
            rejected.append((text, "names an entity or number absent from the cited evidence"))
            continue

        mean_confidence = sum(item.confidence for item in cited) / len(cited)
        accepted.append(
            Claim(
                text=text,
                evidence_fingerprints=tuple(dict.fromkeys(item.fingerprint for item in cited)),
                source_urls=tuple(dict.fromkeys(item.source_url for item in cited if item.source_url)),
                confidence=round(100 * mean_confidence),
            )
        )

    return GroundingReport(accepted=tuple(accepted), rejected=tuple(rejected))


def grounded_on(text: str, evidence: Sequence[Evidence]) -> bool:
    """Whether ``text`` is supported by ``evidence``, using the same gate as above.

    Exposed for the deterministic fallback, which builds its own sentences and
    must be held to exactly the same standard as the model's.
    """
    return bool(fold_ascii(text).strip()) and is_grounded(text, _cited_text(evidence))
