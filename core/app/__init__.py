"""
Фабрика для создания FastAPI приложений.
"""

from core.app.factory import create_service_app, load_service_settings
from core.app.server import serve

__all__ = ["create_service_app", "load_service_settings", "serve"]
