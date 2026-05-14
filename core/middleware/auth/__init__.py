"""
Auth Middleware - модульная авторизация.
"""

from .company_resolver import CompanyResolver
from .context_factory import ContextFactory
from .middleware import AuthMiddleware, CompanyCreationRequired
from .platform_handlers import (
    PlatformHandler,
    TelegramHandler,
    WhatsAppHandler,
    get_platform_handler,
)
from .route_config import ROUTE_RULES, RouteMatcher, RouteRule

__all__ = [
    "AuthMiddleware",
    "CompanyCreationRequired",
    "RouteRule",
    "RouteMatcher",
    "ROUTE_RULES",
    "CompanyResolver",
    "ContextFactory",
    "PlatformHandler",
    "TelegramHandler",
    "WhatsAppHandler",
    "get_platform_handler",
]


