"""Search pipeline — step-based orchestration for the person-search flow."""
from .context import PipelineContext
from .base import PipelineStep

__all__ = ["PipelineContext", "PipelineStep"]
