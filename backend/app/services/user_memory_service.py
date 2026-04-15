"""
UserMemoryService — Agentic Memory layer that remembers the user.

Stores user preferences, behavioral patterns, past conversation context,
and personal information. Uses SQLite for structured storage and keyword-based
search to enable J.A.R.V.I.S to adapt and personalize responses over time.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.user_memory import UserMemory
from app.utils.logger import logger


class UserMemoryService:
    """Manages persistent user memory across sessions."""

    # -- CRUD Operations (SQLite) ------------------------------------------

    def remember(
        self,
        db: Session,
        category: str,
        key: str,
        value: str,
        context: str | None = None,
        importance: int = 5,
    ) -> UserMemory:
        """Store or update a memory. If key exists in category, update it."""
        existing = (
            db.query(UserMemory)
            .filter(UserMemory.category == category, UserMemory.key == key)
            .first()
        )
        if existing:
            existing.value = value
            existing.context = context or existing.context
            existing.importance = importance
            existing.updated_at = datetime.now(UTC)
            db.flush()
            db.refresh(existing)
            logger.log_action(f"Memory updated: [{category}] {key}")
            return existing

        memory = UserMemory(
            category=category,
            key=key,
            value=value,
            context=context,
            importance=importance,
        )
        db.add(memory)
        db.flush()
        db.refresh(memory)
        logger.log_success(f"Memory stored: [{category}] {key}")
        return memory

    def recall(self, db: Session, category: str | None = None, key: str | None = None) -> list[dict[str, Any]]:
        """Retrieve memories, optionally filtered by category and/or key."""
        query = db.query(UserMemory)
        if category:
            query = query.filter(UserMemory.category == category)
        if key:
            query = query.filter(UserMemory.key.ilike(f"%{key}%"))
        memories = query.order_by(UserMemory.importance.desc(), UserMemory.updated_at.desc()).all()
        return [_memory_to_dict(m) for m in memories]

    def forget(self, db: Session, memory_id: int) -> bool:
        """Delete a specific memory by ID."""
        memory = db.query(UserMemory).filter(UserMemory.id == memory_id).first()
        if not memory:
            return False
        db.delete(memory)
        logger.log_action(f"Memory erased: [{memory.category}] {memory.key}")
        return True

    def forget_category(self, db: Session, category: str) -> int:
        """Delete all memories in a category. Returns count deleted."""
        count = db.query(UserMemory).filter(UserMemory.category == category).delete()
        logger.log_action(f"Category purged: {category} ({count} memories)")
        return count

    # -- Keyword Search (SQLite) -------------------------------------------

    def semantic_recall(self, db: Session, query: str, n_results: int = 5) -> str:
        """Search user memories using keyword matching (SQLite LIKE)."""
        memories = (
            db.query(UserMemory)
            .filter(
                UserMemory.value.ilike(f"%{query}%")
                | UserMemory.key.ilike(f"%{query}%")
                | UserMemory.context.ilike(f"%{query}%")
            )
            .order_by(UserMemory.importance.desc())
            .limit(n_results)
            .all()
        )
        if not memories:
            return ""
        parts = [f"[{m.category}] {m.key}: {m.value}" for m in memories]
        return "\n".join(parts)

    # -- Context Builder (for AI prompts) ----------------------------------

    def build_user_context(self, db: Session) -> str:
        """Build a context string from all user memories for AI prompt injection."""
        memories = db.query(UserMemory).order_by(
            UserMemory.importance.desc(), UserMemory.updated_at.desc()
        ).limit(50).all()

        if not memories:
            return ""

        sections: dict[str, list[str]] = {}
        for m in memories:
            sections.setdefault(m.category, []).append(f"- {m.key}: {m.value}")

        parts = []
        for cat, items in sections.items():
            parts.append(f"[{cat.upper()}]")
            parts.extend(items)
            parts.append("")

        return "\n".join(parts)

    # -- Auto-Learn from Conversation --------------------------------------

    def learn_from_interaction(self, db: Session, user_message: str, ai_response: str) -> None:
        """Analyze a conversation turn and extract memorable information."""
        lower = user_message.lower()

        # Detect name introduction
        for pattern in ["benim adım ", "ben ", "my name is ", "i'm ", "i am "]:
            if pattern in lower:
                name = user_message.split(pattern.strip())[-1].strip().split()[0].strip(".,!?")
                if len(name) > 1:
                    self.remember(db, "identity", "user_name", name,
                                  context=f"User introduced themselves: '{user_message}'", importance=9)
                break

        # Detect profession/role
        for pattern in ["i work as ", "i'm a ", "ben bir ", "mesleğim "]:
            if pattern in lower:
                role = user_message.split(pattern.strip())[-1].strip().split(".")[0].strip()
                if len(role) > 2:
                    self.remember(db, "identity", "profession", role,
                                  context=f"User mentioned role: '{user_message}'", importance=8)
                break

        # Track interaction patterns
        self.remember(
            db, "interaction", "last_interaction",
            datetime.now(UTC).isoformat(),
            context="Last conversation timestamp",
            importance=3,
        )

        # Count interactions
        existing = (
            db.query(UserMemory)
            .filter(UserMemory.category == "interaction", UserMemory.key == "total_interactions")
            .first()
        )
        count = int(existing.value) + 1 if existing else 1
        self.remember(db, "interaction", "total_interactions", str(count), importance=3)


def _memory_to_dict(m: UserMemory) -> dict[str, Any]:
    return {
        "id": m.id,
        "category": m.category,
        "key": m.key,
        "value": m.value,
        "context": m.context,
        "importance": m.importance,
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "updated_at": m.updated_at.isoformat() if m.updated_at else None,
    }
