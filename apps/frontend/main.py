"""
Frontend Service - FastAPI приложение для фронтенда.

Порт: 8002
БД: shared_db
"""

import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from core.config.loader import load_merged_config
from core.config import set_settings
from core.logging import setup_logging
from core.middleware.auth import AuthMiddleware
from core.middleware.profiling import ProfilingMiddleware
from core.files import initialize_default_processors
from core.api import auth_router

from apps.frontend.config import FrontendSettings
from apps.frontend.container import get_frontend_container
from apps.frontend.core.htmx_helpers import HTMXHeaderMiddleware
from apps.frontend.core.plugin_loader import discover_and_load_plugins
from apps.frontend.api_router import router as frontend_api_router
from apps.frontend.pages_router import router as frontend_pages_router
from apps.frontend.websockets_router import router as frontend_websockets_router
from apps.frontend.websockets.notifications import router as websocket_notifications_router
from apps.frontend.api import models as frontend_models
from apps.frontend.api.mcp import router as mcp_api_router
from apps.agents.container import get_agents_container
from apps.agents.api.v1.admin import router as admin_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan события для FastAPI"""
    logger.info("Запуск Frontend Service...")
    
    logger.info("Загрузка плагинов...")
    await discover_and_load_plugins(app)
    
    logger.info("Frontend Service запущен")
    
    yield
    
    logger.info("Остановка Frontend Service...")


def create_app() -> FastAPI:
    """Создает FastAPI приложение"""
    
    project_root = Path(__file__).parent.parent.parent
    service_config_path = Path(__file__).parent / "conf.json"
    
    merged_config = load_merged_config(
        base_config_path=project_root / "conf.json",
        service_config_path=service_config_path
    )
    
    settings = FrontendSettings(**merged_config)
    set_settings(settings)
    
    logger.info(f"Frontend config: env={settings.server.env}, port={settings.server.port}")
    
    setup_logging("frontend", settings.logging)
    
    container = get_frontend_container()
    
    initialize_default_processors(
        file_repository=container.file_repository,
        storage=container.storage
    )
    
    app = FastAPI(
        title="Frontend Service",
        version="1.0.0",
        description="Фронтенд сервис с HTMX и плагинной системой",
        lifespan=lifespan,
        debug=settings.server.debug,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )
    
    app.state.container = container
    app.state.settings = settings
    app.state.agents_container = get_agents_container()
    
    app.add_middleware(
        ProxyHeadersMiddleware,
        trusted_hosts=["*"] if settings.server.debug else [settings.server.domain, f"*.{settings.server.domain}"]
    )
    
    app.add_middleware(
        ProfilingMiddleware,
        log_slow_requests=True,
        slow_threshold_ms=500
    )
    
    app.add_middleware(AuthMiddleware)
    
    app.add_middleware(HTMXHeaderMiddleware)
    
    allowed_origins = ["*"] if settings.server.debug else [
        "http://localhost:3000",
        f"https://{settings.server.domain}",
        f"https://*.{settings.server.domain}",
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    @app.middleware("http")
    async def utf8_response_middleware(request: Request, call_next):
        response = await call_next(request)
        if "application/json" in response.headers.get("content-type", ""):
            response.headers["content-type"] = "application/json; charset=utf-8"
        return response
    
    @app.middleware("http")
    async def static_cache_middleware(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            if request.url.path.endswith(('.js', '.css')):
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            else:
                response.headers["Cache-Control"] = "public, max-age=3600"
        return response
    
    logger.info("Подключение роутеров...")
    
    app.include_router(frontend_api_router, prefix="/frontend/api")
    app.include_router(frontend_pages_router)
    app.include_router(frontend_websockets_router, prefix="/frontend")
    app.include_router(websocket_notifications_router, tags=["websocket-notifications"], include_in_schema=False)
    app.include_router(frontend_models.router, tags=["frontend-models-direct"], include_in_schema=False)
    app.include_router(auth_router, prefix="/auth", tags=["auth-callback"])
    app.include_router(admin_router, prefix="/frontend/api/admin", tags=["admin"])
    app.include_router(mcp_api_router, prefix="/frontend/api", tags=["mcp-api"])
    
    logger.info("Монтирование статических файлов...")
    
    frontend_dir = Path(__file__).parent
    
    modules_dir = frontend_dir / "modules"
    for module_path in sorted(modules_dir.iterdir()):
        if module_path.is_dir() and (module_path / "static").exists():
            module_name = module_path.name
            module_static = module_path / "static"
            app.mount(f"/static/{module_name}", StaticFiles(directory=str(module_static)), name=f"static-{module_name}")
    
    pages_dir = frontend_dir / "pages"
    for page_path in sorted(pages_dir.iterdir()):
        if page_path.is_dir() and (page_path / "static").exists():
            page_name = page_path.name
            page_static = page_path / "static"
            app.mount(f"/static/{page_name}", StaticFiles(directory=str(page_static)), name=f"static-{page_name}")
    
    static_dir = frontend_dir / "shared" / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    
    docs_dir = project_root / "site"
    if docs_dir.exists():
        app.mount("/docs", StaticFiles(directory=str(docs_dir), html=True), name="docs")
    
    logger.info("Frontend Service создан")
    
    return app


app = create_app()


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "service": "frontend"}


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "frontend",
        "version": "1.0.0",
        "status": "running"
    }
