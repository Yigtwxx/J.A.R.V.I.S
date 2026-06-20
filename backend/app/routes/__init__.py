from .agent import router as agent_router
from .audit import router as audit_router
from .chat import router as chat_router
from .export import router as export_router
from .face_match import router as face_match_router
from .health import router as health_router
from .history import router as history_router
from .memory import router as memory_router
from .plugins import router as plugins_router
from .profiles import router as profiles_router
from .search import router as search_router
from .system import router as system_router
from .version_history import router as version_history_router
from .vision import router as vision_router
from .visual_intel import router as visual_intel_router
from .watch import router as watch_router

__all__ = [
    "agent_router", "audit_router", "search_router", "profiles_router", "history_router",
    "version_history_router", "face_match_router", "chat_router", "export_router",
    "memory_router", "watch_router", "plugins_router", "vision_router",
    "visual_intel_router", "system_router", "health_router",
]
