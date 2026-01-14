"""API endpoints"""

from .a2a import router as a2a_router
from .chat import router as chat_router
from .registry import router as registry_router
from .websocket import router as websocket_router

__all__ = ["registry_router", "a2a_router", "chat_router", "websocket_router"]
