from .search import router as search_router
from .profiles import router as profiles_router
from .history import router as history_router
from .version_history import router as version_history_router
from .face_match import router as face_match_router
from .chat import router as chat_router

__all__ = ["search_router", "profiles_router", "history_router", "version_history_router", "face_match_router", "chat_router"]
