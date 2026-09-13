import json
from collections.abc import AsyncIterator
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agents.agent_loop import AgentEvent
from app.agents.pending_actions import agent_action_queue
from app.dependencies import get_agent_loop
from app.middleware.security import verify_api_key
from app.utils.logger import logger
from app.utils.sse import with_heartbeat

router = APIRouter(prefix="/api/agent", tags=["agent"])


class AgentChatMessage(BaseModel):
    role: str
    content: str


class AgentChatRequest(BaseModel):
    message: str
    history: list[AgentChatMessage] = []
    stream: bool = True


class ActionResolution(BaseModel):
    decision: Literal["approve", "deny"]
    history: list[AgentChatMessage] = []


def _frame(event: AgentEvent) -> str:
    """One SSE frame. The type is repeated in the body so a parser that keeps
    only `data:` lines — which is what the console's own `parseSseFrames` does —
    still knows what it is holding."""
    return f"event: {event.get('type', 'message')}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"


async def _frames(events: AsyncIterator[AgentEvent]) -> AsyncIterator[str]:
    async for event in events:
        yield _frame(event)


def _sse(events: AsyncIterator[AgentEvent]) -> StreamingResponse:
    return StreamingResponse(
        # A tool-calling round can spend minutes producing no tokens, and Node's
        # undici cuts a response body that stays silent for 300 s — the failure
        # already seen live on the two search streams.
        with_heartbeat(_frames(events)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _history(messages: list[AgentChatMessage]) -> list[dict] | None:
    return [{"role": m.role, "content": m.content} for m in messages] or None


@router.post("/chat")
async def agent_chat(
    request: AgentChatRequest,
    _api_key: str = Depends(verify_api_key),
    _agent=Depends(get_agent_loop),
):
    """Agentic chat endpoint — the AI decides which tools to call."""
    logger.log_action("Agent chat request received", target=request.message[:80])

    history = _history(request.history)

    if request.stream:
        return _sse(_agent.run_events(user_message=request.message, conversation_history=history))

    return await _agent.run(user_message=request.message, conversation_history=history)


@router.post("/actions/{action_id}/resolve")
async def resolve_agent_action(
    action_id: str,
    request: ActionResolution,
    _api_key: str = Depends(verify_api_key),
    _agent=Depends(get_agent_loop),
):
    """Answer an approval the agent stopped on, then carry the turn on.

    Resolving and resuming are one call so approving continues the same turn
    instead of starting a disconnected second one — the user asked a question,
    approved one step of the answer, and should get the rest of the answer.
    """
    action = agent_action_queue.get(action_id)
    if action is None:
        # The queue is in-memory, so this is also what a backend restart between
        # the question and the answer looks like.
        raise HTTPException(status_code=404, detail="This action is no longer pending; nothing was performed.")

    tool_name = action.action_type
    approved = request.decision == "approve"

    try:
        result = await agent_action_queue.resolve(action_id, approved=approved, registry=_agent.registry)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="This action is no longer pending.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    async def _events() -> AsyncIterator[AgentEvent]:
        # The outcome is reported before the model gets a chance to describe it,
        # so what actually happened is on screen even if the follow-up fails.
        yield {"type": "tool_result", "tool": tool_name, "content": result}
        async for event in _agent.resume_events(
            tool_name=tool_name,
            tool_result=result,
            conversation_history=_history(request.history),
        ):
            yield event

    return _sse(_events())


@router.get("/actions")
async def list_agent_actions(_api_key: str = Depends(verify_api_key)):
    """Approvals the agent is still waiting on."""
    pending = agent_action_queue.list_pending()
    return {"pending_actions": pending, "count": len(pending)}


@router.get("/tools")
async def list_agent_tools(
    _api_key: str = Depends(verify_api_key),
    _agent=Depends(get_agent_loop),
):
    """List all available tools the agent can use."""
    return {"tools": _agent.registry.get_ollama_schemas()}
