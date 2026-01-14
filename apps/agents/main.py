"""
Главный файл приложения agents.
"""

import asyncio
from pathlib import Path
import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from core.app import create_service_app
from core.tracing.middleware import TracingMiddleware
from core.context import set_context, clear_context
from core.models.context_models import Context, Language
from core.models.identity_models import User, Company
from apps.agents.src.api import a2a_router, chat_router, registry_router, websocket_router
from apps.agents.src.api.v1 import api_v1_router
from apps.agents.src.api.embed import router as embed_router
from apps.agents.config import AgentSettings, get_settings
from apps.agents.src.container import get_container
from apps.agents.src.services.agents_loader import load_flows_to_db, load_tools_to_db
from core.logging import get_logger

logger = get_logger(__name__)


async def on_startup(app: FastAPI, container, settings: AgentSettings):
    """Кастомная логика при запуске сервиса agents"""
    
    # Подключаемся к Redis с retry
    logger.info("Connecting to Redis...")
    max_startup_retries = 5
    for attempt in range(max_startup_retries):
        try:
            await container.redis_client.connect()
            logger.info("Redis connected")
            break
        except Exception as e:
            if attempt < max_startup_retries - 1:
                wait = 2 ** attempt
                logger.warning(f"Redis connection failed (attempt {attempt+1}), retry in {wait}s: {e}")
                await asyncio.sleep(wait)
            else:
                logger.error("Failed to connect to Redis on startup")
                raise
    
    # Создаем системный контекст
    system_context = Context(
        user=User(user_id="system", name="System", groups=["admin"]),
        host="system",
        session_id="system-startup",
        channel="system",
        language=Language.RU,
        active_company=Company(
            company_id="system", 
            name="System", 
            subdomain="system"
        ),
        user_companies=[],
        trace_id="system:startup",
    )
    set_context(system_context)
    
    try:
        # Сначала загружаем tools синхронно (нужны для агентов)
        loaded_tools = await load_tools_to_db(container.tool_repository)
        logger.info(f"Загружено tools: {loaded_tools}")
        
        # В тестах загружаем агенты СИНХРОННО (worker может быть не готов)
        if os.getenv("TESTING") == "true":
            logger.info("🔄 Загрузка агентов синхронно (TESTING=true)...")
            from apps.agents.src.services.agents_loader import load_flows_to_db
            loaded_agents = await load_flows_to_db(
                container.agent_repository,
                container.node_repository,
                container.tool_repository
            )
            logger.info(f"✅ Загружено агентов: {loaded_agents}")
        else:
            # Запускаем фоновую миграцию агентов в system через TaskIQ
            # НЕ ЖДЕМ завершения - сервис стартует сразу
            from apps.agents.src.tasks.company_init_tasks import init_company_resources
            
            task = await init_company_resources.kiq(
                company_id="system",
                company_name="System",
                subdomain="system"
            )
            
            logger.info(
                f"🚀 Фоновая миграция агентов в system запущена: task_id={task.task_id}"
            )
            logger.info(
                "⚠️  Агенты будут доступны после завершения миграции"
            )
        
    except Exception as e:
        logger.error(f"Ошибка запуска миграции в system: {e}", exc_info=True)
        # НЕ падаем - миграцию можно запустить вручную
    finally:
        clear_context()

    # Синхронизация LLM моделей от провайдера
    if os.getenv("TESTING") != "true":
        try:
            synced_count = await container.llm_models_service.sync_models()
            logger.info(f"Синхронизировано LLM моделей: {synced_count}")
            # Запуск фоновой синхронизации каждые 60 секунд
            await container.llm_models_service.start_background_sync(interval=60)
        except Exception as e:
            logger.error(f"Ошибка при синхронизации LLM моделей: {e}")
    else:
        logger.info("⏭️  Пропускаем синхронизацию LLM моделей (TESTING=true)")


async def on_shutdown(app: FastAPI, container):
    """Кастомная логика при остановке сервиса agents"""
    
    # Остановка фоновой синхронизации моделей
    await container.llm_models_service.stop_background_sync()
    
    # Закрываем Redis с error handling
    try:
        await container.redis_client.close()
        logger.info("Redis disconnected")
    except Exception as e:
        logger.error(f"Error closing Redis: {e}")


app = create_service_app(
    service_name="agents",
    settings_class=AgentSettings,
    get_container=get_container,
    routers=[
        api_v1_router,
        registry_router,
        chat_router,
        websocket_router,
        a2a_router,
        embed_router,
    ],
    repository_names=["agent_repository", "node_repository", "tool_repository"],
    on_startup=on_startup,
    on_shutdown=on_shutdown,
    extra_middlewares=[
        (SessionMiddleware, {
            "secret_key": get_settings().auth.jwt_secret_key or "dev-secret-key-change-in-production",
            "session_cookie": "platform_session",
            "same_site": "lax",
            "https_only": False,
        }),
        (TracingMiddleware, {}),
    ],
    cors_origins=["*"],
    api_version="v1",
    title="Agent Platform",
    description="Agent Platform - платформа агентских систем",
    version="2.0.0",
)

# Документация (статические файлы mkdocs)
docs_path = Path(__file__).parent / "site"
if docs_path.exists():
    app.mount("/documentation", StaticFiles(directory=docs_path, html=True), name="documentation")

# Статические файлы для чата
static_path = Path(__file__).parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=static_path), name="static")

# Core frontend библиотека (общая для всех сервисов)
core_frontend_path = Path(__file__).parent.parent.parent / "core" / "frontend" / "static"
if core_frontend_path.exists():
    app.mount("/static/core", StaticFiles(directory=core_frontend_path), name="core_frontend")
    logger.info(f"Core frontend библиотека смонтирована: {core_frontend_path}")

# UI - статические файлы
ui_path = Path(__file__).parent / "ui"
if ui_path.exists():
    app.mount("/agents/static", StaticFiles(directory=ui_path), name="ui_static")


@app.get("/")
async def root():
    """Редирект на UI"""
    return RedirectResponse(url="/agents/example_react", status_code=302)


@app.get("/ui")
@app.get("/ui/{agent_id:path}")
async def old_ui_redirect(agent_id: str = "example_react"):
    """Редирект со старых путей /ui на новые /agents"""
    return RedirectResponse(url=f"/agents/{agent_id}", status_code=301)


@app.get("/agents/ui")
@app.get("/agents/ui/{agent_id:path}")
async def old_agents_ui_redirect(agent_id: str = "example_react"):
    """Редирект со старых путей /agents/ui на новые /agents"""
    return RedirectResponse(url=f"/agents/{agent_id}", status_code=301)


@app.get("/agents", response_class=HTMLResponse)
@app.get("/agents/", response_class=HTMLResponse)
@app.get("/agents/{agent_id}", response_class=HTMLResponse)
async def ui_agent(request: Request, agent_id: str = "example_react"):
    """SPA страница для агента"""
    # Пропускаем API пути
    if agent_id.startswith("api/") or agent_id.startswith("static/"):
        raise HTTPException(status_code=404, detail="Not found")
    
    ui_templates = Jinja2Templates(directory=ui_path)
    base_url = f"{request.base_url.scheme}://{request.base_url.netloc}"
    return ui_templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "agent_id": agent_id,
            "agent_name": agent_id,
            "base_url": base_url,
        }
    )


@app.get("/manifest.json")
async def manifest():
    """PWA Web App Manifest"""
    return FileResponse(
        Path(__file__).parent / "static" / "manifest.json",
        media_type="application/manifest+json"
    )


@app.get("/sw.js")
async def service_worker():
    """Service Worker - должен быть в корне для правильного scope"""
    return FileResponse(
        Path(__file__).parent / "static" / "sw.js",
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"}
    )


if __name__ == "__main__":
    try:
        import uvicorn
    except ImportError:
        raise RuntimeError("uvicorn не установлен. Установите: pip install uvicorn")

    settings = get_settings()
    uvicorn.run(
        "apps.agents.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.server.debug,
    )
