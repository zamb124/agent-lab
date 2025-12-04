"""
Декларативная конфигурация маршрутов для AuthMiddleware.
"""

import fnmatch
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class RouteRule:
    """Правило маршрутизации"""
    
    pattern: str
    skip: bool = False
    auth_required: bool = True
    context_type: str = "frontend"
    platform: Optional[str] = None


SKIP_PATHS = [
    "/static/*",
    "/.well-known/*",
    "/favicon.ico",
    "/health",
    "/agents/health",
    "/crm/health",
    "/debug/*",
]

ROUTE_RULES: List[RouteRule] = [
    # Webhooks - без авторизации, специальный контекст
    RouteRule("/agents/api/v1/webhook/telegram/*", auth_required=False, context_type="webhook", platform="telegram"),
    RouteRule("/agents/api/v1/webhook/whatsapp/*", auth_required=False, context_type="webhook", platform="whatsapp"),
    RouteRule("/agents/api/v1/payments/webhook/*", skip=True),
    
    # Публичные endpoints без авторизации
    RouteRule("/", auth_required=False, context_type="anonymous"),  # Landing page
    RouteRule("/agents/api/v1/lead", auth_required=False, context_type="anonymous"),
    RouteRule("/frontend/auth", auth_required=False, context_type="anonymous"),
    RouteRule("/frontend/chat/embed*", auth_required=False, context_type="anonymous"),
    RouteRule("/auth/*", auth_required=False, context_type="anonymous"),
    RouteRule("/docs*", auth_required=False, context_type="anonymous"),
    RouteRule("/api/docs", auth_required=False, context_type="anonymous"),
    RouteRule("/api/redoc", auth_required=False, context_type="anonymous"),
    RouteRule("/api/openapi.json", auth_required=False, context_type="anonymous"),
    RouteRule("/privacy", auth_required=False, context_type="anonymous"),
    RouteRule("/terms", auth_required=False, context_type="anonymous"),
    
    # Страницы без привязки к компании (но с авторизацией)
    RouteRule("/frontend/select-company", context_type="frontend", auth_required=True),
    RouteRule("/frontend/create-company", context_type="frontend", auth_required=True),
    RouteRule("/frontend/api/admin/create-my-company", context_type="frontend", auth_required=True),
    RouteRule("/frontend/models/create_company_form/*", context_type="frontend", auth_required=True),
    
    # Frontend - требует авторизации и субдомена
    RouteRule("/frontend/api/*", context_type="frontend", auth_required=True),
    RouteRule("/frontend/*", context_type="frontend", auth_required=True),
    
    # RAG UI - отдельный интерфейс, требует авторизации
    RouteRule("/rag/*", context_type="frontend", auth_required=True),
    RouteRule("/rag", context_type="frontend", auth_required=True),
    
    # API - авторизация через токен
    RouteRule("/agents/api/v1/files/download/*", context_type="api", auth_required=False),
    RouteRule("/agents/api/v1/*", context_type="api", auth_required=True),
    
    # CRM API
    RouteRule("/crm/api/v1/*", context_type="api", auth_required=True),
    RouteRule("/crm/health", auth_required=False, context_type="anonymous"),
    
    # AmoCRM integration
    RouteRule("/api/amocrm*", context_type="amocrm", auth_required=False),
    
    # Root
    RouteRule("/", auth_required=False, context_type="anonymous"),
]

# Страницы где разрешен доступ без субдомена (select-company, create-company)
NO_SUBDOMAIN_ALLOWED_PATHS = [
    "/frontend/select-company",
    "/frontend/create-company",
    "/frontend/api/admin/create-my-company",
    "/frontend/api/admin/me",
    "/frontend/api/admin/companies",
    "/frontend/api/admin/companies/*",
    "/frontend/api/admin/company/*",
    "/frontend/models/create_company_form/*",
]

# Страницы доступные для удаляемой компании
DELETING_COMPANY_ALLOWED_PATHS = [
    "/frontend/select-company",
    "/frontend/create-company",
    "/auth/logout",
    "/frontend/api/admin/*",
]


class RouteMatcher:
    """Матчер маршрутов"""
    
    def __init__(self, rules: List[RouteRule] = None, skip_paths: List[str] = None):
        self.rules = rules or ROUTE_RULES
        self.skip_paths = skip_paths or SKIP_PATHS
    
    def should_skip(self, path: str) -> bool:
        """Проверяет, нужно ли пропустить middleware для пути"""
        return any(fnmatch.fnmatch(path, pattern) for pattern in self.skip_paths)
    
    def match(self, path: str) -> Optional[RouteRule]:
        """Находит подходящее правило для пути"""
        for rule in self.rules:
            if fnmatch.fnmatch(path, rule.pattern):
                return rule
        return None
    
    def allows_no_subdomain(self, path: str) -> bool:
        """Проверяет, разрешен ли доступ без субдомена"""
        return any(fnmatch.fnmatch(path, pattern) for pattern in NO_SUBDOMAIN_ALLOWED_PATHS)
    
    def allows_deleting_company(self, path: str) -> bool:
        """Проверяет, разрешен ли доступ для удаляемой компании"""
        return any(fnmatch.fnmatch(path, pattern) for pattern in DELETING_COMPANY_ALLOWED_PATHS)

