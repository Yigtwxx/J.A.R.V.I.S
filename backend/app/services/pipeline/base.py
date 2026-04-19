"""Abstract base class for all pipeline steps."""
from __future__ import annotations

from abc import ABC, abstractmethod

from .context import PipelineContext


class PipelineStep(ABC):
    """Every step reads from and writes back to a PipelineContext."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable step identifier (used in logs)."""

    @abstractmethod
    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        """Execute this step and return the (mutated) context."""
