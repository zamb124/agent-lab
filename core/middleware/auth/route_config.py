"""
Декларативная конфигурация маршрутов для AuthMiddleware.
"""

import fnmatch
from dataclasses import dataclass
from typing import Optional, List


@dataclass
class RouteRule:
    """Правило маршрутизации"""
    
    pattern: str
    skip: bool = False
    auth_required: bool = True
    context_type: str = "frontend"
    channel: Optional[str] = None


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
    # ============================================================================
    # ПУБЛИЧНЫЕ ENDPOINTS (без авторизации)
    # ============================================================================
    
    # Главная страница
    RouteRule("/", auth_required=False, context_type="anonymous"),
    
    # Страницы продуктов (публичный доступ)
    RouteRule("/products/*", auth_required=False, context_type="anonymous"),
    
    # Статические файлы
    RouteRule("/static/*", auth_required=False, context_type="anonymous"),
    RouteRule("/assets/*", auth_required=False, context_type="anonymous"),
    RouteRule("/src/*", auth_required=False, context_type="anonymous"),
    RouteRule("/media/*", auth_required=False, context_type="anonymous"),
    RouteRule("/favicon.ico", auth_required=False, context_type="anonymous"),
    
    # PWA файлы (должны быть доступны публично)
    RouteRule("/manifest.json", auth_required=False, context_type="anonymous"),
    RouteRule("/sw.js", auth_required=False, context_type="anonymous"),
    RouteRule("/offline.html", auth_required=False, context_type="anonymous"),
    
    # Эндпоинты OAuth (с префиксами сервисов и без)
    RouteRule("/api/auth/login/*", auth_required=False, context_type="anonymous"),
    RouteRule("/api/auth/callback", auth_required=False, context_type="anonymous"),
    RouteRule("/api/auth/logout", auth_required=False, context_type="anonymous"),
    RouteRule("/*/api/auth/login/*", auth_required=False, context_type="anonymous"),
    RouteRule("/*/api/auth/callback", auth_required=False, context_type="anonymous"),
    RouteRule("/*/api/auth/logout", auth_required=False, context_type="anonymous"),
    
    # Публичные API
    RouteRule("/api/leads", auth_required=False, context_type="anonymous"),
    RouteRule("/frontend/api/leads", auth_required=False, context_type="anonymous"),
    RouteRule("/api/i18n/*", auth_required=False, context_type="anonymous"),
    RouteRule("/api/health", auth_required=False, context_type="anonymous"),
    
    # Документация
    RouteRule("/docs*", auth_required=False, context_type="anonymous"),
    RouteRule("/redoc", auth_required=False, context_type="anonymous"),
    RouteRule("/openapi.json", auth_required=False, context_type="anonymous"),
    
    # Вебхуки (без JWT, используют свою аутентификацию)
    RouteRule("/agents/api/v1/webhook/telegram/*", auth_required=False, context_type="webhook", channel="telegram"),
    RouteRule("/agents/api/v1/webhook/whatsapp/*", auth_required=False, context_type="webhook", channel="whatsapp"),
    RouteRule("/agents/api/v1/payments/webhook/*", skip=True),
    
    # API для встраивания - публичный доступ для встраиваемых виджетов
    RouteRule("/agents/api/v1/embed/*", auth_required=False, context_type="anonymous"),
    
    # ============================================================================
    # АВТОРИЗАЦИЯ ТРЕБУЕТСЯ, НО СУБДОМЕН НЕ ОБЯЗАТЕЛЕН
    # ============================================================================
    
    # Управление компаниями (пользователь авторизован, но ещё не выбрал компанию)
    RouteRule("/select-company", context_type="frontend", auth_required=True),
    RouteRule("/api/companies/check-slug", context_type="frontend", auth_required=True),
    RouteRule("/api/companies/me", context_type="frontend", auth_required=True),
    RouteRule("/api/companies", context_type="frontend", auth_required=True),
    RouteRule("/frontend/api/companies/check-slug", context_type="frontend", auth_required=True),
    RouteRule("/frontend/api/companies/me", context_type="frontend", auth_required=True),
    RouteRule("/frontend/api/companies", context_type="frontend", auth_required=True),
    
    # API фронтенда для управления конфигурациями виджетов
    RouteRule("/frontend/api/embed/configs/*", context_type="api", auth_required=True),
    RouteRule("/frontend/api/embed/configs", context_type="api", auth_required=True),
    
    # API фронтенда для управления командой
    RouteRule("/api/team/*", context_type="api", auth_required=True),
    RouteRule("/frontend/api/team/*", context_type="api", auth_required=True),
    
    # API фронтенда для управления API ключами
    RouteRule("/api/api-keys/*", context_type="api", auth_required=True),
    RouteRule("/api/api-keys", context_type="api", auth_required=True),
    RouteRule("/frontend/api/api-keys/*", context_type="api", auth_required=True),
    RouteRule("/frontend/api/api-keys", context_type="api", auth_required=True),
    
    # API фронтенда для биллинга
    RouteRule("/api/billing/*", context_type="api", auth_required=True),
    RouteRule("/frontend/api/billing/*", context_type="api", auth_required=True),
    
    # API фронтенда для настроек
    RouteRule("/api/settings/*", context_type="api", auth_required=True),
    RouteRule("/frontend/api/settings/*", context_type="api", auth_required=True),
    
    # Push Notifications API (публичный ключ без авторизации, подписка с авторизацией)
    RouteRule("/api/push/vapid-public-key", context_type="anonymous", auth_required=False),
    RouteRule("/frontend/api/push/vapid-public-key", context_type="anonymous", auth_required=False),
    RouteRule("/*/api/push/vapid-public-key", context_type="anonymous", auth_required=False),
    RouteRule("/api/push/*", context_type="api", auth_required=True),
    RouteRule("/frontend/api/push/*", context_type="api", auth_required=True),
    RouteRule("/*/api/push/*", context_type="api", auth_required=True),
    
    # API фронтенда для статуса сервисов (публичный доступ для мониторинга)
    RouteRule("/api/services/status", context_type="anonymous", auth_required=False),
    RouteRule("/frontend/api/services/status", context_type="anonymous", auth_required=False),
    
    # Универсальный эндпоинт информации о пользователе (доступен на всех сервисах)
    RouteRule("/api/auth/me", context_type="api", auth_required=True),
    RouteRule("/*/api/auth/me", context_type="api", auth_required=True),
    RouteRule("/*/api/auth/me/*", context_type="api", auth_required=True),
    
    # ============================================================================
    # ТРЕБУЕТСЯ АВТОРИЗАЦИЯ И СУБДОМЕН (компания)
    # ============================================================================
    
    # Панель управления - главная страница после авторизации
    RouteRule("/dashboard", context_type="frontend", auth_required=True),
    
    # Страницы консоли фронтенда
    RouteRule("/team", context_type="frontend", auth_required=True),
    RouteRule("/api-keys", context_type="frontend", auth_required=True),
    RouteRule("/billing", context_type="frontend", auth_required=True),
    RouteRule("/embed-configs", context_type="frontend", auth_required=True),
    RouteRule("/settings/*", context_type="frontend", auth_required=True),
    RouteRule("/settings", context_type="frontend", auth_required=True),
    
    # UI агентов - статика без авторизации (должна быть перед /agents/ui/*)
    RouteRule("/agents/ui/static/*", auth_required=False, context_type="anonymous"),
    
    # UI агентов - страницы (требуют авторизацию)
    RouteRule("/agents/ui/*", context_type="frontend", auth_required=True),
    RouteRule("/agents/ui", context_type="frontend", auth_required=True),
    RouteRule("/agents", context_type="frontend", auth_required=True),
    
    # API агентов (новый путь)
    RouteRule("/agents/v1/auth/me", context_type="api", auth_required=True),
    RouteRule("/agents/v1/files/download/*", context_type="api", auth_required=False),
    RouteRule("/agents/v1/*", context_type="api", auth_required=True),
    
    # API агентов (устаревший путь /api/v1)
    RouteRule("/agents/api/v1/auth/me", context_type="api", auth_required=True),
    RouteRule("/agents/api/v1/files/download/*", context_type="api", auth_required=False),
    RouteRule("/agents/api/v1/*", context_type="api", auth_required=True),
    
    # Эндпоинты протокола A2A (выполнение агента без префикса /api/)
    RouteRule("/agents/*", context_type="a2a", auth_required=True),
    
    # CRM (если используется)
    RouteRule("/crm/api/v1/*", context_type="api", auth_required=True),
    RouteRule("/crm/*", context_type="frontend", auth_required=True),
    RouteRule("/crm", context_type="frontend", auth_required=True),
    
    # RAG Service - требует авторизацию для tenant isolation
    RouteRule("/rag/ui/static/*", auth_required=False, context_type="anonymous"),
    RouteRule("/rag/api/v1/*", context_type="session", auth_required=True),
    RouteRule("/rag/ui/*", context_type="anonymous", auth_required=False),
    RouteRule("/rag/ui", context_type="anonymous", auth_required=False),
    RouteRule("/rag", context_type="frontend", auth_required=True),
    RouteRule("/rag/", context_type="frontend", auth_required=True),
]

# Страницы где разрешен доступ без субдомена
NO_SUBDOMAIN_ALLOWED_PATHS = [
    "/select-company",
    "/api/companies/check-slug",
    "/api/companies/me",
    "/api/companies",
    "/api/auth/me",
    "/*/api/auth/me",
    "/*/api/auth/me/*",
    "/frontend/api/companies/check-slug",
    "/frontend/api/companies/me",
    "/frontend/api/companies",
    "/*/test",  # E2E тестовые страницы (TESTING mode only)
]

# Страницы доступные для удаляемой компании
DELETING_COMPANY_ALLOWED_PATHS = [
    "/select-company",
    "/auth/logout",
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
