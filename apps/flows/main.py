"""
Точка входа FastAPI для сервиса flows.
"""

import asyncio
from pathlib import Path
import os

from core.config.testing import is_testing
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
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
from apps.flows.config import FlowSettings, FLOWS_PUBLIC_API_PREFIX, get_settings
from apps.flows.src.container import get_container
from apps.flows.src.services.flows_loader import load_flows_to_db, load_tools_to_db
from apps.flows.src.middleware.embed_dynamic_cors import EmbedDynamicCorsMiddleware
from core.logging import get_logger

logger = get_logger(__name__)

# CORS для A2A/embed с другого порта (CRM :8003 → flows :8001): credentials несовместимы с Allow-Origin: *.
_FLOWS_DEV_CORS_ORIGIN_REGEX = (
    r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
    r"|"
    r"^https?://([a-z0-9-]+\.)*lvh\.me(:\d+)?$"
)


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
    from apps.flows.src.realtime import register_flows_ws_commands

    register_flows_ws_commands()

    from apps.flows.src.tasks.flow_tasks import process_flow_task
    from core.api.integrations import set_flow_resume_handler

    async def _flow_resume_via_taskiq(**kwargs):
        await process_flow_task.kiq(**kwargs)

    set_flow_resume_handler(_flow_resume_via_taskiq)

    from core.files.writer import FileWriter

    FileWriter.configure_process_upload(
        file_processor=container.file_processor,
        download_url_prefix=f"{FLOWS_PUBLIC_API_PREFIX}/files/download",
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

    # Загрузка tools + постановка init_company в worker не должны блокировать lifespan:
    # иначе Uvicorn не слушает порт, пока не отработают БД и TaskIQ (Docker health → unhealthy).
    if is_testing():
        system_context = Context(
            user=User(user_id="system", name="System", groups=["admin"]),
            host="system",
            session_id="system-startup",
            channel="system",
            language=Language.RU,
            active_company=Company(
                company_id="system",
                name="System",
                subdomain="system",
            ),
            user_companies=[],
            trace_id="system:startup",
        )
        set_context(system_context)
        try:
            loaded_tools = await load_tools_to_db(container.tool_repository)
            logger.info(f"Загружено tools: {loaded_tools}")
            logger.info("Загрузка flows из bundles синхронно (TESTING=true)...")
            from apps.flows.src.services.flows_loader import load_flows_to_db

            loaded_flow_ids = await load_flows_to_db(
                container.flow_repository,
                container.node_repository,
                container.tool_repository,
            )
            logger.info(f"Загружено flows: {loaded_flow_ids}")
            from apps.flows.src.services.operator_demo_queue import ensure_example_hitl_queue

            await ensure_example_hitl_queue(container.operator_repository, "system")
        except Exception as e:
            logger.error(f"Ошибка запуска миграции в system: {e}", exc_info=True)
        finally:
            clear_context()
    else:

        async def _tools_and_company_init_background() -> None:
            system_context = Context(
                user=User(user_id="system", name="System", groups=["admin"]),
                host="system",
                session_id="system-startup",
                channel="system",
                language=Language.RU,
                active_company=Company(
                    company_id="system",
                    name="System",
                    subdomain="system",
                ),
                user_companies=[],
                trace_id="system:startup",
            )
            set_context(system_context)
            try:
                loaded_tools = await load_tools_to_db(container.tool_repository)
                logger.info(f"Загружено tools: {loaded_tools}")
                from apps.flows.src.tasks.company_init_tasks import init_company_resources

                task = await init_company_resources.kiq(
                    company_id="system",
                    company_name="System",
                    subdomain="system",
                )
                logger.info(
                    "Фоновая инициализация flows для system: task_id=%s",
                    task.task_id,
                )
            except Exception as e:
                logger.error(
                    "Ошибка запуска миграции в system: %s",
                    e,
                    exc_info=True,
                )
            finally:
                clear_context()

        asyncio.create_task(_tools_and_company_init_background())
        logger.info("Загрузка tools и init_company_resources запущены в фоне")

    # Синхронизация LLM у провайдеров: не блокирует lifespan — иначе HTTP (в т.ч. /health)
    # недоступен, пока не отработают все внешние запросы (несколько провайдеров × ретраи).
    if not is_testing():

        async def _llm_models_startup_background() -> None:
            try:
                scheduler_context = await _build_scheduler_auth_context(
                    container=container,
                    trace_id="system:scheduler-sync",
                    session_id="system-scheduler-sync",
                )
                set_context(scheduler_context)
                try:
                    synced_counts = await container.llm_models_service.sync_all_providers()
                    total_synced = sum(synced_counts.values())
                    logger.info(
                        "Синхронизировано LLM моделей: %s (%s)",
                        total_synced,
                        synced_counts,
                    )
                    await container.llm_models_service.start_background_sync(interval=60)
                finally:
                    clear_context()
            except Exception as e:
                logger.error(
                    "Ошибка при синхронизации LLM моделей: %s",
                    e,
                    exc_info=True,
                )

        asyncio.create_task(_llm_models_startup_background())
        logger.info("Синхронизация LLM моделей запущена в фоне")
    else:
        logger.info("Пропускаем синхронизацию LLM моделей (TESTING)")
        from core.clients.llm.factory import get_llm
        from core.clients.llm.mock import configure_mock_llm_redis

        get_llm("mock-gpt-4")
        configure_mock_llm_redis(container.redis_client)
        logger.info("MockLLM: очередь ответов из Redis (как в TaskIQ worker)")

    # Telegram Dev Polling (только в development)
    if settings.server.env == "development" and not is_testing():
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
    if not is_testing():
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


_flow_settings = get_settings()
_cors_regex = _flow_settings.cors_allow_origin_regex
if "*" in _flow_settings.cors_allow_origins:
    raise ValueError("flows.cors_allow_origins не может содержать '*' для embed/A2A")
if _cors_regex is None and _flow_settings.server.debug and not is_testing():
    _cors_regex = _FLOWS_DEV_CORS_ORIGIN_REGEX

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
    cors_origins=list(_flow_settings.cors_allow_origins),
    cors_allow_origin_regex=_cors_regex,
    api_version="v1",
    title="Humanitec Flows",
    description="Сервис flows: конфигурации, runtime и A2A",
    version="2.0.0",
    mount_repo_documentation=False,
)

if _flow_settings.dynamic_embed_cors_enabled:
    app.add_middleware(EmbedDynamicCorsMiddleware, container=get_container())

# Документация (локальная статика apps/flows/site)
docs_path = Path(__file__).parent / "site"
if docs_path.exists():
    app.mount("/documentation", StaticFiles(directory=docs_path, html=True), name="documentation")

# Core frontend — раньше общего /static: иначе Mount("/static") забирает /static/core/... и ищет
# core/... внутри apps/flows/static (404 на tokens.css, import map и т.д.).
core_frontend_path = Path(__file__).parent.parent.parent / "core" / "frontend" / "static"
if core_frontend_path.exists():
    app.mount("/static/core", StaticFiles(directory=core_frontend_path), name="core_frontend")
    logger.info(f"Core frontend библиотека смонтирована: {core_frontend_path}")

# Статические файлы для чата (остальное под /static, кроме уже смонтированного /static/core)
static_path = Path(__file__).parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=static_path), name="static")

# UI - статические файлы
ui_path = Path(__file__).parent / "ui"
if ui_path.exists():
    app.mount("/flows/static", StaticFiles(directory=ui_path), name="ui_static")


_INDEX_HTML = (ui_path / "index.html").read_text(encoding="utf-8") if ui_path.exists() else ""


@app.get("/")
async def root():
    """Корневой запрос — редирект на SPA."""
    return RedirectResponse(url="/flows", status_code=302)


@app.get("/ui")
@app.get("/ui/{path:path}")
async def old_ui_redirect():
    """Редирект со старых путей /ui на новый /flows."""
    return RedirectResponse(url="/flows", status_code=301)


@app.get("/flows/ui")
@app.get("/flows/ui/{path:path}")
async def old_flows_ui_redirect():
    """Редирект со старых путей /flows/ui на /flows."""
    return RedirectResponse(url="/flows", status_code=301)


_API_LIKE_PREFIXES = ("api/", "static/", "ws/")


@app.get("/flows", response_class=HTMLResponse)
@app.get("/flows/", response_class=HTMLResponse)
@app.get("/flows/operator", response_class=HTMLResponse)
@app.get("/flows/operator/", response_class=HTMLResponse)
@app.get("/flows/{flow_id}", response_class=HTMLResponse)
@app.get("/flows/{flow_id}/{rest:path}", response_class=HTMLResponse)
async def ui_spa(flow_id: str = "", rest: str = ""):
    """SPA: маршруты flow_chat / flow_editor / operator / list."""
    if flow_id and flow_id.split("/")[0] in [p.rstrip("/") for p in _API_LIKE_PREFIXES]:
        raise HTTPException(status_code=404, detail="Not found")
    return HTMLResponse(content=_INDEX_HTML)


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
