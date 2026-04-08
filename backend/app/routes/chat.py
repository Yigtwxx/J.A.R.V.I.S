
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.security import verify_api_key
from app.services.ai_service import AIService
from app.services.user_memory_service import UserMemoryService
from app.utils.logger import logger

router = APIRouter(prefix="/api/chat", tags=["chat"])

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    query_name: str
    messages: list[ChatMessage]

ai_service = AIService()
memory_service = UserMemoryService()

@router.post("/")
async def chat_endpoint(request: ChatRequest, db: Session = Depends(get_db), _api_key: str = Depends(verify_api_key)):
    """
    RAG-based conversational endpoint for a specific person.
    Streams back the AI answer based on local JSON context.
    Injects user memory context for personalized responses.
    """
    logger.log_action(f"Incoming direct query for entity: {request.query_name}")

    if not request.query_name or not request.messages:
        raise HTTPException(status_code=400, detail="Missing query_name or messages")

    # Learn from user interaction
    last_user_msg = next((m.content for m in reversed(request.messages) if m.role == "user"), "")
    if last_user_msg:
        memory_service.learn_from_interaction(db, last_user_msg, "")

    # Build user context from memories
    user_context = memory_service.build_user_context(db)

    # The ai_service.chat_with_context returns an async generator
    generator = ai_service.chat_with_context(
        request.query_name, request.messages, user_context=user_context,
    )

    return StreamingResponse(
        generator,
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )
