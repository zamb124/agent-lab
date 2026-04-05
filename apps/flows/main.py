"""
Точка входа FastAPI для сервиса flows.
"""

import asyncio
from pathlib import Path
import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from core.app import create_service_app
from core.context import set_context, clear_context
from core.identity.system_bootstrap import (
    SYSTEM_ADMIN_EMAIL,
    ensure_system_admin_membership,
)
from core.models.context_models import Context, Language
from core.models.identity_models import User, Company
from core.utils.tokens import get_token_service
from apps.flows.src.api import a2a_router, chat_router, registry_router, websocket_router
from apps.flows.src.api.v1 import api_v1_router
from apps.flows.src.api.embed import router as embed_router
from apps.flows.config import FlowSettings, get_settings
from apps.flows.src.container import get_container
from apps.flows.src.services.flows_loader import load_flows_to_db, load_tools_to_db
from core.logging import get_logger

logger = get_logger(__name__)


async def _build_scheduler_auth_context(container: object, trace_id: str, session_id: str) -> Context:
    company, user = await ensure_system_admin_membership(container)
    if user is None:
        raise ValueError(
            f"Нет пользователя с email {SYSTEM_ADMIN_EMAIL}: контекст для фоновых задач не собрать"
        )
    roles = user.companies.get(company.company_id, [])
    auth_token = get_token_service().create_token(
        user_id=user.user_id,
        company_id=company.company_id,
        roles=roles,
    )
    return Context(
        user=User(user_id=user.user_id, name=user.name or user.user_id, groups=user.groups),
        host="system",
        session_id=session_id,
        channel="system",
        language=Language.RU,
        active_company=Company(company_id=company.company_id, name=company.name, subdomain=company.subdomain),
        user_companies=[],
        trace_id=trace_id,
        auth_token=auth_token,
    )


async def on_startup(app: FastAPI, container, settings: FlowSettings):
    """Логика при старте сервиса flows."""
    from core.files.writer import FileWriter

    FileWriter.configure_process_upload(
        file_processor=container.file_processor,
        download_url_prefix=f"/{settings.server.name}/api/v1/files/download",
    )

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
        # Сначала загружаем tools синхронно (нужны для flows)
        loaded_tools = await load_tools_to_db(container.tool_repository)
        logger.info(f"Загружено tools: {loaded_tools}")
        
        # В тестах загружаем bundles (flows) в БД синхронно (worker может быть не готов)
        if os.getenv("TESTING") == "true":
            logger.info("Загрузка flows из bundles синхронно (TESTING=true)...")
            from apps.flows.src.services.flows_loader import load_flows_to_db
            loaded_flow_ids = await load_flows_to_db(
                container.flow_repository,
                container.node_repository,
                container.tool_repository
            )
            logger.info(f"Загружено flows: {loaded_flow_ids}")
        else:
            # Фоновая загрузка bundles в company system через TaskIQ (не блокирует старт)
            from apps.flows.src.tasks.company_init_tasks import init_company_resources
            
            task = await init_company_resources.kiq(
                company_id="system",
                company_name="System",
                subdomain="system"
            )
            
            logger.info(
                f"Фоновая инициализация flows для system запущена: task_id={task.task_id}"
            )
            logger.info(
                "Flows из bundles будут доступны после завершения задачи"
            )
        
    except Exception as e:
        logger.error(f"Ошибка запуска миграции в system: {e}", exc_info=True)
        # НЕ падаем - миграцию можно запустить вручную
    finally:
        clear_context()

    # Синхронизация LLM моделей от провайдера
    if os.getenv("TESTING") != "true":
        try:
            scheduler_context = await _build_scheduler_auth_context(
                container=container,
                trace_id="system:scheduler-sync",
                session_id="system-scheduler-sync",
            )
            set_context(scheduler_context)
            synced_count = await container.llm_models_service.sync_models()
            logger.info(f"Синхронизировано LLM моделей: {synced_count}")
            # Запуск фоновой синхронизации каждые 60 секунд
            await container.llm_models_service.start_background_sync(interval=60)
        except Exception as e:
            logger.error(f"Ошибка при синхронизации LLM моделей: {e}")
        finally:
            clear_context()
    else:
        logger.info("Пропускаем синхронизацию LLM моделей (TESTING=true)")
        from core.clients.llm.factory import get_llm
        from core.clients.llm.mock import configure_mock_llm_redis

        get_llm("mock-gpt-4")
        configure_mock_llm_redis(container.redis_client)
        logger.info("MockLLM: очередь ответов из Redis (как в TaskIQ worker)")

    # Telegram Dev Polling (только в development)
    if settings.server.env == "development" and os.getenv("TESTING") != "true":
        from apps.flows.src.triggers.dev_polling import start_dev_polling
        await start_dev_polling()
        logger.info("Telegram dev polling запущен")


async def on_shutdown(app: FastAPI, container):
    """Логика при остановке сервиса flows."""
    
    # Остановка Telegram dev polling
    try:
        from apps.flows.src.triggers.dev_polling import stop_dev_polling
        await stop_dev_polling()
    except Exception as e:
        logger.warning(f"Error stopping dev polling: {e}")
    
    # Остановка фоновой синхронизации моделей
    if os.getenv("TESTING") != "true":
        try:
            scheduler_context = await _build_scheduler_auth_context(
                container=container,
                trace_id="system:scheduler-stop",
                session_id="system-scheduler-stop",
            )
            set_context(scheduler_context)
            await container.llm_models_service.stop_background_sync()
        finally:
            clear_context()
    
    # Закрываем Redis с error handling
    try:
        await container.redis_client.close()
        logger.info("Redis disconnected")
    except Exception as e:
        logger.error(f"Error closing Redis: {e}")


app = create_service_app(
    service_name="flows",
    settings_class=FlowSettings,
    get_container=get_container,
    routers=[
        api_v1_router,
        registry_router,
        chat_router,
        websocket_router,
        a2a_router,
        embed_router,
    ],
    repository_names=["flow_repository", "node_repository", "tool_repository"],
    on_startup=on_startup,
    on_shutdown=on_shutdown,
    extra_middlewares=[
        (SessionMiddleware, {
            "secret_key": get_settings().auth.jwt_secret_key or "dev-secret-key-change-in-production",
            "session_cookie": "platform_session",
            "same_site": "lax",
            "https_only": False,
        }),
    ],
    cors_origins=["*"],
    api_version="v1",
    title="Humanitec Flows",
    description="Сервис flows: конфигурации, runtime и A2A",
    version="2.0.0",
    mount_repo_mkdocs=False,
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
    app.mount("/flows/static", StaticFiles(directory=ui_path), name="ui_static")


@app.get("/")
async def root():
    """Редирект на UI"""
    return RedirectResponse(url="/flows/example_react", status_code=302)


@app.get("/ui")
@app.get("/ui/{flow_id:path}")
async def old_ui_redirect(flow_id: str = "example_react"):
    """Редирект со старых путей /ui на /flows/{flow_id}"""
    return RedirectResponse(url=f"/flows/{flow_id}", status_code=301)


@app.get("/flows/ui")
@app.get("/flows/ui/{flow_id:path}")
async def old_flows_ui_redirect(flow_id: str = "example_react"):
    """Редирект со старых путей /flows/ui на /flows/{flow_id}"""
    return RedirectResponse(url=f"/flows/{flow_id}", status_code=301)


@app.get("/flows", response_class=HTMLResponse)
@app.get("/flows/", response_class=HTMLResponse)
@app.get("/flows/{flow_id}", response_class=HTMLResponse)
async def ui_flow(request: Request, flow_id: str = "example_react"):
    """SPA редактора и просмотра flow."""
    # Пропускаем API пути
    if flow_id.startswith("api/") or flow_id.startswith("static/"):
        raise HTTPException(status_code=404, detail="Not found")
    
    ui_templates = Jinja2Templates(directory=ui_path)
    base_url = f"{request.base_url.scheme}://{request.base_url.netloc}"
    return ui_templates.TemplateResponse(
        request,
        "index.html",
        {
            "flow_id": flow_id,
            "flow_name": flow_id,
            "base_url": base_url,
        },
    )


if __name__ == "__main__":
    try:
        import uvicorn
    except ImportError:
        raise RuntimeError("uvicorn не установлен. Установите: pip install uvicorn")

    settings = get_settings()
    uvicorn.run(
        "apps.flows.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.server.debug,
    )
