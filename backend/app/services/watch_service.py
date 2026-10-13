"""
WatchService — Continuous surveillance and change detection for targets.

Enables background monitoring of targets with periodic re-scanning
and diff-based change alerts. Runs as async background tasks.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from app.discovery.dependencies import get_discovery_runner
from app.services.discovery_integration import profile_snapshot, status_index, watch_alerts
from app.utils.logger import logger

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids a heavy import at module load
    from app.discovery.loop.runner import DiscoveryResult, DiscoveryRunner


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
        self.last_profile_snapshot: dict[str, Any] = {}
        """Previous `profile_snapshot(result.profiles)` from the discovery pipeline."""
        self.last_diff: dict[str, dict[str, Any]] | None = None
        """Most recent alert batch, in the `{key: {old, new}}` shape the panel renders."""
        self.changes_detected: int = 0
        self.is_active: bool = True
        self.created_at: datetime = datetime.now(UTC)
        self._task: asyncio.Task | None = None

    def as_status(self) -> dict[str, Any]:
        """Status payload for the API.

        The key is `last_checked`, not `last_check`: that is the name the frontend
        schema and WatchPanel read, and the mismatch is why the panel never
        rendered a last-scan time.
        """
        return {
            "query": self.query,
            "interval_minutes": self.interval_minutes,
            "last_checked": self.last_check.isoformat() if self.last_check else None,
            "last_diff": self.last_diff,
            "changes_detected": self.changes_detected,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
        }


class WatchService:
    """Manages background monitoring of targets."""

    def __init__(self):
        self._targets: dict[str, WatchTarget] = {}

    @property
    def active_watches(self) -> list[dict[str, Any]]:
        """Return status of all active watches."""
        return [t.as_status() for t in self._targets.values()]

    def stop_watch(self, query: str) -> dict[str, Any]:
        """Stop monitoring a target and drop it from the list."""
        target = self._targets.pop(query, None)
        if not target:
            return {"status": "not_found", "query": query}

        self._cancel(target)
        logger.log_action(f"Watch mode deactivated for target: {query}")
        return {
            "status": "stopped",
            "query": query,
            "total_changes": target.changes_detected,
        }

    def stop_all(self) -> int:
        """Stop all active watches. Returns count stopped."""
        targets, self._targets = self._targets, {}
        for target in targets.values():
            self._cancel(target)
        logger.log_action(f"All watches terminated: {len(targets)} target(s)")
        return len(targets)

    def get_watch_status(self, query: str) -> dict[str, Any] | None:
        """Get status of a specific watch."""
        target = self._targets.get(query)
        return target.as_status() if target else None

    @staticmethod
    def _cancel(target: WatchTarget) -> None:
        target.is_active = False
        if target._task:
            target._task.cancel()

    # -- Discovery pipeline re-scan ----------------------------------------

    @staticmethod
    async def rescan(
        query: str,
        runner: DiscoveryRunner | None = None,
        *,
        depth: int = 5,
    ) -> DiscoveryResult:
        """Re-run a watched target through the discovery pipeline.

        `interactive=False` is not optional here. A watch fires on a timer with
        nobody at the screen, so a mid-search disambiguation question would block
        the round until it timed out and the re-scan would be wasted.
        """
        active = runner or get_discovery_runner()
        return await active.run(
            session_id=f"watch-{uuid4().hex[:12]}",
            raw_query=query,
            depth=depth,
            interactive=False,
        )

    @staticmethod
    def compute_profile_diff(
        old_snapshot: dict[str, Any],
        new_snapshot: dict[str, Any],
        profiles: Sequence[Any] = (),
    ) -> list[dict[str, Any]]:
        """Alerts between two discovery snapshots.

        Fires on: a new account, a removed account, a changed avatar (compared on
        `avatar_sha256`, never on the URL) or a changed bio.

        A platform going `found` -> `blocked` is deliberately NOT an alert. The
        account did not disappear; we were refused. Because a blocked candidate is
        no longer live it drops out of the snapshot entirely, so without this rule
        a refusal is indistinguishable from a deletion and a false "account
        removed" alarm fires every single time a site rate-limits or captchas us.
        """
        return watch_alerts(old_snapshot, new_snapshot, statuses=status_index(profiles))

    def start_discovery_watch(
        self,
        query: str,
        interval_minutes: int = 60,
        runner: DiscoveryRunner | None = None,
        notify_fn: Callable[[str, dict], Any] | None = None,
    ) -> dict[str, Any]:
        """Watch a target by re-running it through the discovery pipeline."""
        if query in self._targets and self._targets[query].is_active:
            return {"status": "already_watching", "query": query}

        target = WatchTarget(query, interval_minutes, notify_fn)
        self._targets[query] = target
        target._task = asyncio.create_task(self._discovery_loop(target, runner))

        logger.log_success(f"Discovery watch activated for target: {query} (every {interval_minutes}min)")
        return {
            "status": "watching",
            "query": query,
            "interval_minutes": interval_minutes,
            "engine": "discovery",
        }

    async def _discovery_loop(self, target: WatchTarget, runner: DiscoveryRunner | None) -> None:
        """Scan, then sleep — never the other way round.

        The baseline scan has to happen the moment the watch starts. Sleeping
        first meant a fresh watch showed no last-scan time and no changes until a
        full interval had elapsed, and could not raise its first alert until two
        had — an hour of looking broken on the default interval.
        """
        while target.is_active:
            try:
                await self._run_once(target, runner)
                await asyncio.sleep(target.interval_minutes * 60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.log_error(f"Discovery watch loop error for '{target.query}': {e}")
                await asyncio.sleep(60)  # Wait before retry

    async def _run_once(self, target: WatchTarget, runner: DiscoveryRunner | None) -> list[dict[str, Any]]:
        """One re-scan, diffed against the previous one. Returns the alerts raised.

        The first call only establishes the baseline, so it always returns none —
        there is nothing to compare a first scan against.
        """
        logger.log_action(f"Discovery watch: re-scanning target '{target.query}'")
        try:
            result = await self.rescan(target.query, runner)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            # Leave `last_profile_snapshot` untouched: replacing the baseline with
            # nothing would make the next successful scan report every account as new.
            logger.log_warning(f"Discovery watch scan failed for '{target.query}': {e}")
            return []

        target.last_check = datetime.now(UTC)
        snapshot = profile_snapshot(result.profiles)
        alerts: list[dict[str, Any]] = []

        if target.last_profile_snapshot:
            alerts = self.compute_profile_diff(target.last_profile_snapshot, snapshot, result.profiles)
            if alerts:
                target.changes_detected += len(alerts)
                target.last_diff = {
                    f"{a['platform']}:{a['username']}": {"old": a.get("before"), "new": a.get("after")} for a in alerts
                }
                logger.log_warning(f"WATCH ALERT for '{target.query}': {len(alerts)} change(s) detected!")
                await self._notify(target, alerts)
            else:
                logger.log_action(f"Discovery watch complete for '{target.query}': No changes")

        target.last_profile_snapshot = snapshot
        return alerts

    async def _notify(self, target: WatchTarget, alerts: list[dict[str, Any]]) -> None:
        """Fan an alert batch out to the callback and the SSE stream."""
        if target.callback:
            try:
                await target.callback(
                    target.query,
                    {"changes": alerts, "timestamp": datetime.now(UTC).isoformat()},
                )
            except Exception as e:
                logger.log_warning(f"Watch notification failed: {e}")

        # `broadcast` is synchronous — awaiting it raises TypeError — and it strips
        # bracketed segments as Rich markup, so the tag and query must go unbracketed
        # or they never reach the stream.
        for alert in alerts:
            logger.broadcast(f"WATCH {target.query}: {alert['platform']} {alert['change']}")


# Module-level singleton
watch_service = WatchService()
