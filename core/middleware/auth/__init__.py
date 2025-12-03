"""
Auth Middleware - модульная авторизация.
"""

from .middleware import AuthMiddleware, CompanyCreationRequired
from .route_config import RouteRule, RouteMatcher, ROUTE_RULES
from .company_resolver import CompanyResolver
from .context_factory import ContextFactory
from .platform_handlers import (
    PlatformHandler,
    TelegramHandler,
    WhatsAppHandler,
    get_platform_handler,
)

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


