"""Runs browse tasks for one search: budgets, frames, events, and the hard stop.

Sits between the round (which knows *which* handles are worth a browser) and the
agent (which knows how to work one page). Keeping it separate is what lets the
round's target-selection be tested without a policy and the agent's loop be
tested without a round.

The whole task is wrapped in ``asyncio.wait_for``. The agent already enforces
its own step and time budgets, but that check happens between steps: a single
``page.click`` that never returns would sail past it. Two independent ceilings,
because the expensive failure here is silent.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.discovery.browse.agent import BrowseAgent, BrowseBudget
from app.discovery.browse.page import BrowsePage
from app.discovery.browse.policy import BrowsePolicy, VisionPolicy
from app.discovery.browse.types import BrowseOutcome, BrowseReport, BrowseTask
from app.discovery.media.shots import FrameStore
from app.utils.logger import logger


@dataclass(frozen=True, slots=True)
class BrowseSettings:
    """The knobs the round needs to consult before it commits to a browse."""

    enabled: bool = True
    max_tasks_per_search: int = 2
    max_steps: int = 12
    max_seconds: float = 180.0
    min_time_left_seconds: float = 300.0
    allow_pixel_clicks: bool = True
    viewport: tuple[int, int] = (1280, 800)


EmitFn = Callable[[str, dict], Awaitable[None]]


class BrowseRunner:
    """Owns everything one search needs to browse, and nothing it does not."""

    def __init__(
        self,
        *,
        open_page: Callable[[], Awaitable[BrowsePage]],
        policy: BrowsePolicy,
        frames: FrameStore,
        settings: BrowseSettings | None = None,
    ) -> None:
        self._open_page = open_page
        self._policy = policy
        self._frames = frames
        self.settings = settings or BrowseSettings()

    async def run(
        self,
        task: BrowseTask,
        *,
        session_id: str,
        emit: EmitFn | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> BrowseReport:
        """Work one target. Returns a report whatever happens; never raises."""
        budget = BrowseBudget(
            max_steps=self.settings.max_steps,
            max_seconds=self.settings.max_seconds,
            allow_pixel_clicks=self.settings.allow_pixel_clicks,
            viewport=self.settings.viewport,
        )

        async def save_frame(step: int, data: bytes) -> str:
            # Synchronous Pillow work, pushed off the loop: a 1280x800 JPEG
            # resize is milliseconds, but it happens on every step of every task
            # and this loop is also serving the SSE stream the user is watching.
            return await asyncio.to_thread(self._frames.save, session_id, step, data)

        async def emit_step(event_type: str, payload: dict) -> None:
            if emit is not None:
                await emit(event_type, {"task_id": task.task_id, **payload})

        agent = BrowseAgent(
            policy=self._policy,
            open_page=self._open_page,
            budget=budget,
            emit=emit_step,
            save_frame=save_frame,
            should_stop=should_stop,
            shrink=self._frames.shrink,
        )

        try:
            # The outer ceiling. Generous against the agent's own budget so it
            # only ever fires for a page operation that hung, never for a task
            # that was simply working.
            return await asyncio.wait_for(agent.run(task), timeout=self.settings.max_seconds + 60.0)
        except TimeoutError:
            logger.log_warning(
                f"Browse task {task.task_id} hung and was cut off",
                broadcast=False,
            )
            return BrowseReport(
                task=task,
                outcome=BrowseOutcome.TIME_BUDGET,
                detail="the page stopped responding",
            )
        except Exception as exc:  # pragma: no cover - defence in depth
            logger.log_warning(f"Browse task {task.task_id} failed: {exc}", broadcast=False)
            return BrowseReport(task=task, outcome=BrowseOutcome.ERROR, detail=str(exc))

    def purge(self, session_id: str) -> None:
        """Drop this session's frames. Called from the search's teardown."""
        self._frames.purge(session_id)


def build_browse_runner(fetch, settings, frames: FrameStore) -> BrowseRunner | None:
    """Assemble the browse tier from settings, or ``None`` when it is off.

    Returning ``None`` rather than a disabled object keeps the phase genuinely
    inert: the round checks for it once and never constructs a policy, a budget
    or a frame path. ``discovery_archive_recovery_enabled`` was once a flag no
    code read; a switch that does not switch anything is worse than no switch.
    """
    if not settings.discovery_browse_enabled:
        return None

    policy = VisionPolicy(
        model=settings.discovery_browse_model or settings.vision_model,
        timeout_s=settings.discovery_browse_step_timeout_seconds,
        keep_alive=settings.discovery_browse_keep_alive,
    )
    return BrowseRunner(
        open_page=lambda: fetch.open_agent_page(
            viewport=(
                settings.discovery_browse_viewport_width,
                settings.discovery_browse_viewport_height,
            )
        ),
        policy=policy,
        frames=frames,
        settings=BrowseSettings(
            enabled=True,
            max_tasks_per_search=settings.discovery_browse_max_tasks_per_search,
            max_steps=settings.discovery_browse_max_steps,
            max_seconds=settings.discovery_browse_max_seconds,
            min_time_left_seconds=settings.discovery_browse_min_time_left_seconds,
            allow_pixel_clicks=settings.discovery_browse_allow_pixel_clicks,
            viewport=(
                settings.discovery_browse_viewport_width,
                settings.discovery_browse_viewport_height,
            ),
        ),
    )


__all__ = ["BrowseRunner", "BrowseSettings", "build_browse_runner"]
