"""
Фабрика для создания FastAPI приложений.

Базовая функция create_service_app упрощает создание новых сервисов:
- Загрузка конфигурации
- Настройка middleware
- Регистрация CRUD роутеров из контейнера
- Настройка lifespan

Пример использования:
    from core.app import create_service_app
    from apps.flows.config import FlowSettings
    from apps.flows.src.container import get_container

    app = create_service_app(
        service_name="flows",
        settings_class=FlowSettings,
        get_container=get_container,
        routers=[api_v1_router, registry_router],
        on_startup=my_startup_func,
    )
"""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TypeVar

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from core.api.auth import router as core_auth_router
from core.api.calendar import router as core_calendar_router
from core.api.companies import router as core_companies_router
from core.api.integrations import router as core_integrations_router
from core.api.team import router as core_team_router
from core.app.file_types_route import register_platform_file_types_route
from core.app.health_payload import build_health_payload
from core.app.i18n_routes import register_platform_i18n_routes
from core.app.pwa_routes import register_platform_pwa_routes
from core.billing import set_billing_service
from core.billing.cbr_rate_provider import refresh_loop_coro as _cbr_loop_coro
from core.billing.cbr_rate_provider import refresh_rate_once as _cbr_refresh_once
from core.billing.exceptions import BillingBalanceBlockedError
from core.config import BaseSettings as PlatformBaseSettings
from core.config import set_settings
from core.config.loader import get_project_root, load_merged_config
from core.config.testing import is_testing
from core.container.base import BaseContainer
from core.files.api import build_file_api_router
from core.files.processors import initialize_default_processors
from core.frontend.documentation_mount import mount_documentation_static
from core.logging import (
    SystemLogScope,
    get_logger,
)
from core.logging.setup import setup_logging
from core.middleware.access_log import AccessLogMiddleware
from core.middleware.auth import AuthMiddleware
from core.middleware.deployment_headers import DeploymentHeadersMiddleware
from core.middleware.dev_inter_service_proxy import (
    DevInterServiceProxyMiddleware,
    DevInterServiceWsProxyMiddleware,
)
from core.middleware.platform_error_envelope import PlatformHttpErrorEnvelopeMiddleware
from core.push.apns_credentials import resolve_apns_credentials
from core.push.apns_service import init_apns_push_service
from core.push.fcm_credentials import resolve_fcm_credentials
from core.push.fcm_service import init_fcm_push_service
from core.push.router import router as push_router
from core.push.service import init_web_push_service
from core.tracing import setup_tracing
from core.tracing.tracer import set_span_repository, set_tracing_service_name
from core.types import JsonObject, JsonValue
from core.utils.background import run_with_log_context
from core.websocket.manager import notification_manager
from core.websocket.router import router as ws_router

logger = get_logger(__name__)

SettingsT = TypeVar("SettingsT", bound=PlatformBaseSettings)
ContainerT = TypeVar("ContainerT", bound=BaseContainer)
ServiceStartupHook = Callable[[FastAPI, ContainerT, SettingsT], Awaitable[None]]
ServiceShutdownHook = Callable[[FastAPI, ContainerT], Awaitable[None]]


def load_service_settings(
    service_name: str, settings_class: type[SettingsT]
) -> tuple[SettingsT, Path]:
    """
    Загружает настройки сервиса (merge без логов до setup_logging).

    Вызов set_settings(settings) — ответственность create_service_app после
    setup_logging.

    Returns:
        (settings, project_root)
    """
    project_root = get_project_root()

    merged_config = load_merged_config(service_name=service_name, silent=True)

    settings = settings_class.model_validate(merged_config)

    return settings, project_root


def create_service_app(
    service_name: str,
    settings_class: type[SettingsT],
    get_container: Callable[[], ContainerT],
    routers: list[APIRouter] | None = None,
    pages_routers: list[APIRouter] | None = None,
    on_startup: ServiceStartupHook[ContainerT, SettingsT] | None = None,
    on_shutdown: ServiceShutdownHook[ContainerT] | None = None,
    cors_origins: list[str] | None = None,
    cors_allow_origin_regex: str | None = None,
    extra_middlewares: Sequence[tuple[type, Mapping[str, JsonValue]]] | None = None,
    static_mounts: list[tuple[str, str, str]] | None = None,
    title: str | None = None,
    description: str | None = None,
    version: str = "1.0.0",
    api_version: str | None = "v1",  # None - без /api/, "v1" - /api/v1
    docs_url: str = "/docs",
    redoc_url: str = "/redoc",
    openapi_url: str = "/openapi.json",
    include_auth_middleware: bool = True,
    include_crud_routers: bool = True,
    include_tracing_lifecycle: bool | None = None,
    include_platform_lifecycle: bool = True,
    include_platform_routers: bool = True,
    mount_repo_documentation: bool = True,
    documentation_gateway_prefix: str | None = None,
    include_platform_pwa: bool | None = None,
    services_spa_index: Path | None = None,
) -> FastAPI:
    """
    Создает FastAPI приложение для сервиса.

    Args:
        service_name: Имя сервиса (например, "flows")
        settings_class: Класс настроек (наследник BaseSettings)
        get_container: Функция получения контейнера
        routers: Список API роутеров (prefix зависит от api_version)
        pages_routers: Список page роутеров (без prefix - они имеют свой)
        on_startup: Функция вызываемая при старте (async)
        on_shutdown: Функция вызываемая при остановке (async)
        cors_origins: Разрешенные origins для CORS (конкретные URL; с credentials нельзя звёздочку как единственный origin)
        cors_allow_origin_regex: Regex для Origin (Starlette CORSMiddleware), суммируется с allow_origins
        extra_middlewares: Дополнительные middleware [(MiddlewareClass, {kwargs}), ...]
        static_mounts: Статические директории [(path, directory, name), ...]
        api_version: Версия API ("v1" для flows и др., None для frontend)
        docs_url, redoc_url, openapi_url: Пути для документации
        include_auth_middleware: Включать ли AuthMiddleware
        include_crud_routers: Включать ли автоматические CRUD роутеры
        include_tracing_lifecycle: Включать ли tracing startup hooks. None — вместе с include_platform_lifecycle.
        include_platform_lifecycle: Включать ли Redis/billing/push startup hooks
        include_platform_routers: Включать ли общие платформенные роутеры (files/auth/calendar/ws/i18n)
        mount_repo_documentation: Смонтировать статическую документацию (Zensical) из корня репозитория ``documentation-dist/`` на ``/documentation/`` (False для flows со своим ``apps/flows/site``).
        documentation_gateway_prefix: Если задан (например ``documents`` для office), первый сегмент публичных путей HTTP API и платформенных роутеров (team, ws, auth, …); плюс дублирование документации на ``/{prefix}/documentation/`` за ingress.
        include_platform_pwa: Маршруты ``/manifest.json``, ``/sw.js``, ``/offline.html``. None: выключено при ``TESTING=true``, иначе включено.
        services_spa_index: Путь к ``index.html`` SPA; если файл существует, регистрируются
            ``GET /{public_segment}/services`` и ``GET /{public_segment}/services/`` с тем же HTML.

    Returns:
        Настроенное FastAPI приложение
    """

    tracing_lifecycle_enabled = (
        include_platform_lifecycle if include_tracing_lifecycle is None else include_tracing_lifecycle
    )

    # Загрузка конфигурации (silent: без записей до setup_logging)
    settings, project_root = load_service_settings(service_name, settings_class)

    # Настройка логирования и публикация settings в глобальный синглтон
    setup_logging(service_name, settings.logging)
    set_settings(settings)

    # Получение контейнера
    container = get_container()

    # Lifespan: системный скоуп — нет request_id/user_id, но нужен canonical service.name
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with SystemLogScope(lifecycle_phase="startup"):
            await _run_startup(app)
            yield
        async with SystemLogScope(lifecycle_phase="shutdown"):
            await _run_shutdown(app)

    async def _run_startup(app: FastAPI) -> None:
        logger.info("service.starting", service=service_name)

        # Инициализация трейсинга отделена от полного platform lifecycle: lightweight
        # sandbox services должны писать spans, но не поднимать Redis/billing/push.
        if tracing_lifecycle_enabled and settings.tracing.enabled:
            setup_tracing(settings.tracing)
            if settings.tracing.postgres_enabled:
                if not settings.database.tracing_url:
                    raise ValueError(
                        "tracing.postgres_enabled требует database.tracing_url (DATABASE__TRACING_URL)"
                    )
                set_tracing_service_name(service_name)
                set_span_repository(container.span_repository)
            logger.info("Трейсинг инициализирован")

        if include_platform_lifecycle:

            # Redis pub/sub listener для WebSocket уведомлений
            await notification_manager.start_redis_listener(settings.database.redis_url)
            logger.info("Notification manager запущен")

            # Инициализация глобального BillingService
            set_billing_service(container.billing_service)
            logger.info("BillingService инициализирован")

            # Инициализация курса USD/RUB от ЦБ РФ: один запрос при старте,
            # затем фоновое обновление каждые 5 минут.
            # Fallback при недоступности ЦБ — billing.usd_to_rub_rate из конфига.
            _cbr_fallback = settings.billing.usd_to_rub_rate
            if is_testing():
                logger.info(
                    "billing.cbr_rate.skipped_testing",
                    fallback=_cbr_fallback,
                )
            else:
                await _cbr_refresh_once(fallback=_cbr_fallback)
                _ = run_with_log_context(
                    _cbr_loop_coro(fallback=_cbr_fallback),
                    name="billing.cbr_rate_refresh",
                    background_kind="startup",
                )
                logger.info("billing.cbr_rate.loop_scheduled")

            if hasattr(container, "file_repository"):
                initialize_default_processors(container.file_repository)
                logger.info(
                    "initialize_default_processors: FileReader может грузить файлы по file_id / S3"
                )

            # Инициализация WebPushService
            if settings.push.enabled:
                if not settings.push.vapid_private_key or not settings.push.vapid_public_key:
                    raise ValueError(
                        "push.enabled=true требует push.vapid_private_key и push.vapid_public_key"
                    )
                _ = init_web_push_service(
                    vapid_private_key=settings.push.vapid_private_key,
                    vapid_public_key=settings.push.vapid_public_key,
                    vapid_email=settings.push.vapid_email,
                )
                logger.info("WebPushService инициализирован")

            apns = resolve_apns_credentials(settings)
            if apns:
                _ = init_apns_push_service(
                    team_id=apns.team_id,
                    key_id=apns.key_id,
                    private_key_pem=apns.private_key_pem,
                    bundle_id=apns.bundle_id,
                    use_sandbox=apns.use_sandbox,
                )
                logger.info("ApnsPushService инициализирован")

            fcm = resolve_fcm_credentials(settings.push)
            if fcm:
                _ = init_fcm_push_service(
                    project_id=fcm.project_id,
                    client_email=fcm.client_email,
                    private_key_pem=fcm.private_key_pem,
                    token_uri=fcm.token_uri,
                )
                logger.info("FcmPushService инициализирован project_id=%s", fcm.project_id)

        # Кастомный startup
        if on_startup:
            await on_startup(app, container, settings)

        logger.info("service.started", service=service_name)

    async def _run_shutdown(app: FastAPI) -> None:
        logger.info("service.stopping", service=service_name)

        if on_shutdown:
            await on_shutdown(app, container)

        # В одном процессе pytest поднимается несколько приложений (flows, office, rag, sync);
        # stop_redis_listener обнуляет глобальный клиент и ломает notify_user в чужих тестах.
        if include_platform_lifecycle and not is_testing():
            await notification_manager.stop_redis_listener()

    # Создание приложения
    app = FastAPI(
        title=title or f"{service_name.title()} Service",
        version=version,
        description=description or f"Сервис {service_name}",
        lifespan=lifespan,
        debug=settings.server.debug,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
    )

    app.state.container = container
    app.state.settings = settings

    @app.exception_handler(BillingBalanceBlockedError)
    async def _billing_balance_blocked_handler(
        _request: Request, exc: BillingBalanceBlockedError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={"detail": str(exc), "code": "billing_balance_blocked"},
        )
    _ = _billing_balance_blocked_handler

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """
        Гарантирует одну structured-запись на каждое необработанное исключение.

        Не глотает: после логирования возвращает 500 JSON. Тело по умолчанию без
        текста исключения (клиент / межсервис). При ``server.debug=True`` добавляется
        ``exception_detail`` (локальная отладка). ``exception_type`` — всегда, имя класса.
        """
        exc_cls = type(exc).__name__
        logger.exception(
            "http_unhandled_exception",
            **{
                "exception.type": exc_cls,
                "http.path": request.url.path,
                "http.method": request.method,
            },
        )
        payload: JsonObject = {
            "detail": "Internal Server Error",
            "code": "internal_error",
            "exception_type": exc_cls,
        }
        if settings.server.debug:
            payload["exception_detail"] = str(exc)[:4096]
        return JSONResponse(status_code=500, content=payload)
    _ = _unhandled_exception_handler

    # CORS собираем здесь, подключаем в конце create_service_app (внешний слой стека).
    # Иначе preflight OPTIONS обрабатывает AuthMiddleware раньше и отдаёт 404 без ACAO.
    cors_allow_origins = list(cors_origins) if cors_origins else []
    cors_allow_methods = ["*"]
    cors_allow_headers = ["*"]
    resolved_cors_allow_origin_regex = (
        cors_allow_origin_regex.strip() if cors_allow_origin_regex and cors_allow_origin_regex.strip() else None
    )

    # Proxy headers
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["*"])

    # Auth middleware (внутренний слой: bind user/company/session, set_context)
    if include_auth_middleware:
        app.add_middleware(AuthMiddleware)

    # Access log (внешний слой: вход в request-скоуп — request_id/trace_id;
    # видит финальный status_code и duration_ms; снимает скоуп в finally).
    app.add_middleware(AccessLogMiddleware, service_name=service_name)

    # Дополнительные middleware
    if extra_middlewares:
        for middleware_class, kwargs in extra_middlewares:
            app.add_middleware(middleware_class, **dict(kwargs))

    app.add_middleware(DeploymentHeadersMiddleware)

    # Локальный dev/test: браузер на :8002 с путём /flows/... без ingress — пересылаем на flows_service_url
    app.add_middleware(DevInterServiceProxyMiddleware, service_name=service_name)
    # Тот же прокси, но для WebSocket-апгрейдов: ASGI-уровневый, BaseHTTPMiddleware WS не покрывает.
    app.add_middleware(DevInterServiceWsProxyMiddleware, service_name=service_name)

    # Наружный слой — обогащение JSON ошибок (последний в цепочке add_middleware).
    app.add_middleware(PlatformHttpErrorEnvelopeMiddleware, service_name=service_name)

    # Первый сегмент публичного URL: обычно совпадает с service_name.
    # Исключение — office (документы): в браузере /documents/..., задаётся
    # documentation_gateway_prefix (см. office.mdc, SERVICE_PUBLIC_NAME в CI).
    url_route_segment = documentation_gateway_prefix or service_name

    # api_version="v1" → /{segment}/api/v1 (REST API)
    # api_version=None → /{segment} (сайт без /api/)
    if api_version:
        api_prefix = f"/{url_route_segment}/api/{api_version}"
    else:
        api_prefix = f"/{url_route_segment}"
    logger.info("service.api_prefix", api_prefix=api_prefix)

    # CRUD роутеры
    if include_crud_routers:
        crud_routers = container.get_crud_routers()
        logger.info("service.crud_routers_loaded", count=len(crud_routers))
        for router in crud_routers:
            app.include_router(router, prefix=api_prefix)

    # API роутеры (с prefix /service_name/api/v1)
    if routers:
        for router in routers:
            tags = router.tags or [service_name]
            app.include_router(router, prefix=api_prefix, tags=tags)

    public_segment = url_route_segment

    if include_platform_routers:
        # Файловый роутер (upload/download/metadata) — единообразный контракт для доменных сервисов.
        files_api_prefix = f"/{url_route_segment}/api/{api_version or 'v1'}"
        _file_router = build_file_api_router(
            get_file_repo=lambda: container.file_repository,
            service_api_prefix=files_api_prefix,
        )
        app.include_router(_file_router, prefix=f"{files_api_prefix}/files")
        logger.info("service.router_attached", router="files", prefix=f"{files_api_prefix}/files")

        auth_prefix = f"/{public_segment}/api/auth"
        logger.info("service.router_attached", router="core_auth", prefix=auth_prefix)
        app.include_router(core_auth_router, prefix=auth_prefix, tags=["auth"])
        if service_name == "frontend":
            logger.info("service.router_attached", router="core_auth_oauth", prefix="/auth")
            app.include_router(core_auth_router, prefix="/auth", tags=["auth"])

        calendar_prefix = f"/{public_segment}/api/calendar"
        logger.info("service.router_attached", router="core_calendar", prefix=calendar_prefix)
        app.include_router(core_calendar_router, prefix=calendar_prefix, tags=["calendar"])

        integrations_prefix = f"/{public_segment}"
        logger.info("service.router_attached", router="core_integrations", prefix=integrations_prefix)
        app.include_router(core_integrations_router, prefix=integrations_prefix, tags=["integrations"])

        team_prefix = f"/{public_segment}/api/team"
        logger.info("service.router_attached", router="core_team", prefix=team_prefix)
        app.include_router(core_team_router, prefix=team_prefix, tags=["team"])

        if service_name == "frontend":
            companies_prefix = "/frontend/api/companies"
        else:
            companies_prefix = f"/{public_segment}/api/companies"
        logger.info("service.router_attached", router="core_companies", prefix=companies_prefix)
        app.include_router(core_companies_router, prefix=companies_prefix, tags=["companies"])

        push_prefix = f"/{public_segment}"
        logger.info("service.router_attached", router="push", prefix=f"{push_prefix}/api/push")
        app.include_router(push_router, prefix=push_prefix, tags=["push"])

        # WebSocket роутер для уведомлений (`/<svc>/api/ws/notifications`).
        ws_prefix = f"/{public_segment}/api" if service_name != "core" else ""
        ws_path = f"{ws_prefix}/ws/notifications" if service_name != "core" else "/ws/notifications"
        logger.info("service.router_attached", router="ws_notifications", path=ws_path)
        app.include_router(ws_router, prefix=ws_prefix, tags=["websocket"])

    # Pages роутеры (добавляем префикс сервиса к их собственному префиксу)
    if pages_routers:
        for router in pages_routers:
            tags = router.tags or [f"{service_name}-pages"]
            # Добавляем только префикс публичного пути (public_segment), FastAPI сам добавит его к prefix роутера
            if hasattr(router, "prefix") and router.prefix:
                app.include_router(router, prefix=f"/{public_segment}", tags=tags)
            else:
                # Роутер без префикса подключается как есть
                app.include_router(router, tags=tags)

    # Статические файлы
    if static_mounts:
        for mount_path, directory, name in static_mounts:
            if Path(directory).exists():
                app.mount(mount_path, StaticFiles(directory=directory), name=name)

    if mount_repo_documentation:
        mount_documentation_static(
            app,
            project_root,
            gateway_prefix=documentation_gateway_prefix,
        )

    if include_platform_pwa is None:
        include_platform_pwa = not is_testing()

    if include_platform_routers and include_platform_pwa:
        register_platform_pwa_routes(app, project_root)
        logger.info("PWA: /manifest.json, /sw.js, /offline.html")

    if include_platform_routers:
        register_platform_i18n_routes(app, project_root)
        logger.info("I18n: GET /api/i18n/{locale}")

        register_platform_file_types_route(app)
        logger.info("FileTypes: GET /api/platform/file-types")

    if services_spa_index is not None and services_spa_index.is_file():
        _services_spa_html = services_spa_index.read_text(encoding="utf-8")

        @app.get(f"/{public_segment}/services", response_class=HTMLResponse)
        @app.get(f"/{public_segment}/services/", response_class=HTMLResponse)
        async def platform_services_spa() -> HTMLResponse:
            return HTMLResponse(content=_services_spa_html)
        _ = platform_services_spa

        logger.info(
            "Platform services SPA: GET /%s/services, /%s/services/ -> %s",
            public_segment,
            public_segment,
            services_spa_index,
        )

    # Health-endpoints
    @app.get("/health")
    @app.get(f"/{service_name}/health")
    async def health() -> dict[str, str]:
        return build_health_payload(settings)
    _ = health

    @app.get("/")
    async def root() -> JsonObject:
        return {"service": service_name, "version": version, "status": "running"}
    _ = root

    # Тестовый endpoint (ТОЛЬКО в TESTING режиме)
    if is_testing():

        @app.get(f"/{service_name}/test", response_class=HTMLResponse)
        async def test_page() -> str:
            """
            Универсальная пустая страница для E2E UI тестов.

            Доступна ТОЛЬКО в TESTING режиме на всех сервисах:
            - CRM: http://localhost:9003/crm/test
            - Frontend: http://localhost:9004/frontend/test
            - Agents: http://localhost:9001/agents/test
            - RAG: http://localhost:9002/rag/test

            Страница пустая для тестирования компонентов

            Предоставляет:
            - importmap для lit (локальные пути /static/core/assets/js/lit/)
            - Доступ к /static/core/* (все core компоненты)
            - Пустой контейнер #test-root
            """
            return """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>E2E Test Page</title>
    <script type="importmap">
    {
        "imports": {
            "lit": "/static/core/assets/js/lit/lit.min.js",
            "lit/decorators.js": "/static/core/assets/js/lit/decorators.min.js",
            "lit/directives/class-map.js": "/static/core/assets/js/lit/directives/class-map.min.js",
            "lit/directives/repeat.js": "/static/core/assets/js/lit/directives/repeat.min.js",
            "lit/directives/unsafe-html.js": "/static/core/assets/js/lit/directives/unsafe-html.min.js",
            "lit/directives/when.js": "/static/core/assets/js/lit/directives/when.min.js",
            "lit/directives/guard.js": "/static/core/assets/js/lit/directives/guard.min.js",
            "@platform/lib/": "/static/core/lib/",
            "@platform/services/": "/static/core/services/"
        }
    }
    </script>
    <style>
        body {
            font-family: system-ui, -apple-system, sans-serif;
            padding: 2rem;
        }
        #test-root {
            min-height: 200px;
        }
    </style>
</head>
<body>
    <div id="test-root"></div>
</body>
</html>"""
        _ = test_page

        logger.info(
            "service.test_endpoint_enabled",
            service=service_name,
            path=f"/{service_name}/test",
        )

    if resolved_cors_allow_origin_regex is None:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_allow_origins,
            allow_credentials=True,
            allow_methods=cors_allow_methods,
            allow_headers=cors_allow_headers,
        )
    else:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_allow_origins,
            allow_credentials=True,
            allow_methods=cors_allow_methods,
            allow_headers=cors_allow_headers,
            allow_origin_regex=resolved_cors_allow_origin_regex,
        )

    logger.info("service.created", service=service_name)

    return app
