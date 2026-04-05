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

import logging
import os
from pathlib import Path
from typing import Type, Callable, List, Optional, Any, Tuple
from contextlib import asynccontextmanager

from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from pydantic_settings import BaseSettings as PydanticBaseSettings


from core.config.loader import load_merged_config
from core.config import set_settings
from core.app.health_payload import build_health_payload
from core.logging import setup_logging
from core.middleware.auth import AuthMiddleware
from core.middleware.deployment_headers import DeploymentHeadersMiddleware
from core.middleware.dev_inter_service_proxy import DevInterServiceProxyMiddleware
from core.tracing import setup_tracing
from core.tracing.tracer import set_span_repository, set_tracing_service_name
from core.websocket.manager import notification_manager
from core.websocket.router import router as ws_router
from core.api.auth import router as core_auth_router
from core.api.calendar import router as core_calendar_router
from core.api.companies import router as core_companies_router
from core.api.team import router as core_team_router
from core.push.router import router as push_router
from core.push.apns_credentials import resolve_apns_credentials
from core.push.apns_service import init_apns_push_service
from core.push.service import init_web_push_service
from core.app.pwa_routes import register_platform_pwa_routes
from core.app.i18n_routes import register_platform_i18n_routes

logger = logging.getLogger(__name__)


def load_service_settings(
    service_name: str,
    settings_class: Type[PydanticBaseSettings]
) -> Tuple[Any, Path]:
    """
    Загружает настройки сервиса.
    
    Returns:
        (settings, project_root)
    """
    project_root = Path(__file__).parent.parent.parent

    merged_config = load_merged_config(service_name=service_name)
    
    settings = settings_class(**merged_config)
    set_settings(settings)
    
    return settings, project_root


def create_service_app(
    service_name: str,
    settings_class: Type[PydanticBaseSettings],
    get_container: Callable,
    routers: List[APIRouter] = None,
    pages_routers: List[APIRouter] = None,
    repository_names: List[str] = None,
    on_startup: Optional[Callable] = None,
    on_shutdown: Optional[Callable] = None,
    cors_origins: List[str] = None,
    extra_middlewares: List[Tuple[type, dict]] = None,
    static_mounts: List[Tuple[str, str, str]] = None,
    extra_state: dict = None,
    title: str = None,
    description: str = None,
    version: str = "1.0.0",
    api_version: str = "v1",  # None - без /api/, "v1" - /api/v1
    docs_url: str = "/docs",
    redoc_url: str = "/redoc",
    openapi_url: str = "/openapi.json",
    include_auth_middleware: bool = True,
    include_crud_routers: bool = True,
    mount_repo_mkdocs: bool = True,
    mkdocs_gateway_prefix: Optional[str] = None,
    include_platform_pwa: Optional[bool] = None,
) -> FastAPI:
    """
    Создает FastAPI приложение для сервиса.
    
    Args:
        service_name: Имя сервиса (например, "flows")
        settings_class: Класс настроек (наследник BaseSettings)
        get_container: Функция получения контейнера
        routers: Список API роутеров (prefix зависит от api_version)
        pages_routers: Список page роутеров (без prefix - они имеют свой)
        repository_names: Имена репозиториев для CRUD роутеров
        on_startup: Функция вызываемая при старте (async)
        on_shutdown: Функция вызываемая при остановке (async)
        cors_origins: Разрешенные origins для CORS
        extra_middlewares: Дополнительные middleware [(MiddlewareClass, {kwargs}), ...]
        static_mounts: Статические директории [(path, directory, name), ...]
        api_version: Версия API ("v1" для flows и др., None для frontend)
        docs_url, redoc_url, openapi_url: Пути для документации
        include_auth_middleware: Включать ли AuthMiddleware
        include_crud_routers: Включать ли автоматические CRUD роутеры
        mount_repo_mkdocs: Смонтировать MkDocs из корня репозитория ``site/`` на ``/documentation/`` (False для flows со своим ``apps/flows/site``).
        mkdocs_gateway_prefix: Если задан (например ``frontend``), дублировать документацию на ``/{prefix}/documentation/`` за ingress.
        include_platform_pwa: Маршруты ``/manifest.json``, ``/sw.js``, ``/offline.html``. None: выключено при ``TESTING=true``, иначе включено.
        
    Returns:
        Настроенное FastAPI приложение
    """
    
    # Загрузка конфигурации
    settings, project_root = load_service_settings(service_name, settings_class)
    
    # Настройка логирования
    setup_logging(service_name, settings.logging)
    
    # Получение контейнера
    container = get_container()
    
    # Lifespan
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info(f"Запуск {service_name} Service...")
        
        # Инициализация трейсинга
        if settings.tracing.enabled:
            setup_tracing(settings.tracing)
            if settings.tracing.postgres_enabled:
                if not settings.database.tracing_url:
                    raise ValueError(
                        "tracing.postgres_enabled требует database.tracing_url (DATABASE__TRACING_URL)"
                    )
                set_tracing_service_name(settings.server.name)
                set_span_repository(container.span_repository)
            logger.info("Трейсинг инициализирован")
        
        # Redis pub/sub listener для WebSocket уведомлений
        await notification_manager.start_redis_listener(settings.database.redis_url)
        logger.info("Notification manager запущен")
        
        # Инициализация глобального BillingService
        from core.billing import set_billing_service
        set_billing_service(container.billing_service)
        logger.info("BillingService инициализирован")
        
        # Инициализация WebPushService
        if settings.push.enabled:
            init_web_push_service(
                vapid_private_key=settings.push.vapid_private_key,
                vapid_public_key=settings.push.vapid_public_key,
                vapid_email=settings.push.vapid_email,
            )
            logger.info("WebPushService инициализирован")

        apns = resolve_apns_credentials(settings)
        if apns:
            init_apns_push_service(
                team_id=apns.team_id,
                key_id=apns.key_id,
                private_key_pem=apns.private_key_pem,
                bundle_id=apns.bundle_id,
                use_sandbox=apns.use_sandbox,
            )
            logger.info("ApnsPushService инициализирован")
        
        # Кастомный startup
        if on_startup:
            await on_startup(app, container, settings)
        
        logger.info(f"{service_name} Service запущен")
        
        yield
        
        logger.info(f"Остановка {service_name} Service...")
        
        # Кастомный shutdown
        if on_shutdown:
            await on_shutdown(app, container)
        
        # В одном процессе pytest поднимается несколько приложений (flows, office, rag, sync);
        # stop_redis_listener обнуляет глобальный клиент и ломает notify_user в чужих тестах.
        if os.environ.get("TESTING") != "true":
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
    
    # Дополнительные атрибуты state
    if extra_state:
        for key, value in extra_state.items():
            setattr(app.state, key, value)
    
    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Proxy headers
    app.add_middleware(
        ProxyHeadersMiddleware,
        trusted_hosts=["*"]
    )
    
    # Auth middleware
    if include_auth_middleware:
        app.add_middleware(AuthMiddleware)
    
    # Дополнительные middleware
    if extra_middlewares:
        for middleware_class, kwargs in extra_middlewares:
            app.add_middleware(middleware_class, **kwargs)

    app.add_middleware(DeploymentHeadersMiddleware)

    # Локальный dev/test: браузер на :8002 с путём /flows/... без ingress — пересылаем на flows_service_url
    app.add_middleware(DevInterServiceProxyMiddleware, service_name=settings.server.name)

    # API prefix
    # api_version="v1" → /flows/api/v1 (REST API)
    # api_version=None → /frontend (сайт без /api/)
    if api_version:
        api_prefix = f"/{settings.server.name}/api/{api_version}"
    else:
        api_prefix = f"/{settings.server.name}"
    logger.info(f"API prefix: {api_prefix}")
    
    # Инициализация репозиториев для CRUD роутеров
    if repository_names:
        for repo_name in repository_names:
            _ = getattr(container, repo_name)
    
    # CRUD роутеры
    if include_crud_routers:
        crud_routers = container.get_crud_routers()
        logger.info(f"Найдено {len(crud_routers)} CRUD роутеров")
        for router in crud_routers:
            app.include_router(router, prefix=api_prefix)
    
    # API роутеры (с prefix /service_name/api/v1)
    if routers:
        for router in routers:
            tags = router.tags or [service_name]
            app.include_router(router, prefix=api_prefix, tags=tags)

    # Файловый роутер (upload/download/metadata) — единообразный контракт для всех сервисов.
    # Даже когда S3 выключен, upload должен отвечать 503, а не 404.
    files_api_prefix = f"/{settings.server.name}/api/{api_version or 'v1'}"
    from core.files.api import build_file_api_router
    _file_router = build_file_api_router(
        get_file_repo=lambda: container.file_repository,
        service_api_prefix=files_api_prefix,
    )
    app.include_router(_file_router, prefix=f"{files_api_prefix}/files")
    logger.info(f"Файловый роутер подключён: {files_api_prefix}/files")

    public_segment = settings.server.name

    # Core auth роутер (автоматически для всех сервисов)
    auth_prefix = f"/{public_segment}/api/auth"
    logger.info(f"Подключение core auth роутера ({auth_prefix}/*)")
    app.include_router(core_auth_router, prefix=auth_prefix, tags=["auth"])
    if service_name == "frontend":
        logger.info("Подключение core auth роутера (/auth/*) для единого OAuth callback")
        app.include_router(core_auth_router, prefix="/auth", tags=["auth"])

    calendar_prefix = f"/{public_segment}/api/calendar"
    logger.info(f"Подключение core calendar роутера ({calendar_prefix}/*)")
    app.include_router(core_calendar_router, prefix=calendar_prefix, tags=["calendar"])

    team_prefix = f"/{public_segment}/api/team"
    logger.info(f"Подключение core team роутера ({team_prefix}/*)")
    app.include_router(core_team_router, prefix=team_prefix, tags=["team"])

    if service_name != "frontend":
        companies_prefix = f"/{public_segment}/api/companies"
        logger.info(f"Подключение core companies роутера ({companies_prefix}/*)")
        app.include_router(core_companies_router, prefix=companies_prefix, tags=["companies"])
    
    # Push notifications роутер (автоматически для всех сервисов)
    push_prefix = f"/{public_segment}"
    logger.info(f"Подключение push роутера ({push_prefix}/api/push/*)")
    app.include_router(push_router, prefix=push_prefix, tags=["push"])
    
    # WebSocket роутер для уведомлений (автоматически для всех сервисов)
    # Монтируем с префиксом сервиса для правильного роутинга через nginx
    ws_path = f"/{public_segment}/ws/notifications" if service_name != "core" else "/ws/notifications"
    logger.info(f"Подключение WebSocket роутера для уведомлений ({ws_path})")
    app.include_router(ws_router, prefix=f"/{public_segment}" if service_name != "core" else "", tags=["websocket"])
    
    # Pages роутеры (добавляем префикс сервиса к их собственному префиксу)
    if pages_routers:
        for router in pages_routers:
            tags = router.tags or [f"{service_name}-pages"]
            # Добавляем только префикс публичного пути (server.name), FastAPI сам добавит его к prefix роутера
            if hasattr(router, 'prefix') and router.prefix:
                app.include_router(router, prefix=f"/{public_segment}", tags=tags)
            else:
                # Роутер без префикса подключается как есть
                app.include_router(router, tags=tags)
    
    # Статические файлы
    if static_mounts:
        for mount_path, directory, name in static_mounts:
            if Path(directory).exists():
                app.mount(mount_path, StaticFiles(directory=directory), name=name)

    if mount_repo_mkdocs:
        from core.frontend.mkdocs_mount import mount_mkdocs_documentation

        mount_mkdocs_documentation(
            app,
            project_root,
            gateway_prefix=mkdocs_gateway_prefix,
        )

    if include_platform_pwa is None:
        include_platform_pwa = os.getenv("TESTING", "false").lower() != "true"

    if include_platform_pwa:
        register_platform_pwa_routes(app, project_root)
        logger.info("PWA: /manifest.json, /sw.js, /offline.html")

    register_platform_i18n_routes(app, project_root)
    logger.info("I18n: GET /api/i18n/{locale}")

    # Health endpoints
    @app.get("/health")
    @app.get(f"/{service_name}/health")
    async def health():
        return build_health_payload(settings)
    
    @app.get("/")
    async def root():
        return {
            "service": settings.server.name,
            "version": version,
            "status": "running"
        }
    
    # Testing endpoint (ТОЛЬКО в TESTING режиме)
    if os.getenv("TESTING", "false").lower() == "true":
        @app.get(f"/{service_name}/test", response_class=HTMLResponse)
        async def test_page():
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
        
        logger.info(f"✅ Test endpoint enabled: /{service_name}/test (TESTING mode)")
    
    logger.info(f"{service_name} Service создан")
    
    return app
