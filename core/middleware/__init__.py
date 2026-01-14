"""
Middleware - middleware для FastAPI.

Базовые middleware которые могут использовать сервисы.
"""

from core.middleware.auth.middleware import AuthMiddleware

__all__ = ["AuthMiddleware"]













