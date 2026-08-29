"""The page abstraction: a narrow protocol, and one adapter over a live page.

Two things are deliberate here.

**The protocol declares exactly what the agent uses** — twelve members, no more.
That is what lets every test drive a ``FakePage`` serving fixture HTML instead
of launching Chromium, and it is why nothing under ``tests/`` ever imports
patchright.

**The adapter never imports patchright either.** It takes the live page as
``Any`` and duck-types the Playwright API. The browser stays entirely owned by
``FetchSession``, which is the invariant recorded in ``discovery/dependencies``:
one owner, one lifecycle, one place that can leak it.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any, Protocol, runtime_checkable

from app.discovery.browse.scripts import (
    CLEAR_OVERLAY_JS,
    COLLECT_ELEMENTS_JS,
    DRAW_OVERLAY_JS,
    IDX_ATTRIBUTE,
    PAGE_CONTEXT_JS,
)
from app.utils.logger import logger

SCROLL_STEP_PX = 700
"""A little less than a viewport, so the agent always keeps some overlap and
cannot scroll straight past the one line it was looking for."""


@runtime_checkable
class BrowsePage(Protocol):
    """Everything the browse agent is allowed to do to a page."""

    @property
    def url(self) -> str: ...

    @property
    def last_status(self) -> int | None:
        """HTTP status of the most recent main-frame navigation, or ``None``.

        The single source for a ``not_found`` verdict. An in-page route change
        produces no response at all, which is exactly why an empty DOM must
        never be read as an absence.
        """
        ...

    async def goto(self, url: str) -> int | None: ...
    async def context(self) -> dict[str, Any]: ...
    async def collect(self) -> list[dict[str, Any]]: ...
    async def screenshot(self) -> bytes: ...
    async def content(self) -> str: ...
    async def click_index(self, index: int) -> None: ...
    async def click_at(self, x: int, y: int) -> None: ...
    async def type_into(self, index: int, text: str) -> None: ...
    async def scroll(self, direction: str) -> None: ...
    async def settle(self, ms: int = 800) -> None: ...
    async def close(self) -> None: ...


class PatchrightPage:
    """Adapts a live Playwright/patchright ``Page`` to :class:`BrowsePage`.

    The four event handlers wired in :meth:`prepare` are not conveniences; each
    closes a way the run could stop being controllable:

    * ``download`` — a driven browser must never write a file to the host.
    * ``filechooser`` — nor read one.
    * ``dialog`` — an ``alert()`` blocks every subsequent command until someone
      clicks it, and nobody is watching this browser.
    * ``page`` — a popup would leave the agent driving a tab it cannot see.
    """

    def __init__(self, page: Any, *, timeout_ms: int = 15_000) -> None:
        self._page = page
        self._timeout = timeout_ms
        self._last_status: int | None = None

    async def prepare(self) -> None:
        """Attach the safety handlers and the navigation-status listener."""
        self._page.set_default_timeout(self._timeout)

        self._page.on("download", lambda download: _fire(download.cancel()))
        self._page.on("filechooser", lambda chooser: _fire(chooser.set_files([])))
        self._page.on("dialog", lambda dialog: _fire(dialog.dismiss()))

        def _on_response(response: Any) -> None:
            # Only the main frame's own document counts. Sub-resource 404s are
            # routine on every large site and say nothing about the account.
            try:
                request = response.request
                if request.is_navigation_request() and request.frame == self._page.main_frame:
                    self._last_status = int(response.status)
            except Exception:  # pragma: no cover - listener must never raise
                pass

        self._page.on("response", _on_response)

        context = getattr(self._page, "context", None)
        if context is not None:
            context.on("page", lambda opened: _fire(opened.close()) if opened is not self._page else None)

    # -- state ---------------------------------------------------------------

    @property
    def url(self) -> str:
        return str(getattr(self._page, "url", "") or "")

    @property
    def last_status(self) -> int | None:
        return self._last_status

    # -- navigation ----------------------------------------------------------

    async def goto(self, url: str) -> int | None:
        self._last_status = None
        response = await self._page.goto(url, wait_until="domcontentloaded", timeout=self._timeout)
        if response is not None:
            self._last_status = int(response.status)
        return self._last_status

    async def settle(self, ms: int = 800) -> None:
        await self._page.wait_for_timeout(ms)

    # -- observation ---------------------------------------------------------

    async def context(self) -> dict[str, Any]:
        return dict(await self._page.evaluate(PAGE_CONTEXT_JS) or {})

    async def collect(self) -> list[dict[str, Any]]:
        return list(await self._page.evaluate(COLLECT_ELEMENTS_JS) or [])

    async def screenshot(self) -> bytes:
        """Viewport-only JPEG, with the numbered overlay drawn on.

        Never ``full_page``: a full shot of an infinite feed is megabytes and
        the model cannot use what is off-screen anyway. The overlay is removed
        again so it can never end up in the harvested HTML.
        """
        try:
            await self._page.evaluate(DRAW_OVERLAY_JS)
        except Exception as exc:
            logger.log_warning(f"Browse overlay failed to draw: {exc}", broadcast=False)
        try:
            return bytes(await self._page.screenshot(type="jpeg", quality=60, full_page=False))
        finally:
            # Suppressed, not logged: the shot is already taken, and a stale
            # overlay is cleared by the next collect() anyway.
            with contextlib.suppress(Exception):
                await self._page.evaluate(CLEAR_OVERLAY_JS)

    async def content(self) -> str:
        return str(await self._page.content() or "")

    # -- actions -------------------------------------------------------------

    def _selector(self, index: int) -> str:
        return f'[{IDX_ATTRIBUTE}="{int(index)}"]'

    async def click_index(self, index: int) -> None:
        await self._page.click(self._selector(index), timeout=self._timeout)

    async def click_at(self, x: int, y: int) -> None:
        await self._page.mouse.click(int(x), int(y))

    async def type_into(self, index: int, text: str) -> None:
        await self._page.fill(self._selector(index), text, timeout=self._timeout)

    async def scroll(self, direction: str) -> None:
        delta = -SCROLL_STEP_PX if str(direction).lower().startswith("up") else SCROLL_STEP_PX
        await self._page.evaluate(f"() => window.scrollBy(0, {delta})")

    async def close(self) -> None:
        try:
            await self._page.close()
        except Exception as exc:  # pragma: no cover - teardown is best effort
            logger.log_warning(f"Browse page did not close cleanly: {exc}", broadcast=False)


def _fire(awaitable: Any) -> None:
    """Run a handler's coroutine without awaiting it.

    Playwright event callbacks are synchronous, so the coroutine they return has
    to be scheduled. Failures are swallowed on purpose: these handlers exist to
    neutralise a download or a dialog, and if one has already gone away there is
    nothing to report and nothing to do.
    """
    if awaitable is None:
        return
    with contextlib.suppress(Exception):
        asyncio.ensure_future(awaitable)
