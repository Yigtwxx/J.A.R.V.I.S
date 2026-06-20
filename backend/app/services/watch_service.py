"""
WatchService — Continuous surveillance and change detection for targets.

Enables background monitoring of targets with periodic re-scanning
and diff-based change alerts. Runs as async background tasks.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any, Callable

from app.services.version_history_service import TRACKED_INTEL_SIGS, _intel_signatures
from app.utils.logger import logger


class WatchTarget:
    """Represents a target being monitored."""

    def __init__(
        self,
        query: str,
        interval_minutes: int = 60,
        callback: Callable[[str, dict], Any] | None = None,
    ):
        self.query = query
        self.interval_minutes = interval_minutes
        self.callback = callback
        self.last_check: datetime | None = None
        self.last_snapshot: dict[str, Any] = {}
        self.changes_detected: int = 0
        self.is_active: bool = True
        self.created_at: datetime = datetime.now(UTC)
        self._task: asyncio.Task | None = None


class WatchService:
    """Manages background monitoring of targets."""

    def __init__(self):
        self._targets: dict[str, WatchTarget] = {}

    @property
    def active_watches(self) -> list[dict[str, Any]]:
        """Return status of all active watches."""
        return [
            {
                "query": t.query,
                "interval_minutes": t.interval_minutes,
                "last_check": t.last_check.isoformat() if t.last_check else None,
                "changes_detected": t.changes_detected,
                "is_active": t.is_active,
                "created_at": t.created_at.isoformat(),
            }
            for t in self._targets.values()
        ]

    def start_watch(
        self,
        query: str,
        interval_minutes: int = 60,
        search_fn: Callable | None = None,
        notify_fn: Callable[[str, dict], Any] | None = None,
    ) -> dict[str, Any]:
        """
        Start monitoring a target. Returns watch status.
        search_fn: async function that performs a search and returns result dict
        notify_fn: async function called when changes are detected
        """
        if query in self._targets and self._targets[query].is_active:
            return {"status": "already_watching", "query": query}

        target = WatchTarget(query, interval_minutes, notify_fn)
        self._targets[query] = target

        # Start background monitoring task
        target._task = asyncio.create_task(
            self._monitor_loop(target, search_fn)
        )

        logger.log_success(f"Watch mode activated for target: {query} (every {interval_minutes}min)")
        return {
            "status": "watching",
            "query": query,
            "interval_minutes": interval_minutes,
        }

    def stop_watch(self, query: str) -> dict[str, Any]:
        """Stop monitoring a target."""
        target = self._targets.get(query)
        if not target:
            return {"status": "not_found", "query": query}

        target.is_active = False
        if target._task:
            target._task.cancel()

        logger.log_action(f"Watch mode deactivated for target: {query}")
        return {
            "status": "stopped",
            "query": query,
            "total_changes": target.changes_detected,
        }

    def stop_all(self) -> int:
        """Stop all active watches. Returns count stopped."""
        count = 0
        for target in self._targets.values():
            if target.is_active:
                target.is_active = False
                if target._task:
                    target._task.cancel()
                count += 1
        logger.log_action(f"All watches terminated: {count} target(s)")
        return count

    def get_watch_status(self, query: str) -> dict[str, Any] | None:
        """Get status of a specific watch."""
        target = self._targets.get(query)
        if not target:
            return None
        return {
            "query": target.query,
            "interval_minutes": target.interval_minutes,
            "last_check": target.last_check.isoformat() if target.last_check else None,
            "changes_detected": target.changes_detected,
            "is_active": target.is_active,
            "created_at": target.created_at.isoformat(),
        }

    # -- Change Detection --------------------------------------------------

    @staticmethod
    def compute_diff(old: dict, new: dict) -> list[dict[str, Any]]:
        """Compare two profile snapshots and return list of changes."""
        changes = []
        # Fields to track for changes
        tracked_fields = [
            "description", "location_country", "location_city",
            "social_media_score", "email_addresses", "phone_numbers",
            "network_connections", "data_breaches", "company_records",
            "github_url", "instagram_url", "twitter_url", "linkedin_url",
        ]

        for field in tracked_fields:
            old_val = old.get(field)
            new_val = new.get(field)
            if old_val != new_val:
                changes.append({
                    "field": field,
                    "old_value": str(old_val)[:200] if old_val else None,
                    "new_value": str(new_val)[:200] if new_val else None,
                    "detected_at": datetime.now(UTC).isoformat(),
                })

        # New intel fields — compare timestamp-free signatures so re-scans only
        # alert on meaningful changes (new domain/sanction/relationship), not the
        # `retrieved_at` that changes every scan (Faz 3.3).
        old_sigs = _intel_signatures(lambda k: old.get(k))
        new_sigs = _intel_signatures(lambda k: new.get(k))
        for key, label in TRACKED_INTEL_SIGS.items():
            if old_sigs.get(key) != new_sigs.get(key):
                changes.append({
                    "field": key,
                    "old_value": str(old_sigs.get(key))[:200] if old_sigs.get(key) else None,
                    "new_value": str(new_sigs.get(key))[:200] if new_sigs.get(key) else None,
                    "detected_at": datetime.now(UTC).isoformat(),
                })

        return changes

    # -- Private -----------------------------------------------------------

    async def _monitor_loop(
        self, target: WatchTarget, search_fn: Callable | None
    ) -> None:
        """Background monitoring loop for a single target."""
        while target.is_active:
            try:
                await asyncio.sleep(target.interval_minutes * 60)

                if not target.is_active:
                    break

                if not search_fn:
                    continue

                logger.log_action(f"Watch mode: Re-scanning target '{target.query}'")

                # Run the search
                try:
                    new_result = await search_fn(target.query)
                    new_snapshot = new_result if isinstance(new_result, dict) else {}
                except Exception as e:
                    logger.log_warning(f"Watch scan failed for '{target.query}': {e}")
                    continue

                target.last_check = datetime.now(UTC)

                # Compare with previous snapshot
                if target.last_snapshot:
                    changes = self.compute_diff(target.last_snapshot, new_snapshot)
                    if changes:
                        target.changes_detected += len(changes)
                        logger.log_warning(
                            f"WATCH ALERT [{target.query}]: {len(changes)} change(s) detected!"
                        )

                        # Notify via callback
                        if target.callback:
                            try:
                                await target.callback(target.query, {
                                    "changes": changes,
                                    "timestamp": datetime.now(UTC).isoformat(),
                                })
                            except Exception as e:
                                logger.log_warning(f"Watch notification failed: {e}")

                        # Broadcast to SSE subscribers
                        for change in changes:
                            await logger.broadcast(
                                f"[WATCH] {target.query}: {change['field']} changed"
                            )
                    else:
                        logger.log_action(f"Watch scan complete for '{target.query}': No changes")

                target.last_snapshot = new_snapshot

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.log_error(f"Watch loop error for '{target.query}': {e}")
                await asyncio.sleep(60)  # Wait before retry


# Module-level singleton
watch_service = WatchService()
