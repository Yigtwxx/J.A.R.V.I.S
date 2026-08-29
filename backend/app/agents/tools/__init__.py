"""Shared helpers for the agent's tool modules."""

from __future__ import annotations

import json
from typing import Any

DEFAULT_RESULT_LIMIT = 4000
"""A tool result is fed straight back into the model's context, so an unbounded
one costs the rest of the conversation."""


def truncate_result(text: str, limit: int = DEFAULT_RESULT_LIMIT) -> str:
    if len(text) > limit:
        return text[:limit] + "\n... [TRUNCATED]"
    return text


def as_json(payload: Any, limit: int = DEFAULT_RESULT_LIMIT) -> str:
    """Render a tool result as the indented JSON the tool modules all return."""
    return truncate_result(json.dumps(payload, ensure_ascii=False, indent=1, default=str), limit)


__all__ = ["DEFAULT_RESULT_LIMIT", "as_json", "truncate_result"]
