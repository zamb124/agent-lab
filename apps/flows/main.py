"""
Точка входа FastAPI для сервиса flows.
"""

import asyncio
import importlib
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

from apps.agent import llm_proxy as agent_llm_proxy  # noqa: E402
from apps.agent.platform_mcp import router as agent_platform_mcp_router  # noqa: E402
from apps.agent.tunnel_bus import (  # noqa: E402
    configure_tunnel_bus_storage,
    start_tunnel_bus_listener,
)
from apps.flows.config import FlowSettings, get_settings  # noqa: E402
from apps.flows.src.api import (  # noqa: E402
    a2a_router,
    registry_router,
    websocket_router,
)
from apps.flows.src.api.v1 import api_v1_router  # noqa: E402
from apps.flows.src.container import FlowContainer, get_container  # noqa: E402
from apps.flows.src.container_contracts import as_flow_runtime_container  # noqa: E402
from apps.flows.src.middleware.embed_dynamic_cors import EmbedDynamicCorsMiddleware  # noqa: E402
from apps.flows.src.services.demo_company_variables import seed_demo_company_variables  # noqa: E402
from apps.flows.src.services.flows_loader import (  # noqa: E402
    load_flows_to_db,
    load_tools_to_db,
)
from apps.flows.src.services.hitl_demo_queue import (  # noqa: E402
    ensure_example_hitl_queue,
    hitl_demo_operator_user_ids,
)
from apps.flows.src.services.landing_bundle_dev_sync import (  # noqa: E402
    sync_landing_public_demo_flows_from_bundles,
)
from apps.flows.src.services.mcp_sync import (  # noqa: E402
    ensure_default_mcp_servers_for_company,
    sync_auto_mcp_servers_for_company,
)
from apps.flows.src.services.platform_assistant_skills import (  # noqa: E402
    seed_platform_assistant_skills,
)
from apps.flows.src.tasks.task_names import TASK_PROCESS_FLOW  # noqa: E402
from apps.flows.src.triggers.dev_polling import start_dev_polling, stop_dev_polling  # noqa: E402
from core.api.integrations import set_flow_resume_handler  # noqa: E402
from core.app import create_service_app  # noqa: E402
from core.clients.llm.mock import (  # noqa: E402
    configure_mock_llm_redis,
    get_or_create_global_mock_llm,
)
from core.config.testing import is_testing  # noqa: E402
from core.context import clear_context, set_context  # noqa: E402
from core.files.create_spec import FileCreateSpec, FileSourceKind, FileSourceRef  # noqa: E402
from core.files.registry import default_retention_for_source  # noqa: E402
from core.files.writer import FileWriter  # noqa: E402
from core.logging import get_logger  # noqa: E402
from core.models.context_models import Context  # noqa: E402
from core.models.i18n_models import Language  # noqa: E402
from core.models.identity_models import Company, User  # noqa: E402
from core.office.ai_settings import ONLYOFFICE_AI_BROWSER_CORS_ORIGINS  # noqa: E402
from core.tasks import enqueue  # noqa: E402

# side-effect: register platform event catalog types
_ = importlib.import_module("apps.flows.src.events")

logger = get_logger(__name__)

# CORS для A2A/embed с другого порта (CRM :8003 → flows :8001): credentials несовместимы с Allow-Origin: *.
_FLOWS_DEV_CORS_ORIGIN_REGEX = (
    r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
    r"|"
    r"^https?://([a-z0-9-]+\.)*lvh\.me(:\d+)?$"
)


async def on_startup(_app: FastAPI, container: FlowContainer, settings: FlowSettings) -> None:
    """Логика при старте сервиса flows."""

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
        _ = await enqueue(
            TASK_PROCESS_FLOW,
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
            background_kind="flow_resume",
        )

    set_flow_resume_handler(_flow_resume_via_taskiq)

    FileWriter.configure_process_upload(
        files_service=container.files_service,
        default_spec=FileCreateSpec(
            source_kind=FileSourceKind.FLOW_ASSET,
            source_ref=FileSourceRef(flow_id="runtime"),
            retention=default_retention_for_source(FileSourceKind.FLOW_ASSET),
        ),
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

    configure_tunnel_bus_storage(container.storage)
    await start_tunnel_bus_listener(container.redis_client)

    if settings.server.env == "development" and not is_testing():
        await sync_landing_public_demo_flows_from_bundles(container, settings)

    # Production/dev system bootstrap: idle_worker → POST /internal/company/init → flows_worker.
    # Тяжёлый company/MCP init в HTTP-процессе flows запрещён (healthcheck + ownership).
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
                runtime_container = as_flow_runtime_container(container)
                _ = await ensure_default_mcp_servers_for_company(container=runtime_container)
                synced = await sync_auto_mcp_servers_for_company(container=runtime_container)
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
            seeded_variables = await seed_demo_company_variables(
                container.variables_service,
                "system",
            )
            logger.info("Демо-переменные system: count=%s", seeded_variables)
            seeded_skills = await seed_platform_assistant_skills(
                container.agent_skill_service,
                container.files_service,
                "system",
            )
            logger.info("platform_assistant skills system: count=%s", seeded_skills)
            stored_company = await container.company_repository.get("system")
            member_user_ids = (
                hitl_demo_operator_user_ids(stored_company)
                if stored_company is not None
                else []
            )
            await ensure_example_hitl_queue(
                container.work_item_service,
                "system",
                member_user_ids=member_user_ids,
            )
        except Exception as e:
            logger.error(f"Ошибка запуска миграции в system: {e}", exc_info=True)
        finally:
            clear_context()

    if is_testing():
        logger.info("Пропускаем синхронизацию LLM моделей (TESTING)")

        _ = get_or_create_global_mock_llm("mock-gpt-4")
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
_flows_brand = _flow_settings.platform_brands[_flow_settings.primary_platform_domain]
_cors_regex = _flow_settings.cors_allow_origin_regex
if "*" in _flow_settings.cors_allow_origins:
    raise ValueError("flows.cors_allow_origins не может содержать '*' для embed/A2A")
if _cors_regex is None and _flow_settings.server.debug and not is_testing():
    _cors_regex = _FLOWS_DEV_CORS_ORIGIN_REGEX

# OnlyOffice AI plugin (CDN/DS) → browser fetch на /agent/llm; без этих Origin UI: «Ошибка: [provider]».
_flows_cors_origins = list(
    dict.fromkeys(
        [
            *_flow_settings.cors_allow_origins,
            *ONLYOFFICE_AI_BROWSER_CORS_ORIGINS,
        ]
    )
)

app = create_service_app(
    service_name="flows",
    settings_class=FlowSettings,
    get_container=get_container,
    services_spa_index=Path(__file__).parent / "ui" / "index.html",
    routers=[
        api_v1_router,
        registry_router,
        websocket_router,
        a2a_router,
        agent_platform_mcp_router,
        agent_llm_proxy.router,
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
    cors_origins=_flows_cors_origins,
    cors_allow_origin_regex=_cors_regex,
    api_version="v1",
    title=f"{_flows_brand.flows_product_label} API",
    description="Сервис flows: конфигурации, runtime и A2A",
    version="2.0.0",
)
agent_llm_proxy.install_llm_proxy_exception_handlers(app)

if _flow_settings.dynamic_embed_cors_enabled:
    app.add_middleware(EmbedDynamicCorsMiddleware, container=get_container())

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
    """SPA: корень приложения (маршрут list с path '")."""
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
    from core.app.server import serve

    serve("flows", "apps.flows.main:app", get_settings())
