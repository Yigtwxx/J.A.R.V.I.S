"""
Memory routes — CRUD for user memories (Agentic Memory layer).
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.security import verify_api_key
from app.services.user_memory_service import UserMemoryService
from app.services.vector_store_service import vector_store_service

router = APIRouter(prefix="/api/memory", tags=["memory"])

memory_service = UserMemoryService(vector_store=vector_store_service)


class MemoryCreate(BaseModel):
    category: str = Field(..., description="Memory category: preference, fact, interaction, personality")
    key: str = Field(..., description="Memory key/label")
    value: str = Field(..., description="Memory value/content")
    context: str | None = None
    importance: int = Field(default=5, ge=1, le=10)


class MemoryQuery(BaseModel):
    query: str = Field(..., description="Semantic search query")
    n_results: int = Field(default=5, ge=1, le=20)


@router.post("/")
async def remember(
    memory: MemoryCreate,
    db: Session = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
):
    """Store a new memory or update existing one."""
    result = memory_service.remember(
        db=db,
        category=memory.category,
        key=memory.key,
        value=memory.value,
        context=memory.context,
        importance=memory.importance,
    )
    return {"status": "stored", "id": result.id, "key": result.key}


@router.get("/")
async def recall_all(
    category: str | None = None,
    key: str | None = None,
    db: Session = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
):
    """Retrieve memories, optionally filtered by category and/or key."""
    memories = memory_service.recall(db, category=category, key=key)
    return {"memories": memories, "count": len(memories)}


@router.get("/context")
async def get_user_context(
    db: Session = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
):
    """Get the full user context string for AI prompt injection."""
    context = memory_service.build_user_context(db)
    return {"context": context, "has_memories": bool(context)}


@router.post("/search")
async def semantic_search(
    query: MemoryQuery,
    _api_key: str = Depends(verify_api_key),
):
    """Semantically search through user memories."""
    results = memory_service.semantic_recall(query.query, n_results=query.n_results)
    return {"results": results, "query": query.query}


@router.delete("/{memory_id}")
async def forget(
    memory_id: int,
    db: Session = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
):
    """Delete a specific memory."""
    deleted = memory_service.forget(db, memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"status": "erased", "id": memory_id}


@router.delete("/category/{category}")
async def forget_category(
    category: str,
    db: Session = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
):
    """Delete all memories in a category."""
    count = memory_service.forget_category(db, category)
    return {"status": "category_purged", "category": category, "deleted_count": count}
