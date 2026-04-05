from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agents.agent_loop import AgentLoop
from app.agents.tools.osint_tools import build_osint_registry
from app.utils.logger import logger

router = APIRouter(prefix="/api/agent", tags=["agent"])

# Build registry once at module load
_registry = build_osint_registry()
_agent = AgentLoop(registry=_registry)


class AgentChatMessage(BaseModel):
    role: str
    content: str


class AgentChatRequest(BaseModel):
    message: str
    history: list[AgentChatMessage] = []
    stream: bool = True


@router.post("/chat")
async def agent_chat(request: AgentChatRequest):
    """Agentic chat endpoint — the AI decides which OSINT tools to call."""
    logger.log_action("Agent chat request received", target=request.message[:80])

    history = [{"role": m.role, "content": m.content} for m in request.history]

    if request.stream:
        generator = _agent.run_streaming(
            user_message=request.message,
            conversation_history=history if history else None,
        )
        return StreamingResponse(
            generator,
            media_type="text/plain",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )
    else:
        result = await _agent.run(
            user_message=request.message,
            conversation_history=history if history else None,
        )
        return {"response": result}


@router.get("/tools")
async def list_agent_tools():
    """List all available tools the agent can use."""
    return {"tools": _registry.get_ollama_schemas()}
