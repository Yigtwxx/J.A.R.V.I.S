"""Session-scoped discovery routes.

The existing ``POST /api/search/`` stays as-is and is **non-interactive**: a
blocking HTTP request cannot sensibly wait on a user answer, so questions are
disabled there. These routes are the interactive path — start a session, watch its
event stream, answer its questions, read the result.

The stream is per-session on purpose. The old ``GET /api/status/stream`` is a
global log tap: every log line in the process is broadcast to every listener, so
two concurrent searches interleave into one unattributable feed.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from app.config import get_settings
from app.discovery.brief.model import Gender, KnownProfile, ReferenceAvatar, ReferenceSource, SearchBrief
from app.discovery.brief.parse import parse_brief
from app.discovery.dependencies import (
    get_avatar_store,
    get_browse_control,
    get_discovery_runner,
    get_evidence_store,
    get_frame_store,
    get_question_broker,
    get_session_manager,
)
from app.discovery.hitl.questions import Answer
from app.discovery.loop.runner import DiscoveryRunner, target_key_for
from app.discovery.media.hashing import dhash64
from app.discovery.media.store import AvatarStore
from app.discovery.platforms.registry import (
    DISCOVERY_ONLY_PLATFORMS,
    UNSUPPORTED_PLATFORMS,
    get_core_registry,
    load_extended_specs,
)
from app.discovery.platforms.urlmatch import match_profile_url
from app.discovery.session.events import EventType, error_payload
from app.discovery.types import EntityType, FetchTier
from app.middleware.security import verify_api_key
from app.schemas.discovery import (
    AnswerAck,
    AnswerRequest,
    BriefParseRequest,
    KnownProfileOut,
    PlatformCatalog,
    PlatformInfo,
    ReferenceAvatarOut,
    ReferenceAvatarResponse,
    SearchBriefIn,
    SearchBriefOut,
    SessionStartResponse,
)
from app.schemas.profile import SearchQuery
from app.utils.logger import logger
from app.utils.sse import with_heartbeat

router = APIRouter(prefix="/api/search", tags=["discovery"])
media_router = APIRouter(prefix="/api/media", tags=["media"])

_SETTINGS = get_settings()


@router.get("/platforms", response_model=PlatformCatalog)
async def list_platforms(_api_key: str = Depends(verify_api_key)) -> PlatformCatalog:
    """The platforms a caller may pick from, straight out of the registry.

    Served rather than hard-coded in the client so the picker cannot drift from
    what the sweep actually checks — a stale client list would offer platforms
    that no longer exist and hide ones that do.
    """
    specs = sorted(get_core_registry().all(), key=lambda s: (s.category, -s.expected_reliability, s.key))
    return PlatformCatalog(
        platforms=[
            PlatformInfo(
                key=spec.key,
                display=spec.display,
                category=spec.category,
                entity_types=sorted(str(entity) for entity in spec.entity_types),
                expected_reliability=spec.expected_reliability,
                requires_stealth=spec.fetch_tier is FetchTier.STEALTH,
                supported=spec.key not in UNSUPPORTED_PLATFORMS,
                unsupported_reason=UNSUPPORTED_PLATFORMS.get(spec.key),
                discovery_only=spec.key in DISCOVERY_ONLY_PLATFORMS,
                discovery_only_reason=DISCOVERY_ONLY_PLATFORMS.get(spec.key),
            )
            for spec in specs
        ],
        extended_count=len(load_extended_specs()),
        extended_min_depth=_SETTINGS.discovery_extended_platforms_min_depth,
    )


# -- the search brief -----------------------------------------------------------


def _brief_from_request(payload: SearchBriefIn, raw_query: str, entity: EntityType) -> SearchBrief:
    """Turn the client's brief into the pipeline's own type.

    `SearchBriefIn.known_profiles` has already been validated as recognisable
    profile URLs, so `match_profile_url` cannot return None here - but it is
    still called rather than trusted, because it is the only thing allowed to
    decide what platform a URL belongs to.
    """
    known = [KnownProfile.from_match(m) for url in payload.known_profiles if (m := match_profile_url(url))]
    avatar = _reference_avatar(payload.reference_image_id)
    return SearchBrief(
        name=(payload.name or "").strip() or raw_query,
        entity=entity,
        gender=Gender(payload.gender),
        known_profiles=tuple(known),
        usernames=tuple(payload.usernames),
        location=payload.location,
        employer=payload.employer,
        school=payload.school,
        email=payload.email,
        domain=payload.domain,
        reference_avatar=avatar,
    )


def _reference_avatar(image_id: str | None) -> ReferenceAvatar | None:
    """Look the uploaded picture back up by its digest, or None if it is gone.

    A missing file is not an error: the store is a cache with its own sweeps, and
    losing a reference photo costs the search two scoring signals, not its
    correctness. Failing the whole request over it would be far worse.
    """
    if not image_id:
        return None
    store = AvatarStore()
    for extension in ("jpg", "png", "gif", "webp"):
        path = store.resolve(f"{image_id}.{extension}")
        if path is None:
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            return None
        return ReferenceAvatar(
            sha256=image_id,
            dhash=dhash64(raw),
            local_url=f"/api/media/avatars/{image_id}.{extension}",
            source=ReferenceSource.UPLOAD,
        )
    logger.log_warning(f"Reference image {image_id[:12]} is no longer on disk; the search runs without it")
    return None


def _brief_to_out(brief: SearchBrief) -> SearchBriefOut:
    """The wire shape of a parsed brief, as the editable chip renders it."""
    avatar = brief.reference_avatar
    return SearchBriefOut(
        name=brief.name,
        gender=brief.gender.value,
        known_profiles=[
            KnownProfileOut(
                platform=p.platform,
                username=p.username,
                canonical_url=p.canonical_url,
                raw_url=p.raw_url or p.canonical_url,
            )
            for p in brief.known_profiles
        ],
        usernames=list(brief.usernames),
        location=brief.location,
        employer=brief.employer,
        school=brief.school,
        email=brief.email,
        domain=brief.domain,
        reference_avatar=(
            ReferenceAvatarOut(
                sha256=avatar.sha256,
                dhash=avatar.dhash,
                preview_url=avatar.local_url,
                source=avatar.source.value,
            )
            if avatar is not None
            else None
        ),
        unparsed=list(brief.unparsed),
        is_empty=brief.is_empty,
    )


@router.post("/brief/parse", response_model=SearchBriefOut)
async def parse_search_brief(
    payload: BriefParseRequest,
    _api_key: str = Depends(verify_api_key),
) -> SearchBriefOut:
    """Read a free-text query into a structured brief, without starting a search.

    Deterministic and cheap - no model, no network - so the UI can call it as the
    user types and show what the search is about to do before it does it. Anything
    the parser could not place comes back in `unparsed` rather than being guessed
    into a field.
    """
    brief = parse_brief(payload.text, entity=EntityType(payload.entity_type))
    return _brief_to_out(brief)


@router.post("/brief/avatar", response_model=ReferenceAvatarResponse)
async def upload_reference_avatar(
    file: UploadFile = File(...),
    _api_key: str = Depends(verify_api_key),
    avatars: AvatarStore = Depends(get_avatar_store),
) -> ReferenceAvatarResponse:
    """Store a reference photo and return the digest a search refers to it by.

    The content type the browser sends is not trusted: `save_bytes` sniffs the
    magic bytes, because a page served with `image/jpeg` is exactly how junk
    would otherwise acquire a digest and a public URL.

    What this buys is deliberately modest and the UI must say so: the picture is
    compared to other avatars **as a file** (sha256, and a dhash that survives a
    resize). It finds the same photograph reused across platforms. It is not face
    recognition and will not find the same person in a different photograph.
    """
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="The uploaded file is empty")

    stored = await asyncio.to_thread(avatars.save_bytes, raw, source_url=file.filename or "upload")
    if stored is None:
        raise HTTPException(
            status_code=415,
            detail="That file is not a readable image, or it exceeds the 8 MB limit",
        )

    logger.log_action(f"Reference photo stored as {stored.sha256[:12]} ({stored.bytes_len} bytes)")
    return ReferenceAvatarResponse(
        sha256=stored.sha256,
        dhash=stored.dhash,
        preview_url=stored.local_url,
        width=stored.width,
        height=stored.height,
        bytes_len=stored.bytes_len,
        content_type=stored.content_type,
    )


@router.post("/sessions", status_code=202, response_model=SessionStartResponse)
async def start_search_session(
    query: SearchQuery,
    _api_key: str = Depends(verify_api_key),
    runner: DiscoveryRunner = Depends(get_discovery_runner),
    manager=Depends(get_session_manager),
) -> SessionStartResponse:
    """Start an interactive search and return immediately with its stream URLs."""
    raw = query.query.strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    if not _SETTINGS.discovery_enabled:
        raise HTTPException(status_code=503, detail="Discovery pipeline is disabled (set DISCOVERY_ENABLED=true)")

    entity = EntityType(getattr(query, "entity_type", "person"))
    interactive = bool(getattr(query, "interactive", True))
    # A client that sent no brief still gets one, parsed from `query` with the
    # same deterministic rules the UI previews with. That is what keeps a bare
    # `?q=` replay and the blocking fallback behaving like the interactive path.
    brief = _brief_from_request(query.brief, raw, entity) if query.brief else parse_brief(raw, entity=entity)
    session_id = str(uuid.uuid4())
    target_key = target_key_for(raw, entity)
    live = manager.create(session_id, target_key)

    # asyncio.create_task, NOT FastAPI BackgroundTasks: the latter only runs after
    # the response is sent and cannot be cancelled, so a runaway search would be
    # unkillable and its exception unobserved.
    task = asyncio.create_task(
        runner.run(
            session_id=session_id,
            raw_query=raw,
            entity_type=entity,
            depth=query.depth,
            interactive=interactive,
            platforms=query.platforms,
            include_extended=query.include_extended_platforms,
            brief=brief,
            bus=live.bus,
        )
    )
    manager.register_task(session_id, task)
    scope = "all platforms" if query.platforms is None else f"{len(query.platforms)} platforms"
    logger.log_action(f"Discovery session {session_id[:8]} started for {raw!r} (depth {query.depth}, {scope})")
    if not brief.is_empty:
        logger.log_action(f"Discovery session {session_id[:8]} brief: {brief.summary()}")

    return SessionStartResponse(
        session_id=session_id,
        target_key=target_key,
        stream_url=f"/api/search/sessions/{session_id}/stream",
        answer_url=f"/api/search/sessions/{session_id}/answer",
    )


@router.get("/sessions/{session_id}/stream")
async def stream_search_session(
    session_id: str,
    request: Request,
    last_event_id: int | None = Query(default=None, alias="last_event_id"),
    _api_key: str = Depends(verify_api_key),
    manager=Depends(get_session_manager),
) -> StreamingResponse:
    """Server-sent events for one session, with `Last-Event-ID` replay."""
    live = manager.get(session_id)
    if live is None:
        raise HTTPException(status_code=404, detail="Unknown or finished session")

    resume_from = last_event_id
    header = request.headers.get("Last-Event-ID")
    if resume_from is None and header and header.isdigit():
        resume_from = int(header)

    async def _events() -> AsyncIterator[str]:
        try:
            async for event in live.bus.subscribe(last_event_id=resume_from):
                if await request.is_disconnected():
                    break
                yield event.to_sse()
                # The session is over: close the response instead of holding the
                # connection open forever. Without this the client waits on a
                # stream that will never produce another byte, which looks
                # identical to a search that is still working.
                if event.type in (EventType.done, EventType.error):
                    break
        except asyncio.CancelledError:  # client went away mid-stream
            raise
        except Exception as exc:
            logger.log_error(f"SSE stream failed for {session_id[:8]}: {exc}")
            yield f"event: error\ndata: {json.dumps(error_payload(str(exc), fatal=True))}\n\n"

    return StreamingResponse(
        # Wrapped so a quiet phase cannot look like a dead connection: a search
        # can spend minutes in one fetch, and Node's undici cuts a body that
        # sends nothing for 300 s (seen live, `UND_ERR_BODY_TIMEOUT`).
        with_heartbeat(_events()),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/sessions/{session_id}/answer", response_model=AnswerAck)
async def answer_question(
    session_id: str,
    payload: AnswerRequest,
    _api_key: str = Depends(verify_api_key),
    manager=Depends(get_session_manager),
    broker=Depends(get_question_broker),
) -> AnswerAck:
    """Answer a pending question and let the paused search continue.

    ``unknown`` and ``skipped`` both mean "we still don't know": they add no
    evidence and apply no penalty. Only an explicit rejection option counts as a no.
    """
    live = manager.get(session_id)
    if live is None:
        raise HTTPException(status_code=404, detail="Unknown or finished session")

    answer = Answer(
        question_id=payload.question_id,
        option_ids=tuple(payload.option_ids),
        text=payload.text,
        skipped=payload.skipped,
        timed_out=False,
        unknown=payload.unknown,
    )
    accepted = broker.resolve(session_id, answer)
    if not accepted:
        raise HTTPException(
            status_code=409,
            detail=f"Session is {live.status} and is not awaiting that question",
        )
    await live.bus.publish(
        EventType.answer_received,
        {"question_id": payload.question_id, "unknown": payload.unknown, "skipped": payload.skipped},
    )
    return AnswerAck(accepted=True, session_status=live.status)


@router.post("/sessions/{session_id}/browse/stop", status_code=202, response_class=Response)
async def stop_browsing(
    session_id: str,
    _api_key: str = Depends(verify_api_key),
    manager=Depends(get_session_manager),
    control=Depends(get_browse_control),
) -> Response:
    """Stop the browse the console is showing, without ending the search.

    202, not 204: the flag is read between steps, so the browser may still be
    mid-click when this returns. Accepted, not completed.

    The search itself carries on through its remaining phases with everything
    already collected — a user closing a live view is not asking to throw away
    eight minutes of work.
    """
    if manager.get(session_id) is None:
        raise HTTPException(status_code=404, detail="Unknown or finished session")
    control.stop(session_id)
    return Response(status_code=202)


@router.delete("/sessions/{session_id}", status_code=204, response_class=Response)
async def cancel_search_session(
    session_id: str,
    _api_key: str = Depends(verify_api_key),
    manager=Depends(get_session_manager),
    broker=Depends(get_question_broker),
) -> Response:
    """Cancel a running search."""
    broker.cancel_session(session_id)
    if not await manager.cancel(session_id):
        raise HTTPException(status_code=404, detail="Unknown or finished session")
    return Response(status_code=204)


@router.get("/sessions/{session_id}/result")
async def get_session_result(
    session_id: str,
    _api_key: str = Depends(verify_api_key),
    store=Depends(get_evidence_store),
) -> dict:
    """The finished profile for a session.

    Returns the same field set as the blocking ``POST /api/search/`` route, so the
    interactive path produces a real, durable result rather than only a live feed.
    Until the search finishes there is no profile yet, so the response carries the
    session's status and a `ready: false` flag instead of a partial profile —
    a half-built profile is exactly the composite the pipeline exists to avoid.
    """
    record = await store.get_session(session_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Unknown session")

    payload = record.get("result_json")
    if not payload:
        return {
            "ready": False,
            "session_id": session_id,
            "status": record.get("status", "running"),
            "termination_reason": record.get("termination_reason"),
            "detail": "The search has not produced a result yet.",
        }
    return {"ready": True, "session_id": session_id, "status": record.get("status"), **payload}


@media_router.get("/avatars/{filename}")
async def get_avatar(
    filename: str,
    _api_key: str = Depends(verify_api_key),
    avatars=Depends(get_avatar_store),
) -> FileResponse:
    """Serve a downloaded avatar.

    Path resolution is done by ``AvatarStore.resolve``, which only accepts a
    64-hex-character basename with a known image extension and refuses anything
    that escapes the storage root — this endpoint must not become a file-read
    primitive.
    """
    path: Path | None = avatars.resolve(filename)
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="Avatar not found")
    return FileResponse(path, headers={"Cache-Control": "public, max-age=86400"})


@media_router.get("/frames/{session_id}/{filename}")
async def get_browse_frame(
    session_id: str,
    filename: str,
    _api_key: str = Depends(verify_api_key),
    frames=Depends(get_frame_store),
) -> FileResponse:
    """One live browse frame.

    ``no-store`` rather than the avatar route's 24 h cache: avatars are content-
    addressed and immutable, while a frame path is reused by the next session
    that gets the same step number.
    """
    path: Path | None = frames.resolve(session_id, filename)
    if path is None:
        raise HTTPException(status_code=404, detail="Frame not found")
    return FileResponse(path, headers={"Cache-Control": "no-store"})
