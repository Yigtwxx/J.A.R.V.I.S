from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.dependencies import get_agent_loop
from app.middleware.security import verify_api_key
from app.utils.logger import logger

router = APIRouter(prefix="/api/agent", tags=["agent"])

class AgentChatMessage(BaseModel):
    role: str
    content: str


class AgentChatRequest(BaseModel):
    message: str
    history: list[AgentChatMessage] = []
    stream: bool = True


@router.post("/chat")
async def agent_chat(
    request: AgentChatRequest,
    _api_key: str = Depends(verify_api_key),
    _agent=Depends(get_agent_loop),
):
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
async def list_agent_tools(
    _api_key: str = Depends(verify_api_key),
    _agent=Depends(get_agent_loop),
):
    """List all available tools the agent can use."""
    return {"tools": _agent.registry.get_ollama_schemas()}
