"""
Точка входа FastAPI для сервиса flows.
"""

import asyncio
import importlib
from collections.abc import AsyncIterator
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

from fastapi.responses import HTMLResponse, RedirectResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from starlette.middleware.sessions import SessionMiddleware  # noqa: E402

from apps.flows.config import FlowSettings, get_settings  # noqa: E402
from apps.flows.di import FlowsDi  # noqa: E402
from apps.flows.realtime.command_router import FLOWS_OPERATIONS  # noqa: E402
from apps.flows.src.api import (  # noqa: E402
    a2a_router,
    websocket_router,
)
from apps.flows.src.api.v1 import api_v1_router  # noqa: E402
from apps.flows.src.api.v1.llm_proxy import router as llm_proxy_router  # noqa: E402
from apps.flows.src.db.bundle_seed_lock import flows_bundle_seed_lock  # noqa: E402
from apps.flows.src.llm_proxy import proxy as llm_proxy  # noqa: E402
from apps.flows.src.middleware.embed_dynamic_cors import EmbedDynamicCorsMiddleware  # noqa: E402
from apps.flows.src.services.demo_company_variables import seed_demo_company_variables  # noqa: E402
from apps.flows.src.services.flow_access_service import FlowAccessService  # noqa: E402
from apps.flows.src.services.flow_factory import FlowFactory  # noqa: E402
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
from apps.flows.src.tools.authz_gate import bound_tool_authz_gate  # noqa: E402
from apps.flows.src.triggers.dev_polling import start_dev_polling, stop_dev_polling  # noqa: E402
from core.api.integrations import set_flow_resume_handler  # noqa: E402
from core.app import create_service_app  # noqa: E402
from core.app.spa import mount_core_frontend, resolve_ui_static_dir  # noqa: E402
from core.authz.service import AuthzService  # noqa: E402
from core.clients.llm.mock import (  # noqa: E402
    configure_mock_llm_redis,
    get_or_create_global_mock_llm,
)
from core.clients.redis_client import RedisClient  # noqa: E402
from core.config.testing import is_testing  # noqa: E402
from core.context import reset_context, set_context  # noqa: E402
from core.db.storage import SharedStorage  # noqa: E402
from core.di import recipe  # noqa: E402
from core.files.create_spec import (  # noqa: E402
    RUNTIME_FLOW_ID,
    FileCreateSpec,
    FileSourceKind,
    FileSourceRef,
)
from core.files.registry import default_retention_for_source  # noqa: E402
from core.files.service import FilesService  # noqa: E402
from core.files.writer import FileWriter  # noqa: E402
from core.logging import get_logger  # noqa: E402
from core.models.context_models import Context  # noqa: E402
from core.models.i18n_models import Language  # noqa: E402
from core.models.identity_models import Company, User  # noqa: E402
from core.office.ai_settings import ONLYOFFICE_AI_BROWSER_CORS_ORIGINS  # noqa: E402
from core.tasks import enqueue  # noqa: E402
from core.variables.service import VariablesService  # noqa: E402
from core.websocket import WsCommandError  # noqa: E402
from core.worktracker.service import WorkItemService  # noqa: E402

# side-effect: register platform event catalog types
_ = importlib.import_module("apps.flows.src.events")

logger = get_logger(__name__)

# CORS для A2A/embed с другого порта (CRM :8003 → flows :8001): credentials несовместимы с Allow-Origin: *.
_FLOWS_DEV_CORS_ORIGIN_REGEX = (
    r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
    r"|"
    r"^https?://([a-z0-9-]+\.)*lvh\.me(:\d+)?$"
)


async def seed_testing_bundle(
    shared_storage: SharedStorage,
    files_service: FilesService,
    flow_access_service: FlowAccessService,
    variables_service: VariablesService,
    authz_service: AuthzService,
    work_item_service: WorkItemService,
) -> None:
    """Сид каталога flows для тест-контура: маркер до лока, повторная проверка внутри.

    Запускается из ``boot_flows`` (self-healing) и из ``scripts.testing.service_seed``
    в ``stack up`` — там он один раз готовит данные до спауна N granian-воркеров,
    иначе каждый воркер встаёт в очередь на ``pg_advisory_lock``.
    """
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
    startup_context = set_context(system_context)
    try:
        seed_marker = await shared_storage.get("flows:testing_bundle_seed")
        if seed_marker == "done":
            logger.info("flows.startup.seed_already_done")
            return
        async with flows_bundle_seed_lock():
            # Пока ждали лок, сид мог завершить другой процесс — повторная проверка.
            seed_marker = await shared_storage.get("flows:testing_bundle_seed")
            if seed_marker == "done":
                logger.info("flows.startup.seed_already_done")
                return
            loaded_tools = await load_tools_to_db(
                flow_access_service=flow_access_service,
            )
            logger.info("flows.startup.tools_loaded", tools=loaded_tools)
            logger.info("flows.bundles.testing.true")
            loaded_flow_ids = await load_flows_to_db(
                flow_access_service,
                files_service=files_service,
            )
            logger.info("flows.startup.flows_loaded", flow_ids=loaded_flow_ids)
            try:
                _ = await ensure_default_mcp_servers_for_company()
                synced = await sync_auto_mcp_servers_for_company(
                    variables_service=variables_service,
                    flow_access_service=flow_access_service,
                )
                logger.info(
                    "flows.mcp.system.servers.tools",
                    servers=synced["servers"],
                    tools=synced["tools"],
                )
            except Exception as mcp_err:
                logger.warning("flows.mcp", mcp_err=mcp_err, exc_info=True)
            seeded_variables = await seed_demo_company_variables(
                variables_service,
                "system",
            )
            logger.info("flows.system.count", count=seeded_variables)
            seeded_skills = await seed_platform_assistant_skills(
                files_service,
                "system",
            )
            logger.info("flows.platform_assistant", count=seeded_skills)
            stored_company = await Company.get("system")
            member_user_ids = (
                await hitl_demo_operator_user_ids(authz_service, "system")
                if stored_company is not None
                else []
            )
            await ensure_example_hitl_queue(
                work_item_service,
                "system",
                member_user_ids=member_user_ids,
            )
            _ = await shared_storage.set("flows:testing_bundle_seed", '"done"')
    finally:
        reset_context(startup_context)


async def boot_flows(
    settings: FlowSettings,
    files_service: FilesService,
    redis_client: RedisClient,
    flow_access_service: FlowAccessService,
    flow_factory: FlowFactory,
) -> AsyncIterator[None]:
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
        files_service=files_service,
        default_spec=FileCreateSpec(
            source_kind=FileSourceKind.FLOW_ASSET,
            source_ref=FileSourceRef(flow_id=RUNTIME_FLOW_ID),
            retention=default_retention_for_source(FileSourceKind.FLOW_ASSET),
        ),
    )

    # Подключаемся к Redis с retry
    logger.info("flows.connecting.redis")
    max_startup_retries = 5
    for attempt in range(max_startup_retries):
        try:
            await redis_client.connect()
            logger.info("flows.redis.connected")
            break
        except Exception as e:
            if attempt < max_startup_retries - 1:
                wait = 1 << attempt
                logger.warning(
                    "flows.startup.redis_retry",
                    attempt=attempt + 1,
                    wait_seconds=wait,
                    error=str(e),
                )
                await asyncio.sleep(wait)
            else:
                logger.error("flows.failed.connect.redis.startup")
                raise

    if settings.server.env == "development" and not is_testing():
        await sync_landing_public_demo_flows_from_bundles(
            flow_access_service, settings, files_service
        )

    # Production/dev system bootstrap: idle_worker → POST /internal/company/init → flows_worker.
    # Тяжёлый company/MCP init в HTTP-процессе flows запрещён (healthcheck + ownership).
    # Каталог и системные данные в тест-контуре сеет один процесс —
    # scripts.testing.service_seed в stack up (peers secrets/realtime должны быть
    # живы: на спаде старта сид не завершается и каждый из N воркеров встаёт на
    # pg_advisory_lock). Воркеры сами не сеют и не ждут.

    if is_testing():
        logger.info("flows.llm.testing")

        _ = get_or_create_global_mock_llm("mock-gpt-4")
        _ = configure_mock_llm_redis(redis_client)
        logger.info("flows.mockllm.redis.taskiq.worker")

    # Telegram Dev Polling (только в development)
    if settings.server.env == "development" and not is_testing():
        await start_dev_polling(flow_factory)
        logger.info("flows.telegram.dev.polling")
    yield
    try:
        await stop_dev_polling()
    except Exception as e:
        logger.warning("flows.shutdown.dev_polling_stop_failed", error=str(e))


_flow_settings = FlowSettings.model_validate(_FLOWS_BOOTSTRAP_MERGED)
_flows_brand = _flow_settings.platform_brands[_flow_settings.primary_platform_domain]
_cors_regex = _flow_settings.cors_allow_origin_regex
if "*" in _flow_settings.cors_allow_origins:
    raise ValueError("flows.cors_allow_origins cannot contain '*' for embed/A2A")
if _cors_regex is None and _flow_settings.server.debug and not is_testing():
    _cors_regex = _FLOWS_DEV_CORS_ORIGIN_REGEX

# OnlyOffice AI plugin (CDN/DS) → browser fetch на /llm; без этих Origin UI: «Ошибка: [provider]».
_flows_cors_origins = list(
    dict.fromkeys(
        [
            *_flow_settings.cors_allow_origins,
            *ONLYOFFICE_AI_BROWSER_CORS_ORIGINS,
        ]
    )
)

_UI_PATH = Path(__file__).parent / "ui"
_UI_STATIC_PATH = resolve_ui_static_dir(_UI_PATH)

app = create_service_app(
    "flows",
    FlowSettings,
    FlowsDi,
    database="flows_url",
    operations=FLOWS_OPERATIONS,
    lifecycle=(recipe(bound_tool_authz_gate), recipe(boot_flows)),
    services_spa_index=_UI_STATIC_PATH / "index.html",
    routers=[
        api_v1_router,
        websocket_router,
        a2a_router,
        llm_proxy_router,
    ],
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
    outer_middlewares=(
        [(EmbedDynamicCorsMiddleware, {})]
        if _flow_settings.dynamic_embed_cors_enabled
        else None
    ),
    extra_exception_handlers=llm_proxy.LLM_PROXY_EXCEPTION_HANDLERS,
    cors_origins=_flows_cors_origins,
    cors_allow_origin_regex=_cors_regex,
    api_version="v1",
    title=f"{_flows_brand.flows_product_label} API",
    description="Сервис flows: конфигурации, runtime и A2A",
    version="2.0.0",
)

# Core frontend — раньше общего /static: иначе Mount("/static") забирает /static/core/... и ищет
# core/... внутри apps/flows/static (404 на tokens.css, import map и т.д.).
mount_core_frontend(app)

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

# UI - статические файлы (ui-dist/ после `npm run build:ui`, иначе ui/)
if _UI_STATIC_PATH.exists():
    app.mount("/flows/static", StaticFiles(directory=_UI_STATIC_PATH), name="ui_static")


_INDEX_HTML = (_UI_STATIC_PATH / "index.html").read_text(encoding="utf-8") if _UI_STATIC_PATH.exists() else ""


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
        raise WsCommandError("not_found", "Not Found", error_code="not_found")
    return HTMLResponse(content=_INDEX_HTML)


if __name__ == "__main__":
    from core.app.server import serve

    serve("flows", "apps.flows.main:app", get_settings())
