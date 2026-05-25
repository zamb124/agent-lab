"""
Точка входа FastAPI для сервиса flows.
"""

import asyncio
from pathlib import Path

from core.config.loader import load_merged_config
from core.config.models import LoggingConfig
from core.logging.setup import setup_logging
from core.types import JsonObject, require_json_object

_FLOWS_BOOTSTRAP_MERGED = load_merged_config(service_name="flows", silent=True)
setup_logging(
    "flows",
    LoggingConfig.model_validate(
        require_json_object(_FLOWS_BOOTSTRAP_MERGED.get("logging") or {}, "logging")
    ),
)

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import HTMLResponse, RedirectResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from starlette.middleware.sessions import SessionMiddleware  # noqa: E402

from apps.flows.config import FLOWS_PUBLIC_API_PREFIX, FlowSettings, get_settings  # noqa: E402
from apps.flows.src.api import (  # noqa: E402
    a2a_router,
    chat_router,
    registry_router,
    websocket_router,
)
from apps.flows.src.api.v1 import api_v1_router  # noqa: E402
from apps.flows.src.container import FlowContainer, get_container  # noqa: E402
from apps.flows.src.middleware.embed_dynamic_cors import EmbedDynamicCorsMiddleware  # noqa: E402
from apps.flows.src.realtime import register_flows_ws_commands  # noqa: E402
from apps.flows.src.services.flows_loader import (  # noqa: E402
    load_flows_to_db,
    load_tools_to_db,
)
from apps.flows.src.services.landing_bundle_dev_sync import (  # noqa: E402
    sync_landing_public_demo_flows_from_bundles,
)
from apps.flows.src.services.mcp_sync import (  # noqa: E402
    ensure_default_mcp_servers_for_company,
    sync_auto_mcp_servers_for_company,
)
from apps.flows.src.services.operator_demo_queue import ensure_example_hitl_queue  # noqa: E402
from apps.flows.src.tasks.company_init_tasks import init_company_resources  # noqa: E402
from apps.flows.src.tasks.flow_tasks import process_flow_task  # noqa: E402
from apps.flows.src.triggers.dev_polling import start_dev_polling, stop_dev_polling  # noqa: E402
from core.api.integrations import set_flow_resume_handler  # noqa: E402
from core.app import create_service_app  # noqa: E402
from core.clients.llm.factory import get_llm  # noqa: E402
from core.clients.llm.mock import configure_mock_llm_redis  # noqa: E402
from core.config.testing import is_testing  # noqa: E402
from core.context import clear_context, set_context  # noqa: E402
from core.files.writer import FileWriter  # noqa: E402
from core.logging import get_logger  # noqa: E402
from core.models.context_models import Context  # noqa: E402
from core.models.i18n_models import Language  # noqa: E402
from core.models.identity_models import Company, User  # noqa: E402
from core.utils.background import run_with_log_context  # noqa: E402

logger = get_logger(__name__)

# CORS для A2A/embed с другого порта (CRM :8003 → flows :8001): credentials несовместимы с Allow-Origin: *.
_FLOWS_DEV_CORS_ORIGIN_REGEX = (
    r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
    r"|"
    r"^https?://([a-z0-9-]+\.)*lvh\.me(:\d+)?$"
)


async def on_startup(_app: FastAPI, container: FlowContainer, settings: FlowSettings) -> None:
    """Логика при старте сервиса flows."""
    register_flows_ws_commands()

    async def _flow_resume_via_taskiq(
        *,
        flow_id: str,
        session_id: str,
        user_id: str,
        content: str,
        branch_id: str,
        channel: str,
        task_id: str,
        context_id: str,
        metadata: JsonObject,
        is_resume: bool,
        files: list[JsonObject],
        context_data: JsonObject,
        trace_context: JsonObject | None,
    ) -> None:
        _ = await process_flow_task.kiq(
            flow_id=flow_id,
            session_id=session_id,
            user_id=user_id,
            content=content,
            branch_id=branch_id,
            channel=channel,
            task_id=task_id,
            context_id=context_id,
            metadata=metadata,
            is_resume=is_resume,
            files=files,
            context_data=context_data,
            trace_context=trace_context,
        )

    set_flow_resume_handler(_flow_resume_via_taskiq)

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
                wait = 1 << attempt
                logger.warning(
                    f"Redis connection failed (attempt {attempt + 1}), retry in {wait}s: {e}"
                )
                await asyncio.sleep(wait)
            else:
                logger.error("Failed to connect to Redis on startup")
                raise

    if settings.server.env == "development" and not is_testing():
        await sync_landing_public_demo_flows_from_bundles(container, settings)

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
            loaded_flow_ids = await load_flows_to_db(
                container.flow_repository,
                container.node_repository,
                container.tool_repository,
            )
            logger.info(f"Загружено flows: {loaded_flow_ids}")

            try:
                _ = await ensure_default_mcp_servers_for_company(container=container)
                synced = await sync_auto_mcp_servers_for_company(container=container)
                logger.info(
                    "MCP синхронизация для system: servers=%s tools=%s",
                    synced["servers"],
                    synced["tools"],
                )
            except Exception as mcp_err:
                logger.warning(
                    "MCP синхронизация при старте тестов пропущена: %s",
                    mcp_err,
                    exc_info=True,
                )
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

                _ = await ensure_default_mcp_servers_for_company(container=container)
                synced = await sync_auto_mcp_servers_for_company(container=container)
                logger.info(
                    "MCP синхронизация для system: servers=%s tools=%s",
                    synced["servers"],
                    synced["tools"],
                )
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

        _ = run_with_log_context(
            _tools_and_company_init_background(),
            name="flows.tools_and_company_init_background",
            background_kind="startup",
        )
        logger.info("flows.tools_and_company_init_scheduled")

    if is_testing():
        logger.info("Пропускаем синхронизацию LLM моделей (TESTING)")

        _ = get_llm("mock-gpt-4")
        _ = configure_mock_llm_redis(container.redis_client)
        logger.info("MockLLM: очередь ответов из Redis (как в TaskIQ worker)")

    # Telegram Dev Polling (только в development)
    if settings.server.env == "development" and not is_testing():
        await start_dev_polling()
        logger.info("Telegram dev polling запущен")


async def on_shutdown(_app: FastAPI, container: FlowContainer) -> None:
    """Логика при остановке сервиса flows."""

    # Остановка Telegram dev polling
    try:
        await stop_dev_polling()
    except Exception as e:
        logger.warning(f"Error stopping dev polling: {e}")

    # Закрываем Redis с error handling
    try:
        await container.redis_client.close()
        logger.info("flows.redis.disconnected")
    except Exception as exc:
        logger.exception(
            "flows.redis.close_failed",
            **{"exception.type": type(exc).__name__},
        )


_flow_settings = FlowSettings.model_validate(_FLOWS_BOOTSTRAP_MERGED)
_cors_regex = _flow_settings.cors_allow_origin_regex
if "*" in _flow_settings.cors_allow_origins:
    raise ValueError("flows.cors_allow_origins не может содержать '*' для embed/A2A")
if _cors_regex is None and _flow_settings.server.debug and not is_testing():
    _cors_regex = _FLOWS_DEV_CORS_ORIGIN_REGEX

app = create_service_app(
    service_name="flows",
    settings_class=FlowSettings,
    get_container=get_container,
    services_spa_index=Path(__file__).parent / "ui" / "index.html",
    routers=[
        api_v1_router,
        registry_router,
        chat_router,
        websocket_router,
        a2a_router,
    ],
    on_startup=on_startup,
    on_shutdown=on_shutdown,
    extra_middlewares=[
        (
            SessionMiddleware,
            {
                "secret_key": _flow_settings.auth.jwt_secret_key
                or "dev-secret-key-change-in-production",
                "session_cookie": "platform_session",
                "same_site": "lax",
                "https_only": False,
            },
        ),
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
    logger.info(
        "flows.static.core_mounted",
        path=str(core_frontend_path),
    )

# Статические файлы для чата (остальное под /static, кроме уже смонтированного /static/core)
static_path = Path(__file__).parent / "static"
demo_cards_path = static_path / "demo_cards"
if demo_cards_path.is_dir():
    app.mount(
        "/flows/demo_cards",
        StaticFiles(directory=demo_cards_path),
        name="flows_demo_cards",
    )
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


@app.get("/flows", response_class=HTMLResponse)
@app.get("/flows/", response_class=HTMLResponse)
async def ui_spa_flows_root():
    """SPA: корень приложения (маршрут list с path '')."""
    return HTMLResponse(content=_INDEX_HTML)


@app.get("/flows/{flow_id}", response_class=HTMLResponse)
@app.get("/flows/{flow_id}/{rest:path}", response_class=HTMLResponse)
async def ui_spa_flow(flow_id: str, rest: str = ""):
    """SPA: flow_chat / flow_editor и вложенные client-маршруты."""
    _ = rest
    if flow_id in ("api", "static", "ws"):
        raise HTTPException(status_code=404, detail="Not Found")
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
