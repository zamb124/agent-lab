"""
Декларативная конфигурация маршрутов для AuthMiddleware.
"""

import fnmatch
from dataclasses import dataclass
from typing import Optional, List

from starlette.requests import Request

# Префиксы, для которых нельзя подменять ответ SPA (API и служебные пути)
SPA_FALLBACK_EXCLUDED_PREFIXES: tuple[str, ...] = (
    "/api/",
    "/l/",
    "/flows/",
    "/crm/",
    "/rag/",
    "/sync/",
    "/documents/",
    "/frontend/",
    "/static/",
    "/assets/",
    "/src/",
    "/media/",
    "/debug/",
    "/.well-known/",
)

SPA_FALLBACK_EXCLUDED_EXACT: frozenset[str] = frozenset(
    {
        "/health",
        "/openapi.json",
        "/redoc",
        "/documentation",
        "/favicon.ico",
    }
)


def path_allows_spa_fallback(path: str) -> bool:
    """Путь без явного правила: можно отдать HTML SPA, если это не API/служебный префикс."""
    if path in SPA_FALLBACK_EXCLUDED_EXACT:
        return False
    for prefix in SPA_FALLBACK_EXCLUDED_PREFIXES:
        if path.startswith(prefix):
            return False
    return True


def browser_request_allows_spa_fallback(request: Request) -> bool:
    """
    Браузерная навигация (document) или явный Accept: text/html.
    Исключает типичные API-клиенты с Accept: application/json.
    """
    if request.method not in ("GET", "HEAD"):
        return False
    if request.headers.get("sec-fetch-dest") == "document":
        return True
    accept = request.headers.get("accept", "")
    if "text/html" in accept.lower():
        return True
    return False


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
    "/apple-touch-icon.png",
    "/apple-touch-icon-precomposed.png",
    "/health",
    "/flows/health",
    "/crm/health",
    "/debug/*",
    "/api/v1/payments/webhook/*",
    "/frontend/api/v1/payments/webhook/*",
]

ROUTE_RULES: List[RouteRule] = [
    # ============================================================================
    # ПУБЛИЧНЫЕ ENDPOINTS (без авторизации)
    # ============================================================================
    
    # Главная страница
    RouteRule("/", auth_required=False, context_type="anonymous"),
    RouteRule("/policy", auth_required=False, context_type="anonymous"),
    RouteRule("/terms", auth_required=False, context_type="anonymous"),
    # Страница входа (redirect после истечения сессии: redirectToAuth() на apex-домене)
    RouteRule("/login", auth_required=False, context_type="anonymous"),
    RouteRule("/frontend/login", auth_required=False, context_type="anonymous"),
    RouteRule("/l/*", auth_required=False, context_type="anonymous"),
    
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
    RouteRule("/auth/login/*", auth_required=False, context_type="anonymous"),
    RouteRule("/auth/callback/*", auth_required=False, context_type="anonymous"),
    RouteRule("/auth/logout", auth_required=False, context_type="anonymous"),
    RouteRule("/*/api/auth/login/*", auth_required=False, context_type="anonymous"),
    RouteRule("/*/api/auth/callback", auth_required=False, context_type="anonymous"),
    RouteRule("/*/api/auth/logout", auth_required=False, context_type="anonymous"),
    RouteRule("/*/api/v1/integrations/oauth/callback", auth_required=False, context_type="anonymous"),
    RouteRule("/api/auth/demo/status", auth_required=False, context_type="anonymous"),
    RouteRule("/frontend/api/auth/demo/status", auth_required=False, context_type="anonymous"),
    RouteRule("/*/api/auth/demo/status", auth_required=False, context_type="anonymous"),
    
    # Публичные API
    RouteRule("/api/leads", auth_required=False, context_type="anonymous"),
    RouteRule("/frontend/api/leads", auth_required=False, context_type="anonymous"),
    RouteRule("/api/i18n/*", auth_required=False, context_type="anonymous"),
    RouteRule("/api/public/legal", auth_required=False, context_type="anonymous"),
    RouteRule("/frontend/api/public/legal", auth_required=False, context_type="anonymous"),
    RouteRule("/api/health", auth_required=False, context_type="anonymous"),
    RouteRule("/api/platform/file-types", auth_required=False, context_type="anonymous"),
    
    # Документация
    RouteRule("/docs*", auth_required=False, context_type="anonymous"),
    RouteRule("/documentation*", auth_required=False, context_type="anonymous"),
    RouteRule("/frontend/documentation*", auth_required=False, context_type="anonymous"),
    RouteRule("/redoc", auth_required=False, context_type="anonymous"),
    RouteRule("/openapi.json", auth_required=False, context_type="anonymous"),

    # Вебхуки (без JWT, используют свою аутентификацию)
    RouteRule("/flows/api/v1/webhook/telegram/*", auth_required=False, context_type="webhook", channel="telegram"),
    RouteRule("/flows/api/v1/webhook/whatsapp/*", auth_required=False, context_type="webhook", channel="whatsapp"),
    RouteRule("/api/v1/payments/webhook/*", skip=True),
    RouteRule("/frontend/api/v1/payments/webhook/*", skip=True),

    # YooMoney OAuth callback (redirect из браузера после авторизации на yoomoney.ru)
    RouteRule("/api/billing/yoomoney/callback", auth_required=False, context_type="anonymous"),
    RouteRule("/frontend/api/billing/yoomoney/callback", auth_required=False, context_type="anonymous"),
    
    # API для встраивания - публичный доступ для встраиваемых виджетов
    RouteRule("/flows/api/v1/embed/*", auth_required=False, context_type="anonymous"),
    
    # ============================================================================
    # АВТОРИЗАЦИЯ ТРЕБУЕТСЯ, НО СУБДОМЕН НЕ ОБЯЗАТЕЛЕН
    # ============================================================================
    
    # Страница принятия инвайта — публичная (JS сам проверяет авторизацию)
    RouteRule("/join", auth_required=False, context_type="anonymous"),

    # Управление компаниями (пользователь авторизован, но ещё не выбрал компанию)
    RouteRule("/select-company", context_type="frontend", auth_required=True),
    RouteRule("/api/companies/check-slug", context_type="frontend", auth_required=True),
    RouteRule("/api/companies/me", context_type="frontend", auth_required=True),
    RouteRule("/api/companies", context_type="frontend", auth_required=True),
    RouteRule("/*/api/companies/me", context_type="frontend", auth_required=True),
    RouteRule("/*/api/companies", context_type="frontend", auth_required=True),
    RouteRule("/frontend/api/companies/check-slug", context_type="frontend", auth_required=True),
    RouteRule("/frontend/api/companies/me", context_type="frontend", auth_required=True),
    RouteRule("/frontend/api/companies", context_type="frontend", auth_required=True),
    
    # API фронтенда для управления конфигурациями виджетов
    RouteRule("/frontend/api/embed/configs/*", context_type="api", auth_required=True),
    RouteRule("/frontend/api/embed/configs", context_type="api", auth_required=True),
    
    # Принятие инвайта (auth, но без субдомена — пользователь ещё может не иметь компании)
    RouteRule("/api/invites/accept", context_type="frontend", auth_required=True),
    RouteRule("/frontend/api/invites/accept", context_type="frontend", auth_required=True),
    # Генерация инвайта (auth + субдомен — только owner/admin действующей компании)
    RouteRule("/api/invites/*", context_type="api", auth_required=True),
    RouteRule("/frontend/api/invites/*", context_type="api", auth_required=True),

    # Core team API на всех сервисах
    RouteRule("/api/team/*", context_type="api", auth_required=True),
    RouteRule("/*/api/team/*", context_type="api", auth_required=True),
    
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

    # API фронтенда для управления scheduler задачами
    RouteRule("/api/scheduler/*", context_type="api", auth_required=True),
    RouteRule("/frontend/api/scheduler/*", context_type="api", auth_required=True),

    # Заявки с лендинга (список; доступ system проверяется в обработчике)
    RouteRule("/api/lead-requests", context_type="api", auth_required=True),
    RouteRule("/frontend/api/lead-requests", context_type="api", auth_required=True),

    # Админ трейсинг (доступ system проверяется в обработчике)
    RouteRule("/api/platform-tracing/*", context_type="api", auth_required=True),
    RouteRule("/frontend/api/platform-tracing/*", context_type="api", auth_required=True),

    # Админ тарифы и usage (доступ system проверяется в обработчике)
    RouteRule("/api/platform-billing/*", context_type="api", auth_required=True),
    RouteRule("/frontend/api/platform-billing/*", context_type="api", auth_required=True),
    
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

    # Core calendar API на всех сервисах
    RouteRule("/api/calendar/*", context_type="api", auth_required=True),
    RouteRule("/*/api/calendar/*", context_type="api", auth_required=True),
    
    # Универсальный эндпоинт информации о пользователе (доступен на всех сервисах)
    RouteRule("/api/auth/me", context_type="api", auth_required=True),
    RouteRule("/api/auth/me/*", context_type="api", auth_required=True),
    # Остальные core auth без префикса сервиса (после /api/auth/me — см. /login выше)
    RouteRule("/api/auth/*", context_type="api", auth_required=True),
    RouteRule("/auth/me", context_type="api", auth_required=True),
    RouteRule("/auth/me/*", context_type="api", auth_required=True),
    RouteRule("/*/api/auth/me", context_type="api", auth_required=True),
    RouteRule("/*/api/auth/me/*", context_type="api", auth_required=True),
    # Остальные core auth endpoints (/providers, /attrs/..., switch-company) на всех сервисах
    RouteRule("/*/api/auth/*", context_type="api", auth_required=True),
    
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
    RouteRule("/scheduler-tasks", context_type="frontend", auth_required=True),
    RouteRule("/lead-requests", context_type="frontend", auth_required=True),
    RouteRule("/platform-tracing", context_type="frontend", auth_required=True),
    RouteRule("/platform-billing", context_type="frontend", auth_required=True),

    # Те же страницы консоли, если путь приходит с префиксом сервиса (/frontend/...).
    # Иначе refresh даёт 404: префикс /frontend/ исключён из анонимного SPA-fallback.
    RouteRule("/frontend/dashboard", context_type="frontend", auth_required=True),
    RouteRule("/frontend/team", context_type="frontend", auth_required=True),
    RouteRule("/frontend/api-keys", context_type="frontend", auth_required=True),
    RouteRule("/frontend/billing", context_type="frontend", auth_required=True),
    RouteRule("/frontend/embed-configs", context_type="frontend", auth_required=True),
    RouteRule("/frontend/settings/*", context_type="frontend", auth_required=True),
    RouteRule("/frontend/settings", context_type="frontend", auth_required=True),
    RouteRule("/frontend/scheduler-tasks", context_type="frontend", auth_required=True),
    RouteRule("/frontend/lead-requests", context_type="frontend", auth_required=True),
    RouteRule("/frontend/platform-tracing", context_type="frontend", auth_required=True),
    RouteRule("/frontend/platform-billing", context_type="frontend", auth_required=True),

    # Scheduler service API
    RouteRule("/scheduler/api/v1/*", context_type="api", auth_required=True),
    
    # UI агентов - статика без авторизации (должна быть перед /flows/ui/*)
    RouteRule("/flows/ui/static/*", auth_required=False, context_type="anonymous"),
    RouteRule("/ui/static/*", auth_required=False, context_type="anonymous"),
    
    # UI агентов - страницы (требуют авторизацию)
    RouteRule("/flows/ui/*", context_type="frontend", auth_required=True),
    RouteRule("/flows/ui", context_type="frontend", auth_required=True),
    RouteRule("/flows", context_type="frontend", auth_required=True),
    # Прямой доступ на порт сервиса (без nginx-префикса /agents)
    RouteRule("/ui/*", context_type="frontend", auth_required=True),
    RouteRule("/ui", context_type="frontend", auth_required=True),
    
    # Скачивание файлов — публичный доступ для всех сервисов;
    # приватные файлы проверяются самим хендлером по company_id
    RouteRule("*/api/v1/files/download/*", context_type="api", auth_required=False),
    RouteRule("*/v1/files/download/*", context_type="api", auth_required=False),
    # Остальные файловые эндпоинты требуют авторизацию.
    RouteRule("*/api/v1/files/*", context_type="api", auth_required=True),
    RouteRule("*/api/v1/files", context_type="api", auth_required=True),
    RouteRule("*/v1/files/*", context_type="api", auth_required=True),
    RouteRule("*/v1/files", context_type="api", auth_required=True),

    # API агентов (новый путь)
    RouteRule("/flows/v1/auth/me", context_type="api", auth_required=True),
    RouteRule("/flows/v1/*", context_type="api", auth_required=True),

    # API агентов (устаревший путь /api/v1)
    RouteRule("/flows/api/v1/auth/me", context_type="api", auth_required=True),
    RouteRule("/flows/api/v1/*", context_type="api", auth_required=True),
    
    # Эндпоинты протокола A2A (выполнение агента без префикса /api/)
    RouteRule("/flows/*", context_type="a2a", auth_required=True),
    
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

    # Sync Service
    # Статика и SPA-оболочка — public; checkAuth() на стороне JS → redirectToAuth()
    RouteRule("/sync/ui/static/*", auth_required=False, context_type="anonymous"),
    # Публичные эндпоинты звонков (join по ссылке — работает и для гостей без auth)
    RouteRule("/sync/api/v1/calls/join/*", auth_required=False, context_type="anonymous"),
    # API и WS — защищены на сервере
    RouteRule("/sync/api/v1/*", context_type="api", auth_required=True),
    RouteRule("/sync/api/auth/*", context_type="api", auth_required=True),
    RouteRule("/sync/api/push/vapid-public-key", context_type="anonymous", auth_required=False),
    RouteRule("/sync/api/push/*", context_type="api", auth_required=True),
    # /sync/ws — auth внутри хендлера через get_user_from_websocket()
    RouteRule("/sync/ws", auth_required=False, context_type="anonymous"),
    RouteRule("/sync/ws/*", auth_required=False, context_type="anonymous"),
    # SPA catch-all — public, чтобы JS мог загрузиться и сделать redirect сам
    RouteRule("/sync", auth_required=False, context_type="anonymous"),
    RouteRule("/sync/", auth_required=False, context_type="anonymous"),
    RouteRule("/sync/*", auth_required=False, context_type="anonymous"),

    # LitServe Service
    RouteRule("/litserve/ui/static/*", auth_required=False, context_type="anonymous"),
    RouteRule("/litserve/api/*", context_type="api", auth_required=True),
    RouteRule("/litserve", auth_required=False, context_type="anonymous"),
    RouteRule("/litserve/", auth_required=False, context_type="anonymous"),
    RouteRule("/litserve/*", auth_required=False, context_type="anonymous"),
    # OpenAI-совместимые эндпоинты живут в корне хоста и авторизуются на уровне handler/dependency.
    RouteRule("/v1/*", auth_required=False, context_type="anonymous"),

    # Documents (apps/office): BFF + Lit shell; OnlyOffice дергает download/callback по JWT в query / Bearer
    RouteRule("/documents/ui/static/*", auth_required=False, context_type="anonymous"),
    RouteRule("/documents/api/v1/office-download", auth_required=False, context_type="anonymous"),
    RouteRule("/documents/api/v1/onlyoffice/callback", auth_required=False, context_type="anonymous"),
    RouteRule("/documents/api/v1/*", context_type="session", auth_required=True),
    RouteRule("/documents", auth_required=False, context_type="anonymous"),
    RouteRule("/documents/", auth_required=False, context_type="anonymous"),
    RouteRule("/documents/*", auth_required=False, context_type="anonymous"),
]

# Страницы где разрешен доступ без субдомена
NO_SUBDOMAIN_ALLOWED_PATHS = [
    "/select-company",
    "/join",
    "/l/*",
    "/api/companies/check-slug",
    "/api/companies/me",
    "/api/companies",
    "/api/auth/me",
    "/api/auth/me/*",
    "/auth/me",
    "/auth/me/*",
    "/*/api/auth/me",
    "/*/api/auth/me/*",
    "/frontend/api/companies/check-slug",
    "/frontend/api/companies/me",
    "/frontend/api/companies",
    "/api/invites/accept",
    "/frontend/api/invites/accept",
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
