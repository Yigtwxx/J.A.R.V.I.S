"""Step 1 — parse raw query into real_name and username."""
from __future__ import annotations

from .base import PipelineStep
from .context import PipelineContext


class QueryParserStep(PipelineStep):
    @property
    def name(self) -> str:
        return "query_parser"

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        raw_query = ctx.raw_query
        if "/" in raw_query:
            parts = [p.strip() for p in raw_query.split("/")]
            ctx.real_name = parts[0]
            ctx.username = parts[1] if len(parts) > 1 else parts[0]
        else:
            ctx.real_name = raw_query
            ctx.username = raw_query
        return ctx
