"""Schemas for the spatial console.

The frontend validates every response against a zod schema of the same shape, so
field names here are a contract rather than an implementation detail.
"""

from pydantic import BaseModel, Field

from app.services.window_control import Outcome


class SceneResponse(BaseModel):
    """What the local vision model saw in one frame of the user's own camera."""

    description: str = Field(..., description="A plain-language description of the person and the room behind them.")
    model: str = Field(..., description="Which local model answered, so a swap is visible in the console.")
    elapsed_ms: int = Field(..., description="How long the model took, measured end to end.")


class WindowOut(BaseModel):
    """One real window, in virtual-desktop pixels."""

    id: str = Field(..., description="OS handle. Valid only for the life of this backend process.")
    key: str = Field(..., description="Stable across restarts — what the browser stores a layout against.")
    title: str
    app: str
    x: int
    y: int
    width: int
    height: int
    minimized: bool


class DesktopOut(BaseModel):
    """The whole virtual desktop, which may span several monitors."""

    x: int
    y: int
    width: int
    height: int


class WindowsResponse(BaseModel):
    """The room's real contents, or an honest account of why there are none.

    ``supported`` is never inferred from an empty list: a machine with nothing
    open and a machine that will not let us look are completely different
    situations, and the console says which.
    """

    supported: bool
    reason: str | None = Field(None, description="Why window control is unavailable, in words a user can act on.")
    platform: str
    desktop: DesktopOut | None = None
    windows: list[WindowOut] = Field(default_factory=list)


class FocusResponse(BaseModel):
    """What happened when a window was asked to come forward."""

    id: str
    outcome: Outcome


class TicketResponse(BaseModel):
    """A single-use pass for the window-control socket.

    A browser WebSocket cannot send an ``X-API-Key`` header, and the Next.js
    proxy that adds one cannot forward an upgrade. So the page authenticates over
    HTTP, gets this, and spends it on the socket — which keeps the API key out of
    every URL, log and referrer along the way.
    """

    ticket: str
    expires_in: int = Field(..., description="Seconds until the ticket is refused.")
