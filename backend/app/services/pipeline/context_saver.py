"""Step 4 — persist context to JSON file and index into ChromaDB."""
from __future__ import annotations

import json
import os
import re

from app.utils.logger import logger

from .base import PipelineStep
from .context import PipelineContext


class ContextSaverStep(PipelineStep):
    @property
    def name(self) -> str:
        return "context_saver"

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        try:
            os.makedirs("data/contexts", exist_ok=True)
            safe_filename = re.sub(r'[^a-zA-Z0-9_\-]', '_', ctx.raw_query.lower())
            with open(f"data/contexts/{safe_filename}.json", "w", encoding="utf-8") as f:
                json.dump(ctx.context, f, ensure_ascii=False, indent=2)
            logger.log_action(
                "Context synchronized to local RAG knowledge base",
                target=safe_filename,
            )
        except Exception as e:
            logger.log_warning(f"Failed to synchronize RAG context: {e}")
        return ctx
