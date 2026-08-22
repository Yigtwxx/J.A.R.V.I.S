"""The in-memory ``Evidence`` value object and its fingerprint.

Everything the pipeline learns becomes an ``Evidence``. The fingerprint is the
load-bearing part of this module: it decides what counts as a *new* fact, which
in turn decides both the confidence score and when the discovery loop stops.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.discovery.fetch.ratelimit import registrable_domain
from app.discovery.types import EvidenceKind, SourceKind

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids importing the ORM at runtime
    from app.models.discovery import EvidenceRecord

_WHITESPACE = re.compile(r"\s+")

# Punctuation that carries no meaning when it merely wraps a value: a bio that
# ends in a period and one that does not are the same claim.
_STRIP_CHARS = " \t\r\n\"'`.,;:!?()[]{}<>@/\\|-_*#"


def _normalize(text: str) -> str:
    """Fold a string down to its identity for fingerprinting purposes.

    Lowercase, collapse runs of internal whitespace to a single space, and strip
    surrounding punctuation. Deliberately conservative: it must never merge two
    genuinely different values, only two spellings of the same one.
    """
    collapsed = _WHITESPACE.sub(" ", text.strip())
    return collapsed.strip(_STRIP_CHARS).lower().strip()


@dataclass(frozen=True, slots=True)
class Evidence:
    """One observed fact, immutable once created.

    Frozen because evidence is an observation: re-weighting it later must produce
    a new object rather than rewrite history. Use :func:`with_confidence` for that.
    """

    kind: EvidenceKind
    subject: str
    """What the fact is about: ``"instagram:jdoe"``, ``"employer"``, ``"email"``."""

    value: str
    source_url: str
    source_kind: SourceKind
    extractor: str
    confidence: float
    """The extractor's own 0..1 belief. Corroboration across sources is applied
    later by the scorer; this field is one source's opinion, nothing more."""

    observed_at: datetime
    platform: str | None = None
    round_no: int = 0
    cluster_id: str | None = None
    raw: dict[str, Any] | None = None

    @property
    def source_domain(self) -> str:
        """Registrable domain of the source, e.g. ``www.instagram.com`` -> ``instagram.com``."""
        return registrable_domain(self.source_url)

    @property
    def fingerprint(self) -> str:
        """``sha256(kind|subject|value|source_domain)`` — the identity of this fact.

        Keyed on the source **domain**, deliberately NOT the full URL.

        The same fact re-scraped from a different path of the same site is not new
        information: ``instagram.com/jdoe`` and ``instagram.com/jdoe/tagged`` both
        assert the same thing on the same authority. Including the path would make
        every re-crawl look like a discovery.

        The same fact from a *different* site, however, IS new — that is
        corroboration, and independent corroboration is the only thing that
        genuinely moves the confidence score. A domain-keyed fingerprint keeps
        those two cases distinguishable.

        This definition also drives loop termination ("two consecutive rounds with
        no new fingerprint -> stop"). A looser key (full URL) would mint fresh
        fingerprints forever and the loop would never converge; a tighter key
        (dropping the source entirely) would collapse real corroboration into a
        single row and the score would never rise.
        """
        payload = f"{self.kind}|{_normalize(self.subject)}|{_normalize(self.value)}|{self.source_domain}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def with_confidence(self, confidence: float) -> Evidence:
        """Return a copy at a different confidence, clamped to 0..1."""
        return replace(self, confidence=max(0.0, min(1.0, confidence)))


def make_evidence(
    kind: EvidenceKind,
    subject: str,
    value: str,
    *,
    source_url: str,
    source_kind: SourceKind,
    extractor: str,
    confidence: float,
    platform: str | None = None,
    round_no: int = 0,
    raw: dict[str, Any] | None = None,
) -> Evidence:
    """Build an ``Evidence`` stamped with the current UTC time."""
    return Evidence(
        kind=kind,
        subject=subject.strip(),
        value=value.strip(),
        source_url=source_url,
        source_kind=source_kind,
        extractor=extractor,
        confidence=max(0.0, min(1.0, confidence)),
        observed_at=datetime.now(UTC),
        platform=platform,
        round_no=round_no,
        raw=raw,
    )


def from_record(record: EvidenceRecord) -> Evidence:
    """Rehydrate an ``Evidence`` from its persisted row."""
    return Evidence(
        kind=EvidenceKind(record.kind),
        subject=record.subject or "",
        value=record.value or "",
        source_url=record.source_url or "",
        source_kind=SourceKind(record.source_kind),
        extractor=record.extractor or "",
        confidence=float(record.confidence if record.confidence is not None else 0.5),
        observed_at=record.observed_at or datetime.now(UTC),
        platform=record.platform,
        round_no=int(record.round_no or 0),
        cluster_id=record.cluster_id,
        raw=record.raw,
    )


def to_record_kwargs(ev: Evidence, *, target_key: str, session_id: str | None) -> dict[str, Any]:
    """Flatten an ``Evidence`` into ``EvidenceRecord(**kwargs)``.

    ``source_domain`` and ``fingerprint`` are materialised here rather than
    recomputed on read, so the DB can enforce uniqueness and index the domain.
    """
    return {
        "target_key": target_key,
        "session_id": session_id,
        "round_no": ev.round_no,
        "kind": str(ev.kind),
        "subject": ev.subject,
        "value": ev.value,
        "platform": ev.platform,
        "source_url": ev.source_url,
        "source_domain": ev.source_domain,
        "source_kind": str(ev.source_kind),
        "extractor": ev.extractor,
        "confidence": ev.confidence,
        "observed_at": ev.observed_at,
        "fingerprint": ev.fingerprint,
        "cluster_id": ev.cluster_id,
        "raw": ev.raw,
    }
