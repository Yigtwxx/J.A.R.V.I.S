"""Search pipeline — step-based orchestration for the person-search flow."""

from .base import PipelineStep
from .context import PipelineContext

__all__ = ["PipelineContext", "PipelineStep"]
