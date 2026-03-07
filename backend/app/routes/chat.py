from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List
from app.services.ai_service import AIService
from app.utils.logger import logger

router = APIRouter(prefix="/api/chat", tags=["chat"])

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    query_name: str
    messages: List[ChatMessage]

ai_service = AIService()

@router.post("/")
async def chat_endpoint(request: ChatRequest):
    """
    RAG-based conversational endpoint for a specific person.
    Streams back the AI answer based on local JSON context.
    """
    logger.log_action(f"Incoming direct query for entity: {request.query_name}")
    
    if not request.query_name or not request.messages:
        raise HTTPException(status_code=400, detail="Missing query_name or messages")
        
    # The ai_service.chat_with_context returns an async generator
    generator = ai_service.chat_with_context(request.query_name, request.messages)
    
    return StreamingResponse(
        generator, 
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )
