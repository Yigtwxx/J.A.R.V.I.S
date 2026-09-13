"""The spatial console's backend surface.

Two things live here.

**Describing a frame.** The camera never leaves the browser. One frame comes here
when the user asks for it, goes to the local Ollama model, and is not stored —
no frame store, no disk write, no upstream call. That is the whole reason this
runs against a local model rather than a hosted one.

This is a person looking at their own camera on their own machine, which is a
different thing from the OSINT pipeline's scope boundary: that bars reaching
other people's cameras and tracking individuals, and nothing here does either.

**Moving real windows.** A web page cannot move another application's window, so
the console hands the geometry here and this drives the OS. Dragging one card
produces a position sixty times a second, which is why that path is a WebSocket
and not sixty POSTs — and why the socket is reached with a single-use ticket
rather than a header the browser has no way to send.

Every window operation reports ``ok``, ``blocked`` or ``gone`` per window. An
elevated window that a normal process cannot touch says so; it never quietly
stays where it was while the card moves on without it.
"""

import asyncio
import contextlib
import secrets
import time

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect

from app.config import get_settings
from app.middleware.security import verify_api_key
from app.schemas.spatial import (
    DesktopOut,
    FocusResponse,
    SceneResponse,
    TicketResponse,
    WindowOut,
    WindowsResponse,
)
from app.services.vision_service import (
    VisionImageError,
    VisionUnavailableError,
    vision_service,
)
from app.services.window_control import (
    Outcome,
    WindowController,
    WindowControlUnsupported,
    get_window_controller,
)
from app.utils.logger import logger

router = APIRouter(prefix="/api/spatial", tags=["spatial"])

_SETTINGS = get_settings()

#: 8 MB, the same ceiling the reference-avatar upload uses. A camera still is a
#: few hundred kilobytes; anything near this is not one.
MAX_FRAME_BYTES = 8 * 1024 * 1024

#: Magic bytes, because the browser's content type is not evidence of anything.
_IMAGE_SIGNATURES = (
    b"\xff\xd8\xff",  # JPEG
    b"\x89PNG\r\n\x1a\n",  # PNG
    b"RIFF",  # WEBP (checked further below)
)

_SCENE_PROMPT = (
    "You are looking through a webcam at the person using this computer, in their own room. "
    "In two or three sentences, describe what you see: the person, what they are wearing, "
    "and the room behind them. Name the furniture and surfaces you can make out. "
    "Describe only what is visible. Do not guess at who they are and do not speculate."
)


def _looks_like_image(raw: bytes) -> bool:
    if raw.startswith(_IMAGE_SIGNATURES[0]) or raw.startswith(_IMAGE_SIGNATURES[1]):
        return True
    return raw.startswith(b"RIFF") and raw[8:12] == b"WEBP"


@router.post("/scene", response_model=SceneResponse)
async def describe_scene(
    file: UploadFile = File(...),
    _api_key: str = Depends(verify_api_key),
) -> SceneResponse:
    """Describe one camera frame using the local vision model.

    The frame is read into memory, sent to Ollama and dropped. Nothing is written
    to disk: unlike the browse tier's screenshots there is nothing here to come
    back to later, and a directory quietly filling with pictures of someone's
    living room is not a feature anybody asked for.

    Calling this evicts the chat model from an 8 GB card, since `qwen2.5vl:7b`
    and `qwen3.5:9b` cannot co-reside — and it evicts more than that. Measured
    on the reporting machine: 6958 MiB of 8188 used with the scene model alone
    resident, already spilling 13% of it to CPU, while the console holds a live
    camera and a MediaPipe network on the same card. That is a whole-desktop
    stall, not a slow endpoint. So the frame is only ever sent when the user
    asks for it, and the model is released the moment it has answered.
    """
    if not _SETTINGS.spatial_enabled:
        raise HTTPException(status_code=503, detail="The spatial console is disabled (set SPATIAL_ENABLED=true)")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="The uploaded frame is empty")
    if len(raw) > MAX_FRAME_BYTES:
        raise HTTPException(
            status_code=413, detail=f"The frame exceeds the {MAX_FRAME_BYTES // (1024 * 1024)} MB limit"
        )
    if not _looks_like_image(raw):
        raise HTTPException(status_code=415, detail="That file is not a readable JPEG, PNG or WebP image")

    model = _SETTINGS.spatial_scene_model or _SETTINGS.vision_model
    started = time.monotonic()

    try:
        description = await vision_service.analyze_image_bytes(
            raw, prompt=_SCENE_PROMPT, keep_alive=_SETTINGS.spatial_scene_keep_alive
        )
    except VisionUnavailableError as exc:
        # 503, not a 200 carrying an apology: a model that could not load is an
        # outage, and the console has to be able to say so.
        logger.log_warning(f"Spatial scene unavailable: {exc}", broadcast=False)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except VisionImageError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    elapsed_ms = int((time.monotonic() - started) * 1000)
    logger.log_action(f"Spatial scene described in {elapsed_ms} ms", target=model)

    return SceneResponse(description=description, model=model, elapsed_ms=elapsed_ms)


# --- Window control ----------------------------------------------------------

#: How long a socket ticket stays spendable. Long enough for the page to open the
#: connection, short enough that one leaked into a log is already useless.
TICKET_TTL_SECONDS = 30

#: The most windows one frame may ask to move. A drag touches one; a pan touches
#: everything in the room. Well past either, and a bound on what a single message
#: can make the operating system do.
MAX_BATCH = 64

#: ticket -> expiry, in monotonic seconds. In memory on purpose: a ticket that
#: outlived a backend restart would be a credential with no owner.
_tickets: dict[str, float] = {}


def _require_window_control() -> None:
    if not _SETTINGS.spatial_enabled:
        raise HTTPException(status_code=503, detail="The spatial console is disabled (set SPATIAL_ENABLED=true)")
    if not _SETTINGS.spatial_window_control:
        raise HTTPException(
            status_code=403,
            detail="Moving real windows is switched off (set SPATIAL_WINDOW_CONTROL=true in .env to enable it)",
        )


def _issue_ticket() -> str:
    now = time.monotonic()
    # Swept here rather than on a timer: the dict only grows when tickets are
    # issued, so the only moment it can need pruning is when one is.
    for value, expiry in list(_tickets.items()):
        if expiry <= now:
            del _tickets[value]

    ticket = secrets.token_urlsafe(32)
    _tickets[ticket] = now + TICKET_TTL_SECONDS
    return ticket


def _spend_ticket(ticket: str | None) -> bool:
    """Single use: a ticket is valid exactly once, and then it is gone."""
    if not ticket:
        return False
    expiry = _tickets.pop(ticket, None)
    return expiry is not None and expiry > time.monotonic()


@router.post("/ticket", response_model=TicketResponse)
async def issue_socket_ticket(_api_key: str = Depends(verify_api_key)) -> TicketResponse:
    """Mint a single-use pass for the window-control socket.

    The page authenticates here, over HTTP, where it can send the API key as a
    header — then spends the ticket on the socket, which cannot. That keeps the
    key out of the URL, and so out of the browser history, the server log and any
    referrer.
    """
    _require_window_control()
    return TicketResponse(ticket=_issue_ticket(), expires_in=TICKET_TTL_SECONDS)


@router.get("/windows", response_model=WindowsResponse)
async def list_windows(_api_key: str = Depends(verify_api_key)) -> WindowsResponse:
    """What is open, and where.

    An unsupported platform answers with ``supported: false`` and a reason, not
    an empty list. The two are indistinguishable to a caller otherwise, and the
    console would show an empty room with nothing to say about why.
    """
    _require_window_control()
    controller = get_window_controller()

    if not controller.is_supported():
        return WindowsResponse(
            supported=False,
            reason=controller.unsupported_reason(),
            platform=controller.platform,
        )

    try:
        # Enumeration is a blocking pass over every top-level window; kept off
        # the event loop, which the SSE streams are sharing.
        windows = await asyncio.to_thread(controller.list_windows)
        desktop = await asyncio.to_thread(controller.desktop_bounds)
    except WindowControlUnsupported as exc:
        return WindowsResponse(supported=False, reason=str(exc), platform=controller.platform)

    return WindowsResponse(
        supported=True,
        platform=controller.platform,
        desktop=DesktopOut(x=desktop.x, y=desktop.y, width=desktop.width, height=desktop.height),
        windows=[
            WindowOut(
                id=window.id,
                key=window.key,
                title=window.title,
                app=window.app,
                x=window.x,
                y=window.y,
                width=window.width,
                height=window.height,
                minimized=window.minimized,
            )
            for window in windows
        ],
    )


@router.post("/windows/{window_id}/focus", response_model=FocusResponse)
async def focus_window(window_id: str, _api_key: str = Depends(verify_api_key)) -> FocusResponse:
    """Bring one window to the front — gestures 5, 6 and 10 all land here."""
    _require_window_control()
    controller = get_window_controller()

    try:
        outcome = await asyncio.to_thread(controller.focus, window_id)
    except WindowControlUnsupported as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc

    return FocusResponse(id=window_id, outcome=outcome)


@router.websocket("/ws")
async def window_socket(websocket: WebSocket, ticket: str | None = None) -> None:
    """The drag channel.

    Dragging a card produces a new position every frame, and panning the room
    produces one for every window at once. Over HTTP that is sixty round trips a
    second per window; over one socket it is one message a frame carrying the
    whole batch.

    The ticket is checked before the upgrade is accepted, so an unauthenticated
    caller never gets a connection to hold open.
    """
    if not (_SETTINGS.spatial_enabled and _SETTINGS.spatial_window_control):
        await websocket.close(code=4403, reason="Window control is switched off")
        return
    if not _spend_ticket(ticket):
        await websocket.close(code=4401, reason="Invalid or expired ticket")
        return

    controller = get_window_controller()
    await websocket.accept()

    if not controller.is_supported():
        await websocket.send_json(
            {"op": "unsupported", "platform": controller.platform, "reason": controller.unsupported_reason()}
        )
        await websocket.close(code=1000)
        return

    try:
        while True:
            message = await websocket.receive_json()
            await websocket.send_json(await _handle(controller, message))
    except WebSocketDisconnect:
        return
    except Exception as exc:  # noqa: BLE001 - a dropped socket must not take the app down
        logger.log_warning(f"Spatial window socket failed: {exc}", broadcast=False)
        # Best effort: the peer may already be gone, which is not an error here.
        with contextlib.suppress(RuntimeError):
            await websocket.close(code=1011)


async def _handle(controller: WindowController, message: object) -> dict[str, object]:
    """One socket message in, one reply out."""
    if not isinstance(message, dict):
        return {"op": "error", "detail": "Expected a JSON object"}

    op = message.get("op")

    if op == "move":
        items = message.get("items")
        if not isinstance(items, list):
            return {"op": "error", "detail": "`move` needs an `items` array"}
        if len(items) > MAX_BATCH:
            return {"op": "error", "detail": f"At most {MAX_BATCH} windows per message"}

        # The whole batch in one thread hop. Per-item hops cost more than the
        # SetWindowPos calls themselves at sixty frames a second.
        results = await asyncio.to_thread(_move_batch, controller, items)
        return {"op": "moved", "results": results}

    if op == "focus":
        window_id = message.get("id")
        if not isinstance(window_id, str):
            return {"op": "error", "detail": "`focus` needs an `id`"}
        outcome = await asyncio.to_thread(controller.focus, window_id)
        return {"op": "focused", "id": window_id, "outcome": outcome.value}

    return {"op": "error", "detail": f"Unknown op {op!r}"}


def _move_batch(controller: WindowController, items: list[object]) -> dict[str, str]:
    """Move every window in one frame's worth of instructions."""
    results: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        window_id = item.get("id")
        if not isinstance(window_id, str):
            continue
        try:
            outcome = controller.move(
                window_id,
                int(item.get("x", 0)),
                int(item.get("y", 0)),
                int(item.get("w", 0)),
                int(item.get("h", 0)),
            )
        except (TypeError, ValueError):
            # A malformed instruction is not a window that vanished, but it is
            # equally not one that moved, and the card must not pretend it did.
            outcome = Outcome.GONE
        results[window_id] = outcome.value
    return results
