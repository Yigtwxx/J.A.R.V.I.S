"""Step 9 — persist version snapshot and search history record."""
from __future__ import annotations

from typing import Any

from app.utils.logger import logger

from .base import PipelineStep
from .context import PipelineContext


class HistorySaverStep(PipelineStep):
    def __init__(self, version_history_service: Any) -> None:
        self._version = version_history_service

    @property
    def name(self) -> str:
        return "history_saver"

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        from app.models.history import SearchHistory

        response = ctx.response

        try:
            self._version.save_snapshot(ctx.db, ctx.raw_query, response)
            change_report = self._version.generate_change_report(ctx.db, ctx.raw_query)
            if change_report and change_report.has_changes:
                response.version_history = change_report.model_dump(mode='json')
                logger.log_success(
                    f"Version history: {len(change_report.changes)} change(s) detected"
                )
            elif change_report:
                response.version_history = change_report.model_dump(mode='json')
                logger.log_action("Version history: No changes detected since last scan")
            else:
                logger.log_action("Version history: First snapshot saved — no previous data to compare")
        except Exception as e:
            logger.log_warning(f"Version history snapshot failed (non-critical): {e}")

        try:
            history_entry = SearchHistory(query_name=ctx.raw_query)
            ctx.db.add(history_entry)
            ctx.db.flush()
        except Exception as e:
            logger.log_warning(f"Failed to record search history: {e}")

        return ctx
