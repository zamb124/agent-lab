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
from core.logging import setup_logging
from core.middleware.auth import AuthMiddleware
from core.tracing import setup_tracing
from core.tracing.tracer import set_span_repository
from core.websocket.manager import notification_manager
from core.websocket.router import router as ws_router
from core.api.auth import router as core_auth_router
from core.push.router import router as push_router
from core.push.service import init_web_push_service

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
                vapid_email=settings.push.vapid_email
            )
            logger.info("WebPushService инициализирован")
        
        # Кастомный startup
        if on_startup:
            await on_startup(app, container, settings)
        
        logger.info(f"{service_name} Service запущен")
        
        yield
        
        logger.info(f"Остановка {service_name} Service...")
        
        # Кастомный shutdown
        if on_shutdown:
            await on_shutdown(app, container)
        
        # Остановка notification manager
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

    # Файловый роутер (upload/download/metadata) — добавляется автоматически
    # для всех сервисов с включённым S3 и заданной api_version
    if api_version and settings.s3.enabled:
        from core.files.api import build_file_api_router
        _file_router = build_file_api_router(
            get_file_repo=lambda: container.file_repository,
            service_api_prefix=api_prefix,
        )
        app.include_router(_file_router, prefix=f"{api_prefix}/files")
        logger.info(f"Файловый роутер подключён: {api_prefix}/files")

    # Core auth роутер (автоматически для всех сервисов)
    auth_prefix = f"/{service_name}/api/auth"
    logger.info(f"Подключение core auth роутера ({auth_prefix}/*)")
    app.include_router(core_auth_router, prefix=auth_prefix, tags=["auth"])
    
    # Push notifications роутер (автоматически для всех сервисов)
    push_prefix = f"/{service_name}"
    logger.info(f"Подключение push роутера ({push_prefix}/api/push/*)")
    app.include_router(push_router, prefix=push_prefix, tags=["push"])
    
    # WebSocket роутер для уведомлений (автоматически для всех сервисов)
    # Монтируем с префиксом сервиса для правильного роутинга через nginx
    ws_path = f"/{service_name}/ws/notifications" if service_name != "core" else "/ws/notifications"
    logger.info(f"Подключение WebSocket роутера для уведомлений ({ws_path})")
    app.include_router(ws_router, prefix=f"/{service_name}" if service_name != "core" else "", tags=["websocket"])
    
    # Pages роутеры (добавляем префикс сервиса к их собственному префиксу)
    if pages_routers:
        for router in pages_routers:
            tags = router.tags or [f"{service_name}-pages"]
            # Добавляем только префикс сервиса, FastAPI сам добавит его к prefix роутера
            if hasattr(router, 'prefix') and router.prefix:
                # Если у роутера есть prefix, добавляем только service_name
                app.include_router(router, prefix=f"/{service_name}", tags=tags)
            else:
                # Роутер без префикса подключается как есть
                app.include_router(router, tags=tags)
    
    # Статические файлы
    if static_mounts:
        for mount_path, directory, name in static_mounts:
            if Path(directory).exists():
                app.mount(mount_path, StaticFiles(directory=directory), name=name)
    
    # Health endpoints
    @app.get("/health")
    @app.get(f"/{service_name}/health")
    async def health():
        return {"status": "healthy", "service": settings.server.name}
    
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
            - importmap для lit (CDN)
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
            "lit": "https://cdn.jsdelivr.net/npm/lit@3/+esm",
            "lit/": "https://cdn.jsdelivr.net/npm/lit@3/"
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
