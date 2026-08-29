"""The observe → decide → act loop.

Every collaborator is injected — the page, the policy, the frame sink, the stop
signal, the event emitter — so the whole loop is exercised in tests without a
browser, a model, or a network. That is not test convenience for its own sake:
this is the one component that can spend minutes and megabytes on a wrong idea,
so its stopping conditions have to be provable, and they cannot be proved
against a live browser.

Four things end a task besides the model saying so, and each exists because the
alternative is a run that looks busy and is not:

* a **structural** wall — the URL is on a login path, or the DOM carries a
  challenge marker. Detected with the pipeline's own ``detect_block_signal``,
  never by asking the model whether it feels blocked.
* **repetition** — three identical actions in a row. A loop that cannot notice
  itself will happily spend the whole budget scrolling the same 700 px.
* **refusals** — three in a row means the agent has decided the way through is
  the sign-in button, and it is not going to change its mind.
* the **budgets**, checked before every step and enforced again by the caller's
  ``asyncio.wait_for``.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.discovery.browse import rules
from app.discovery.browse.guard import check as guard_check
from app.discovery.browse.observe import describe_action, number_elements
from app.discovery.browse.page import BrowsePage
from app.discovery.browse.policy import BrowsePolicy
from app.discovery.browse.prompts import task_sentence
from app.discovery.browse.types import (
    ActionKind,
    BrowseAction,
    BrowseOutcome,
    BrowseReport,
    BrowseStep,
    BrowseTask,
    Element,
    Observation,
)
from app.discovery.fetch.result import detect_block_signal
from app.utils.logger import logger

REPEAT_LIMIT = 3
REFUSAL_LIMIT = 3
UNUSABLE_REPLY_LIMIT = 3

_NOT_FOUND_STATUSES: frozenset[int] = frozenset({404, 410})


@dataclass(slots=True)
class BrowseBudget:
    """Every limit the loop can hit, each with a name the report can carry."""

    max_steps: int = 12
    max_seconds: float = 180.0
    allow_pixel_clicks: bool = True
    viewport: tuple[int, int] = (1280, 800)


EmitFn = Callable[[str, dict[str, Any]], Awaitable[None]]
FrameSink = Callable[[int, bytes], Awaitable[str]]


class BrowseAgent:
    """Drives one page towards one narrow goal, under a hard budget."""

    def __init__(
        self,
        *,
        policy: BrowsePolicy,
        open_page: Callable[[], Awaitable[BrowsePage]],
        budget: BrowseBudget | None = None,
        emit: EmitFn | None = None,
        save_frame: FrameSink | None = None,
        should_stop: Callable[[], bool] | None = None,
        shrink: Callable[[bytes], bytes] | None = None,
        use_rules: bool = True,
    ) -> None:
        self._policy = policy
        self._open_page = open_page
        self._budget = budget or BrowseBudget()
        self._emit = emit
        self._save_frame = save_frame
        self._should_stop = should_stop or (lambda: False)
        self._shrink = shrink
        """Applied to every frame *before* the policy sees it. Without it the
        model is handed a device-scale-2 screenshot and refuses the request."""

        self._use_rules = use_rules

    # -- public --------------------------------------------------------------

    async def run(self, task: BrowseTask) -> BrowseReport:
        """Work the task and report, whatever happened. Never raises."""
        started = time.monotonic()
        report = BrowseReport(task=task, outcome=BrowseOutcome.ERROR)
        page: BrowsePage | None = None

        try:
            page = await self._open_page()
        except Exception as exc:
            report.outcome = BrowseOutcome.UNAVAILABLE
            report.detail = f"no browser available: {exc}"
            report.duration_ms = int((time.monotonic() - started) * 1000)
            return report

        try:
            await self._drive(page, task, report, started)
        except Exception as exc:
            report.outcome = BrowseOutcome.ERROR
            report.detail = f"{type(exc).__name__}: {exc}"
            logger.log_warning(f"Browse task failed: {report.detail}", broadcast=False)
        finally:
            # Unconditional. A model that never says `done` must not be able to
            # hold a page — and a semaphore permit behind it — indefinitely.
            with contextlib.suppress(Exception):
                await page.close()
            report.duration_ms = int((time.monotonic() - started) * 1000)

        return report

    # -- the loop ------------------------------------------------------------

    async def _drive(
        self,
        page: BrowsePage,
        task: BrowseTask,
        report: BrowseReport,
        started: float,
    ) -> None:
        status = await page.goto(task.url)
        report.final_url = page.url
        report.http_status = status

        if status in _NOT_FOUND_STATUSES:
            # The one and only route to `not_found`. An empty DOM is not this,
            # and neither is a client-side route change, which has no response.
            report.outcome = BrowseOutcome.NOT_FOUND
            report.detail = f"the page returned HTTP {status}"
            return

        goal = task_sentence(task.platform, task.username)
        last_line = ""
        html = ""
        recent: list[tuple] = []
        refusals = 0
        unusable = 0
        extracted = False

        for step in range(1, self._budget.max_steps + 1):
            if self._should_stop():
                report.outcome = BrowseOutcome.STOPPED
                report.detail = "stopped from the console"
                return
            if time.monotonic() - started >= self._budget.max_seconds:
                report.outcome = BrowseOutcome.TIME_BUDGET
                report.detail = f"{self._budget.max_seconds:.0f}s spent"
                return

            context = await page.context()
            elements = number_elements(await page.collect())
            html = await page.content()
            report.final_url = page.url
            if page.last_status is not None:
                report.http_status = page.last_status

            signal = detect_block_signal(
                http_status=report.http_status,
                final_url=page.url,
                html=html,
            )
            if signal in ("login_redirect", "consent_redirect"):
                report.outcome = BrowseOutcome.LOGIN_WALL
                report.detail = f"the site demanded a sign-in ({signal})"
                return
            if signal == "cf_challenge":
                report.outcome = BrowseOutcome.CHALLENGE
                report.detail = "an anti-bot challenge stood in the way"
                return

            observation = Observation(
                task=goal,
                url=page.url,
                title=str(context.get("title") or ""),
                text=str(context.get("text") or ""),
                elements=elements,
                step=step,
                max_steps=self._budget.max_steps,
                scroll_y=int(context.get("scrollY") or 0),
                scroll_height=int(context.get("scrollHeight") or 0),
                viewport_height=int(context.get("innerHeight") or 0),
                last=last_line,
            )

            frame = await self._frame(page)
            action = rules.suggest(observation) if self._use_rules else None
            if action is None:
                action = await self._policy.decide(observation, frame)
                report.model_calls += 1

            if action is None:
                unusable += 1
                last_line = "the model returned nothing usable"
                if unusable >= UNUSABLE_REPLY_LIMIT:
                    report.outcome = BrowseOutcome.MODEL_UNAVAILABLE
                    report.detail = f"{unusable} unusable replies in a row"
                    return
                continue
            unusable = 0

            frame_name = await self._store_frame(step, frame)
            refusal = guard_check(
                action,
                elements=elements,
                allow_pixel_clicks=self._budget.allow_pixel_clicks,
                viewport=self._budget.viewport,
            )
            if refusal is not None:
                refusals += 1
                last_line = f"{action.kind} -> refused ({refusal.reason}: {refusal.detail})"
                await self._record(
                    report,
                    step,
                    action,
                    "refused",
                    describe_action(action, elements),
                    frame_name,
                    page.url,
                    refusal=refusal,
                )
                if refusals >= REFUSAL_LIMIT:
                    report.outcome = BrowseOutcome.REFUSED
                    report.detail = f"{refusals} refused actions in a row"
                    return
                continue
            refusals = 0

            # `direction` belongs in the signature: without it a scroll down and
            # a scroll up look identical, and an agent working its way up and
            # down a page would be cut off as a stall on its third step.
            signature = (
                action.kind,
                action.index,
                action.x,
                action.y,
                action.text,
                action.url,
                action.direction,
            )
            recent.append(signature)
            if len(recent) >= REPEAT_LIMIT and len(set(recent[-REPEAT_LIMIT:])) == 1:
                await self._record(
                    report, step, action, "failed", describe_action(action, elements), frame_name, page.url
                )
                report.outcome = BrowseOutcome.STALLED
                report.detail = f"the same action {REPEAT_LIMIT} times running"
                return

            if action.kind in (ActionKind.DONE, ActionKind.GIVE_UP):
                await self._record(report, step, action, "ok", describe_action(action, elements), frame_name, page.url)
                report.html = html
                report.outcome = (
                    BrowseOutcome.EXTRACTED
                    if extracted and action.kind is ActionKind.DONE
                    else BrowseOutcome.REACHED_EMPTY
                )
                report.detail = action.thought
                return

            if action.kind is ActionKind.EXTRACT:
                # `extract` carries no text from the model. It means "the content
                # is on screen"; the reading is done by the pipeline's own
                # extractors against the HTML captured here.
                report.html = html
                extracted = True
                last_line = "extract -> page captured"
                await self._record(report, step, action, "ok", describe_action(action, elements), frame_name, page.url)
                continue

            status_word, detail = await self._act(page, action, elements)
            last_line = f"{action.kind} -> {detail}"
            await self._record(
                report, step, action, status_word, describe_action(action, elements), frame_name, page.url
            )
            report.final_url = page.url

        report.html = report.html or html
        report.outcome = BrowseOutcome.EXTRACTED if extracted else BrowseOutcome.STEP_BUDGET
        report.detail = f"{self._budget.max_steps} steps spent"

    # -- helpers -------------------------------------------------------------

    async def _act(self, page: BrowsePage, action: BrowseAction, elements: tuple[Element, ...]) -> tuple[str, str]:
        """Perform one permitted action. A page-level failure is a step, not a crash."""
        try:
            if action.kind is ActionKind.CLICK:
                await page.click_index(int(action.index or 0))
            elif action.kind is ActionKind.CLICK_AT:
                await page.click_at(int(action.x or 0), int(action.y or 0))
            elif action.kind is ActionKind.TYPE:
                await page.type_into(int(action.index or 0), action.text)
            elif action.kind is ActionKind.SCROLL:
                await page.scroll(action.direction)
            elif action.kind is ActionKind.NAVIGATE:
                await page.goto(action.url)
            elif action.kind is ActionKind.WAIT:
                await page.settle()
        except Exception as exc:
            return "failed", f"{type(exc).__name__}"

        if action.kind in (ActionKind.CLICK, ActionKind.CLICK_AT, ActionKind.NAVIGATE):
            # Give the page a moment to react, or the next observation describes
            # the state we just left and the agent re-decides on stale input.
            with contextlib.suppress(Exception):
                await page.settle()
        return "ok", "ok"

    async def _frame(self, page: BrowsePage) -> bytes:
        """One shot, shrunk once, used by both the model and the panel."""
        try:
            raw = await page.screenshot()
        except Exception as exc:
            logger.log_warning(f"Browse screenshot failed: {exc}", broadcast=False)
            return b""

        if not raw or self._shrink is None:
            return raw
        try:
            # Pillow is synchronous and this runs on every step of a loop that is
            # also serving the live stream.
            return await asyncio.to_thread(self._shrink, raw)
        except Exception as exc:
            logger.log_warning(f"Browse frame not shrunk: {exc}", broadcast=False)
            return raw

    async def _store_frame(self, step: int, frame: bytes) -> str:
        if not frame or self._save_frame is None:
            return ""
        try:
            return await self._save_frame(step, frame)
        except Exception as exc:
            logger.log_warning(f"Browse frame not stored: {exc}", broadcast=False)
            return ""

    async def _record(
        self,
        report: BrowseReport,
        step: int,
        action: BrowseAction,
        status: str,
        description: str,
        frame_name: str,
        page_url: str,
        *,
        refusal=None,
    ) -> None:
        entry = BrowseStep(
            step=step,
            action=action,
            status=status,
            description=description,
            refusal=refusal,
            frame_name=frame_name,
            page_url=page_url,
        )
        report.steps.append(entry)
        if self._emit is None:
            return
        try:
            await self._emit(
                "browse_step",
                {
                    "step": step,
                    "max_steps": self._budget.max_steps,
                    "action": str(action.kind),
                    "by": action.by,
                    "status": status,
                    "description": description,
                    "thought": action.thought,
                    "refusal": str(refusal.reason) if refusal else "",
                    "refusal_detail": refusal.detail if refusal else "",
                    "frame_name": frame_name,
                    "page_url": page_url,
                },
            )
        except Exception as exc:  # pragma: no cover - telemetry must not stop work
            logger.log_warning(f"Browse step event not published: {exc}", broadcast=False)


__all__ = ["BrowseAgent", "BrowseBudget"]
