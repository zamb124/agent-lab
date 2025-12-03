"""
Фабрика для создания FastAPI приложений.

Базовая функция create_service_app упрощает создание новых сервисов:
- Загрузка конфигурации
- Настройка middleware
- Регистрация CRUD роутеров из контейнера
- Настройка lifespan

Пример использования:
    from core.app import create_service_app
    
    app = create_service_app(
        service_name="agents",
        settings_class=AgentsSettings,
        get_container=get_agents_container,
        routers=[agents_router, flows_router],
        on_startup=my_startup_func
    )
"""

import logging
from pathlib import Path
from typing import Type, Callable, List, Optional, Any, Tuple
from contextlib import asynccontextmanager

from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from pydantic_settings import BaseSettings as PydanticBaseSettings

from core.config.loader import load_merged_config
from core.config import set_settings
from core.db import create_tables
from core.logging import setup_logging
from core.middleware.auth import AuthMiddleware
from core.tasks.broker import broker
from core.websocket import websocket_manager

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
    service_config_path = project_root / "apps" / service_name / "conf.json"
    
    merged_config = load_merged_config(
        base_config_path=project_root / "conf.json",
        service_config_path=service_config_path
    )
    
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
    create_tables_config: Optional[dict] = None,
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
    include_broker: bool = True,
) -> FastAPI:
    """
    Создает FastAPI приложение для сервиса.
    
    Args:
        service_name: Имя сервиса (например, "agents")
        settings_class: Класс настроек (наследник BaseSettings)
        get_container: Функция получения контейнера
        routers: Список API роутеров (prefix зависит от api_version)
        pages_routers: Список page роутеров (без prefix - они имеют свой)
        repository_names: Имена репозиториев для CRUD роутеров
        on_startup: Функция вызываемая при старте (async)
        on_shutdown: Функция вызываемая при остановке (async)
        create_tables_config: Конфиг для создания таблиц {"service": [...], "shared": [...]}
        cors_origins: Разрешенные origins для CORS
        extra_middlewares: Дополнительные middleware [(MiddlewareClass, {kwargs}), ...]
        static_mounts: Статические директории [(path, directory, name), ...]
        api_version: Версия API ("v1" для agents, None для frontend)
        docs_url, redoc_url, openapi_url: Пути для документации
        include_auth_middleware: Включать ли AuthMiddleware
        include_crud_routers: Включать ли автоматические CRUD роутеры
        include_broker: Включать ли TaskIQ broker
        
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
        
        if create_tables_config:
            if "service" in create_tables_config:
                logger.info("Создание таблиц в service БД...")
                await create_tables(
                    db_url=container.db_url,
                    table_names=create_tables_config["service"]
                )
            
            if "shared" in create_tables_config and container.shared_db_url:
                logger.info("Создание таблиц в shared БД...")
                await create_tables(
                    db_url=container.shared_db_url,
                    table_names=create_tables_config["shared"]
                )
        
        if include_broker:
            await broker.startup()
            logger.info("TaskIQ broker подключен")
        
        # Redis pub/sub listener для WebSocket нотификаций из воркеров
        await websocket_manager.start_redis_listener()
        logger.info("Redis pub/sub listener запущен")
        
        # Кастомный startup
        if on_startup:
            await on_startup(app, container, settings)
        
        logger.info(f"{service_name} Service запущен")
        
        yield
        
        logger.info(f"Остановка {service_name} Service...")
        
        # Кастомный shutdown
        if on_shutdown:
            await on_shutdown(app, container)
        
        # Остановка Redis listener
        await websocket_manager.stop_redis_listener()
        
        if include_broker:
            await broker.shutdown()
    
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
    # api_version="v1" → /agents/api/v1 (REST API)
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
    
    # Pages роутеры (без дополнительного prefix - они уже имеют свой)
    if pages_routers:
        for router in pages_routers:
            tags = router.tags or [f"{service_name}-pages"]
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
    
    logger.info(f"{service_name} Service создан")
    
    return app
