"""Durable storage for everything the discovery loop observes.

``EvidenceStore`` is the loop's memory. This module holds the evidence half —
what the pipeline *learned*; the session/question/outcome half (what it *did*)
lives in ``journal.py``, along with the shared threading and error-swallowing
plumbing in ``StoreBase``.

Every call runs on a worker thread and never raises: see ``StoreBase._run``.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import replace

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.discovery.evidence.journal import JournalMixin
from app.discovery.evidence.model import Evidence, from_record, to_record_kwargs
from app.discovery.types import EvidenceKind
from app.models.discovery import EvidenceRecord, SearchSession

# How much a prior session's evidence is trusted when its anchor disagrees with
# the current one. See `load_prior` for why this is a mitigation, not a fix.
_ANCHOR_CONFLICT_PENALTY = 0.5


class EvidenceStore(JournalMixin):
    """Async-friendly facade over the four discovery tables."""

    async def add(self, target_key: str, session_id: str | None, ev: Evidence) -> bool:
        """Persist one item. Returns False if the fingerprint was already known.

        Deduplication is delegated to the unique index rather than a prior SELECT,
        because rounds insert concurrently and a check-then-write race would let
        duplicates slip through.
        """

        def _op(session: Session) -> bool:
            record = EvidenceRecord(**to_record_kwargs(ev, target_key=target_key, session_id=session_id))
            try:
                with session.begin_nested():
                    session.add(record)
            except IntegrityError:
                return False
            return True

        return await self._call(_op, False, "add")

    async def add_many(self, target_key: str, session_id: str | None, evs: Iterable[Evidence]) -> list[Evidence]:
        """Persist a batch, returning only the items that were genuinely NEW.

        A duplicate is rolled back to its savepoint so it cannot abort the rest of
        the batch. The returned list is what the loop's "did this round learn
        anything?" termination check runs on.
        """
        items = list(evs)

        def _op(session: Session) -> list[Evidence]:
            fresh: list[Evidence] = []
            for ev in items:
                record = EvidenceRecord(**to_record_kwargs(ev, target_key=target_key, session_id=session_id))
                try:
                    with session.begin_nested():
                        session.add(record)
                except IntegrityError:
                    continue
                fresh.append(ev)
            return fresh

        return await self._call(_op, [], "add_many")

    async def load(
        self,
        target_key: str,
        *,
        kinds: Collection[EvidenceKind] | None = None,
        include_superseded: bool = False,
    ) -> list[Evidence]:
        def _op(session: Session) -> list[Evidence]:
            stmt = select(EvidenceRecord).where(EvidenceRecord.target_key == target_key)
            if kinds:
                stmt = stmt.where(EvidenceRecord.kind.in_([str(k) for k in kinds]))
            if not include_superseded:
                stmt = stmt.where(EvidenceRecord.superseded_by.is_(None))
            return [from_record(r) for r in session.execute(stmt).scalars().all()]

        return await self._call(_op, [], "load")

    async def load_prior(
        self,
        target_key: str,
        *,
        exclude_session: str,
        current_anchor: str | None,
    ) -> list[Evidence]:
        """Evidence about this target from *earlier* sessions.

        Two different people share a ``target_key`` whenever they share a name, so
        prior evidence is genuinely useful and genuinely dangerous. When the older
        session settled on a different anchor handle than the current one, its
        evidence is probably about someone else, and its confidence is multiplied
        by 0.5 and tagged in ``raw``.

        Be clear about what that is: a **mitigation, not a fix**. Halving a wrong
        fact does not make it right, it only makes it quieter. It buys the scorer
        room to outvote stale evidence with fresh corroboration; it cannot detect
        the collision on its own. Real separation happens in clustering.
        """
        anchor = (current_anchor or "").strip().lower()

        def _op(session: Session) -> list[Evidence]:
            stmt = (
                select(EvidenceRecord, SearchSession.anchor_handle)
                .outerjoin(SearchSession, EvidenceRecord.session_id == SearchSession.id)
                .where(
                    EvidenceRecord.target_key == target_key,
                    EvidenceRecord.superseded_by.is_(None),
                )
            )
            if exclude_session:
                stmt = stmt.where(
                    (EvidenceRecord.session_id.is_(None)) | (EvidenceRecord.session_id != exclude_session)
                )

            out: list[Evidence] = []
            for record, prior_anchor in session.execute(stmt).all():
                ev = from_record(record)
                prior = (prior_anchor or "").strip().lower()
                if anchor and prior and prior != anchor:
                    raw = dict(ev.raw or {})
                    raw["prior_anchor_conflict"] = {
                        "prior_anchor": prior_anchor,
                        "current_anchor": current_anchor,
                        "penalty": _ANCHOR_CONFLICT_PENALTY,
                        "note": "same target_key, different anchor - possible name collision",
                    }
                    ev = replace(ev, confidence=ev.confidence * _ANCHOR_CONFLICT_PENALTY, raw=raw)
                out.append(ev)
            return out

        return await self._call(_op, [], "load_prior")

    async def known_fingerprints(self, target_key: str) -> set[str]:
        def _op(session: Session) -> set[str]:
            stmt = select(EvidenceRecord.fingerprint).where(EvidenceRecord.target_key == target_key)
            return set(session.execute(stmt).scalars().all())

        return await self._call(_op, set(), "known_fingerprints")

    async def supersede(self, fingerprints: Collection[str], *, by_id: int | None = None) -> int:
        """Retire rows without deleting them.

        With no replacement ``by_id`` the row points at itself: a self-reference is
        FK-valid and still satisfies the ``superseded_by IS NOT NULL`` test that
        ``load`` filters on. Rows are never deleted — a retracted claim is still a
        fact about what that source said.
        """
        keys = list(fingerprints)
        if not keys:
            return 0

        def _op(session: Session) -> int:
            stmt = select(EvidenceRecord).where(EvidenceRecord.fingerprint.in_(keys))
            rows = session.execute(stmt).scalars().all()
            for row in rows:
                row.superseded_by = by_id if by_id is not None else row.id
            return len(rows)

        return await self._call(_op, 0, "supersede")

    async def set_cluster(self, fingerprints: Collection[str], cluster_id: str) -> int:
        keys = list(fingerprints)
        if not keys:
            return 0

        def _op(session: Session) -> int:
            result = session.execute(
                update(EvidenceRecord).where(EvidenceRecord.fingerprint.in_(keys)).values(cluster_id=cluster_id)
            )
            return int(result.rowcount or 0)

        return await self._call(_op, 0, "set_cluster")
