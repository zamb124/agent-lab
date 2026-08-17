"""
Фикстуры для тестов platform.

ПРАВИЛО: Мок только LLM. Все остальное - реальные объекты.
Tools автоматически работают в mock режиме (TESTING=true).
TaskIQ worker запускается автоматически для тестов.

Фикстуры сервисов и клиентов загружаются из tests/fixtures/ через pytest_plugins.
"""

import os

os.environ.setdefault("LOGGING__LEVEL", "WARNING")

import asyncio
import sys
import uuid
from collections.abc import Generator
from pathlib import Path
from typing import Any, List

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from tests.fixtures.test_database_env import TEST_DATABASE_ENV

pytest_plugins = [
    "tests.hang_guard",
    "tests.fixtures.workers",
    "tests.fixtures.services",
    "tests.fixtures.clients",
    "tests.fixtures.auth",
    "tests.fixtures.push",
    "tests.fixtures.s3",
    "tests.fixtures.mcp_modes_stub",
    "tests.fixtures.mcp_registry_stub",
    "tests.fixtures.embed_e2e",
    "tests.fixtures.flows_chat_e2e",
    "tests.fixtures.google_api_emulator.handle",
    "tests.fixtures.wiki",
    "tests.fixtures.openfga",
    "tests.agent.fixtures.local_releases",
    "tests.agent.fixtures.e2e",
    "tests.profiling.plugin",
    "tests.core.files.conftest",
    "tests.core.mail.live.personal_conftest",
]

os.environ["TESTING"] = "true"
os.environ.setdefault("AGENT__RELEASES__SOURCE", "local")
if sys.platform == "darwin":
    _brew_path = "/opt/homebrew/bin"
    if _brew_path not in os.environ.get("PATH", ""):
        os.environ["PATH"] = f"{_brew_path}:{os.environ.get('PATH', '')}"
for _db_key, _db_val in TEST_DATABASE_ENV.items():
    if _db_key.startswith("OPENFGA__"):
        # Store/model из reports/openfga-test.env должны перекрывать conf defaults.
        os.environ[_db_key] = _db_val
    else:
        os.environ.setdefault(_db_key, _db_val)
os.environ.setdefault("DATABASE__REDIS_URL", "redis://localhost:63792/0")
os.environ.setdefault("TASKS__BROKER_URL", "redis://localhost:63792/1")
os.environ.setdefault("TRACING__TEMPO_ENABLED", "false")
os.environ.setdefault("SERVER__DEFAULT_TENANT_ID", "test_tenant")
os.environ["SERVER__FLOWS_SERVICE_URL"] = "http://localhost:9001"
os.environ["SERVER__RAG_SERVICE_URL"] = "http://localhost:9002"
os.environ["SERVER__CRM_SERVICE_URL"] = "http://localhost:9003"
os.environ["SERVER__FRONTEND_SERVICE_URL"] = "http://localhost:9004"
os.environ["SERVER__SYNC_SERVICE_URL"] = "http://localhost:9005"
os.environ["SERVER__OFFICE_SERVICE_URL"] = "http://localhost:9008"
os.environ["SERVER__SEARCH_SERVICE_URL"] = "http://localhost:9010"
os.environ["SERVER__VOICE_SERVICE_URL"] = "http://localhost:9015"
os.environ["SERVER__CAPABILITY_GATEWAY_SERVICE_URL"] = "http://localhost:9016"
os.environ["SERVER__PROVIDER_LITSERVE_SERVICE_URL"] = "http://localhost:9014"
os.environ["SERVER__CODE_RUNNER_PYTHON_SERVICE_URL"] = "http://localhost:9017"
os.environ["SERVER__CODE_RUNNER_NODE_SERVICE_URL"] = "http://localhost:9018"
os.environ["SERVER__CODE_RUNNER_GO_SERVICE_URL"] = "http://localhost:9019"
os.environ["SERVER__CODE_RUNNER_CSHARP_SERVICE_URL"] = "http://localhost:9020"
os.environ["SERVER__WORKTRACKER_SERVICE_URL"] = "http://localhost:9021"
os.environ["SERVER__WIKI_SERVICE_URL"] = "http://localhost:9023"
os.environ.setdefault("VOICE__STT__PROVIDER", "mock")
os.environ.setdefault("VOICE__STT__MOCK_TRANSCRIPT_TEXT", "Тестовая транскрипция sync worker")
os.environ.setdefault("S3__DEFAULT_BUCKET", "test-bucket")
os.environ.setdefault("S3__BUCKETS__TEST-BUCKET__ENDPOINT_URL", "http://localhost:19002")
from tests.fixtures.test_database_env import TEST_HS256_JWT_SECRET  # noqa: E402

os.environ.setdefault("AUTH__JWT_SECRET_KEY", TEST_HS256_JWT_SECRET)
os.environ.setdefault("OFFICE__DOCUMENT_SERVER_PUBLIC_URL", "http://localhost:18088")
os.environ.setdefault("OFFICE__CALLBACK_PUBLIC_BASE_URL", "http://host.docker.internal:9008")
os.environ.setdefault("OFFICE__JWT_SECRET", "test-onlyoffice-jwt-secret")
os.environ["SERVER__DOCUMENT_SERVER_DEV_UPSTREAM_URL"] = os.environ[
    "OFFICE__DOCUMENT_SERVER_PUBLIC_URL"
]
os.environ.setdefault("RAG__ENABLED", "true")
os.environ.setdefault("RAG__DEFAULT_PROVIDER", "pgvector")
os.environ.setdefault("RAG__PROVIDERS__PGVECTOR__ENABLED", "true")
os.environ.setdefault("LLM__PROVIDER", "openrouter")
os.environ.setdefault("RAG__EMBEDDING__PROVIDER", "provider_litserve")
os.environ.setdefault("RAG__EMBEDDING__API__MODEL", "qwen/qwen3-embedding-0.6b")
os.environ.setdefault("RAG__EMBEDDING__API__DIMENSION", "1024")
os.environ.setdefault("RAG__EMBEDDING__API__MRL_OUTPUT_DIMENSION", "1024")
os.environ["PROVIDER_LITSERVE__API__BASE_URL"] = "http://localhost:9014/v1"
os.environ.setdefault("RAG__DOCUMENT_INDEXING__SEARCH_DEFAULTS__RERANKER__ENABLED", "true")
os.environ.setdefault("LLM__OPENROUTER__API_KEY", "sk-test-key")
import core.config.base  # noqa: E402

core.config.base._settings_instance = None

from core.config import get_settings  # noqa: E402
from core.logging.setup import setup_logging  # noqa: E402

setup_logging("pytest", get_settings().logging)

from apps.platform_tasks.wiring import wire_brokers  # noqa: E402

wire_brokers()

import apps.flows_worker.broker as platform_broker_module  # noqa: E402
from apps.flows.main import app as fastapi_app  # noqa: E402
from apps.flows.src.tasks.flow_tasks import process_flow_task  # noqa: E402
from core.clients.llm import MockLLM, get_global_mock_llm, setup_mock_responses  # noqa: E402
from core.context import Context, User  # noqa: E402
from core.tracing.provider import shutdown_tracing  # noqa: E402
from tests.fixtures.ai_provider_defaults import make_test_company  # noqa: E402

if id(process_flow_task.broker) != id(platform_broker_module.broker):
    raise RuntimeError(
        "process_flow_task привязан к другому broker, чем apps.flows_worker.broker: "
        "TaskIQ worker не сможет выполнять enqueue из HTTP."
    )


def pytest_sessionfinish(session, exitstatus):
    shutdown_tracing()
    from tests.fixtures.aiohttp_cleanup import (
        close_all_open_aiohttp_sessions_sync,
        shutdown_test_logging_handlers,
    )

    close_all_open_aiohttp_sessions_sync()
    shutdown_test_logging_handlers()
    if hasattr(session.config, "workerinput"):
        return
    from tests.fixtures.workers import release_pytest_controller_session

    release_pytest_controller_session()


async def _alembic_current_revision(db_url: str) -> str | None:
    """Читает текущую ревизию alembic_version из БД. None если таблицы нет."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(db_url, echo=False)
    try:
        async with engine.begin() as conn:
            row = await conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
            r = row.first()
            return r[0] if r else None
    except Exception:
        return None
    finally:
        await engine.dispose()


def _alembic_head_revision(script_location: str) -> str | None:
    """Читает head ревизию из файлов Alembic (без подключения к БД)."""
    from pathlib import Path

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = Path(__file__).parent.parent
    ini_path = root / script_location / "alembic.ini"
    if not ini_path.exists():
        return None
    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(root / script_location))
    directory = ScriptDirectory.from_config(cfg)
    heads = directory.get_heads()
    return heads[0] if heads else None


async def _all_migrations_up_to_date() -> tuple[bool, list[str]]:
    """
    Сравнивает head в коде с current в БД для каждого сервиса из migration_manifest.
    Возвращает (all_ok, list_of_stale_service_names).
    """
    from core.db.migration_manifest import (
        database_url_for_migration_key,
        load_migration_manifest,
        migration_entry_is_active,
    )

    manifest = load_migration_manifest()
    stale: list[str] = []
    for entry in manifest.services:
        if not migration_entry_is_active(entry):
            continue
        name = entry.name
        script_loc = f"migrations/{name}"
        head = _alembic_head_revision(script_loc)
        if head is None:
            continue
        from core.config import get_settings

        db_url = database_url_for_migration_key(get_settings().database, entry.database_url_key)
        if not db_url or not str(db_url).strip():
            continue
        current = await _alembic_current_revision(str(db_url))
        if current != head:
            stale.append(name)
    return (len(stale) == 0, stale)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database_before_tests():
    """
    Быстрая проверка актуальности миграций: Alembic head (файлы) == current (БД).

    Миграции применяет make test-up (scripts.test_migrate) до старта pytest;
    фикстура ничего не мигрирует и не держит локов.
    """
    from core.db.migration_manifest import bootstrap_migration_registry

    bootstrap_migration_registry()
    (all_ok, stale_services) = await _all_migrations_up_to_date()
    if not all_ok:
        pytest.fail(
            "Миграции не применены для сервисов: "
            + ", ".join(stale_services)
            + " — выполните make test-up",
            pytrace=False,
        )
    yield


@pytest_asyncio.fixture(scope="session", autouse=True)
async def platform_notification_manager_redis(setup_database_before_tests):
    """Redis Pub/Sub для notify_user; без этого CRM и др. падают до старта flows lifespan."""
    from core.websocket.manager import notification_manager

    redis_url = os.environ.get("DATABASE__REDIS_URL", "redis://localhost:63792/0")
    await notification_manager.start_redis_listener(redis_url)
    yield
    try:
        await asyncio.wait_for(notification_manager.stop_redis_listener(), timeout=30.0)
    except asyncio.TimeoutError:
        from core.logging import get_logger

        get_logger(__name__).warning(
            "platform_notification_manager_redis.stop_redis_listener_timed_out"
        )


def pytest_configure(config):
    """Guard одного pytest-контроллера и подготовка каталога junitxml."""
    import pathlib

    if not hasattr(config, "workerinput"):
        from tests.fixtures.workers import prepare_pytest_controller_session

        try:
            prepare_pytest_controller_session()
        except RuntimeError as exc:
            raise pytest.UsageError(str(exc)) from exc

    junitxml_path = config.getoption("--junitxml", default=None)
    if junitxml_path:
        junit_path = pathlib.Path(junitxml_path)
        junit_path.parent.mkdir(parents=True, exist_ok=True)


_CODE_RUNNER_TEST_PREFIXES = (
    "tests/flows/api/test_code_api.py",
    "tests/flows/api/test_node_execute.py",
    "tests/flows/core/agent/test_tool_node.py",
    "tests/flows/core/tasks/test_tasks.py",
    "tests/flows/e2e/test_tool_node_e2e.py",
    "tests/flows/e2e/test_full_flow_api.py",
)


def _is_sandbox_runtime_test(nodeid: str) -> bool:
    """Тесты с HTTP sandbox-контуром (capability_gateway + code_runner_*) на портах 9016–9020.

    flows/integration и flows/e2e autouse-зависят от sandbox_services и RemoteCodeRunner;
    им нужен увеличенный pytest-timeout, как capabilities и code-runner API тестам.
    """
    if nodeid.startswith("tests/capabilities/"):
        return True
    if nodeid.startswith("tests/flows/integration/"):
        return True
    if nodeid.startswith("tests/flows/e2e/"):
        return True
    return any(nodeid.startswith(prefix) for prefix in _CODE_RUNNER_TEST_PREFIXES)


def _is_sync_db_test(nodeid: str) -> bool:
    return nodeid.startswith("tests/sync/db/")


def _is_crm_e2e_test(nodeid: str) -> bool:
    return nodeid.startswith("tests/crm/e2e/")


def _marker_timeout_seconds(marker: pytest.Mark | None) -> float | None:
    if marker is None or not marker.args:
        return None
    raw: object = marker.args[0]
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    return float(raw)


def _ensure_item_timeout(item: pytest.Item, seconds: float, *, func_only: bool) -> None:
    """Item-level timeout перекрывает module pytestmark (get_closest_marker)."""
    item.own_markers = [marker for marker in item.own_markers if marker.name != "timeout"]
    item.add_marker(pytest.mark.timeout(seconds, func_only=func_only))


def _is_rag_global_maintenance_test(nodeid: str) -> bool:
    """Reembed/orphan maintenance на shared vector_documents: глобальные batch-операции."""
    if nodeid.startswith("tests/core/rag/test_execute_reembed_tick_integration.py"):
        return True
    if nodeid.startswith("tests/rag/test_pgvector_provider.py"):
        return "delete_orphan_company_chunks" in nodeid
    return False


def _is_notification_ws_e2e_test(nodeid: str) -> bool:
    return nodeid.startswith("tests/core/websocket/test_notification_e2e.py")


def _is_files_s3_test(nodeid: str) -> bool:
    """MinIO + Files API (chunked upload/download, retention purge): под -n10 >5s."""
    if nodeid.startswith("tests/files/"):
        return True
    # Тот же purge_expired_batch через idle_worker tick: под -n10 >5s.
    if (
        nodeid.startswith("tests/idle_worker/test_idle_worker_tasks.py")
        and "file_retention_purge" in nodeid
    ):
        return True
    return False


def _is_flows_session_search_test(nodeid: str) -> bool:
    return nodeid.startswith("tests/flows/core/db/test_session_repository_search.py")


def _is_flows_tools_all_api_test(nodeid: str) -> bool:
    return "test_list_all_tools_includes_builtin_registry_tools" in nodeid


def _is_flows_variables_api_test(nodeid: str) -> bool:
    return nodeid.startswith("tests/flows/api/test_flows_variables.py")


def _is_flows_sessions_api_test(nodeid: str) -> bool:
    return nodeid.startswith("tests/flows/api/test_sessions_api.py")


def _is_flows_a2a_api_test(nodeid: str) -> bool:
    """A2A JSON-RPC через in-process ASGI: 1–3 полных MockLLM-прогона >5 с."""
    return nodeid.startswith("tests/flows/api/test_a2a.py")


def _is_google_workspace_emulator_test(nodeid: str) -> bool:
    """Google API emulator + ASGI credentials: изоляция ~7 с, глобальные 5 с — ложный timeout."""
    return nodeid.startswith(
        "tests/core/integrations/test_google_workspace_emulator_auth.py"
    )


def _is_frontend_team_act_as_test(nodeid: str) -> bool:
    return nodeid.startswith("tests/frontend/test_team_act_as.py")


def _is_frontend_public_search_session_test(nodeid: str) -> bool:
    return nodeid.startswith("tests/frontend/api/test_public_search_session.py")


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Timeout-политика по типам тестов. Никаких xdist_group: все тесты параллельны,
    изоляция достигается уникальными идентификаторами и parallel-safe контрактами.

    tryfirst=True обязателен: xdist remote.py тоже регистрирует
    pytest_collection_modifyitems. Наш хук должен выполниться ДО xdist,
    чтобы маркеры уже были видны.
    """
    for item in items:
        if item.get_closest_marker("real_taskiq"):
            if item.get_closest_marker("timeout") is None:
                # func_only=False: setup crm_client/rag_worker под WORKERS=10 и shared Postgres
                # регулярно >5s; глобальный pytest.ini timeout=5 иначе даёт ERROR на setup.
                item.add_marker(pytest.mark.timeout(180, func_only=False))
        elif _is_sync_db_test(item.nodeid):
            if item.get_closest_marker("timeout") is None:
                item.add_marker(pytest.mark.timeout(60, func_only=True))
        elif _is_rag_global_maintenance_test(item.nodeid):
            if item.get_closest_marker("timeout") is None:
                item.add_marker(pytest.mark.timeout(120, func_only=False))
        elif _is_crm_e2e_test(item.nodeid):
            existing_timeout = item.get_closest_marker("timeout")
            existing_seconds = _marker_timeout_seconds(existing_timeout)
            # pytest.ini timeout_func_only=true: маркер без func_only=False режет setup.
            # pytestmark timeout(20) на файле перекрывал 120с → FAILED/ERROR под -n10.
            already_ok = (
                existing_seconds is not None
                and existing_seconds >= 120
                and existing_timeout is not None
                and existing_timeout.kwargs.get("func_only") is False
            )
            if not already_ok:
                applied = (
                    120.0
                    if existing_seconds is None or existing_seconds < 120
                    else existing_seconds
                )
                _ensure_item_timeout(item, applied, func_only=False)
        elif _is_notification_ws_e2e_test(item.nodeid):
            if item.get_closest_marker("timeout") is None:
                item.add_marker(pytest.mark.timeout(120, func_only=False))
        elif _is_sandbox_runtime_test(item.nodeid):
            if item.get_closest_marker("timeout") is None:
                item.add_marker(pytest.mark.timeout(180, func_only=True))
        elif _is_files_s3_test(item.nodeid):
            if item.get_closest_marker("timeout") is None:
                # Chunked upload = несколько HTTP + MinIO + FGA company Check; под -n10 >5s.
                item.add_marker(pytest.mark.timeout(60, func_only=True))
        elif _is_flows_session_search_test(item.nodeid):
            if item.get_closest_marker("timeout") is None:
                item.add_marker(pytest.mark.timeout(60, func_only=True))
        elif _is_flows_tools_all_api_test(item.nodeid):
            if item.get_closest_marker("timeout") is None:
                item.add_marker(pytest.mark.timeout(60, func_only=True))
        elif _is_flows_variables_api_test(item.nodeid):
            if item.get_closest_marker("timeout") is None:
                item.add_marker(pytest.mark.timeout(60, func_only=True))
        elif _is_flows_sessions_api_test(item.nodeid):
            if item.get_closest_marker("timeout") is None:
                item.add_marker(pytest.mark.timeout(60, func_only=True))
        elif _is_flows_a2a_api_test(item.nodeid):
            if item.get_closest_marker("timeout") is None:
                item.add_marker(pytest.mark.timeout(60, func_only=True))
        elif _is_google_workspace_emulator_test(item.nodeid):
            if item.get_closest_marker("timeout") is None:
                item.add_marker(pytest.mark.timeout(30, func_only=True))
        elif _is_frontend_team_act_as_test(item.nodeid):
            if item.get_closest_marker("timeout") is None:
                item.add_marker(pytest.mark.timeout(30, func_only=True))
        elif _is_frontend_public_search_session_test(item.nodeid):
            if item.get_closest_marker("timeout") is None:
                item.add_marker(pytest.mark.timeout(60, func_only=True))

@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_call(item) -> Generator[None, object, object]:
    """
    Для real_taskiq: снимаем старый alarm в начале call и ставим новый
    с тем же faulthandler_timeout только на фазу call (тело теста).
    """
    if not item.get_closest_marker("real_taskiq") and not _is_sandbox_runtime_test(item.nodeid):
        return (yield)
    import faulthandler

    from _pytest.faulthandler import (
        fault_handler_stderr_fd_key,
        get_exit_on_timeout_config_value,
        get_timeout_config_value,
    )

    faulthandler.cancel_dump_traceback_later()
    timeout = get_timeout_config_value(item.config)
    if timeout > 0:
        stderr = item.config.stash[fault_handler_stderr_fd_key]
        exit_on = get_exit_on_timeout_config_value(item.config)
        faulthandler.dump_traceback_later(timeout, file=stderr, exit=exit_on)
    try:
        return (yield)
    finally:
        faulthandler.cancel_dump_traceback_later()


_FIRST_FAIL_DUMP = Path("/tmp/pytest-first-fail.txt")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]) -> Generator[None]:
    """xdist -x печатает traceback только после drain. Первый fail — сразу на диск."""
    _ = item
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or not report.failed or _FIRST_FAIL_DUMP.exists():
        return
    _FIRST_FAIL_DUMP.write_text(f"{report.nodeid}\n{report.longrepr}\n", encoding="utf-8")


def _skip_autouse_test_context(request: pytest.FixtureRequest) -> bool:
    """ASGI-клиенты с Bearer auth: контекст выставляет AuthMiddleware, не test_user.

    In-process ``*_container`` + HTTP в одном тесте: test_context нужен после
    ASGI (middleware restore внешнего Context). Не скипать.
    """
    direct_container_fixtures = (
        "crm_container",
        "flows_container",
        "worktracker_container",
        "wiki_container",
    )
    if any(name in request.fixturenames for name in direct_container_fixtures):
        return False
    asgi_client_fixtures = (
        "frontend_client",
        "flows_client",
        "crm_client",
        "worktracker_client",
        "office_client",
        "sync_client",
        "rag_client",
        "voice_client",
        "wiki_client",
        "wiki_client_member",
        "wiki_client_company2",
    )
    if any(name in request.fixturenames for name in asgi_client_fixtures):
        if "api" in request.node.nodeid:
            return True
        if any(
            name.startswith("auth_headers") or name.startswith("auth_token")
            for name in request.fixturenames
        ):
            return True
    return False


@pytest_asyncio.fixture(autouse=True)
async def test_context(request: pytest.FixtureRequest):
    """
    Тестовый Context с company AI override (make_test_company).

    Async autouse: contextvars должны жить в том же asyncio task, что и тест
    (flow.run / llm_node читают get_context). Sync-фикстура теряет Context
    при создании task для async-фикстур вроде google_api_emulator.

    Не применяется к API/ASGI тестам с Bearer auth (контекст — AuthMiddleware).
    """
    if _skip_autouse_test_context(request):
        yield None
        return
    from core.context import clear_context, set_context
    from core.models.context_models import Context
    from core.models.identity_models import User

    test_ctx = Context(
        user=User(user_id="test_user", name="Test User"),
        active_company=make_test_company(company_id="system", name="System"),
        session_id="test_session",
        channel="test",
        metadata={"user_id": "test_user", "email": "test@example.com", "grps": []},
    )
    set_context(test_ctx)
    yield test_ctx
    clear_context()


@pytest.fixture
def unique_id() -> str:
    """
    Уникальный ID для изоляции тестовых данных.
    Используется для создания уникальных имен сущностей в БД.
    """
    return str(uuid.uuid4())[:8]


@pytest.fixture(autouse=True)
def platform_test_scope() -> Generator[str, None, None]:
    """
    Уникальный test scope на каждый тест — адресная маршрутизация MockLLM.

    Sync-фикстура: биндит ``test_scope`` в лог-контекст главного потока
    xdist-воркера, поэтому каждая asyncio-задача теста (LLM-вызовы, kiq)
    наследует scope через copy-on-create contextvars. Дальше scope едет по
    платформенным рельсам: X-Test-Scope в HTTP/WS, label ``test_scope`` в
    TaskIQ (см. core/test_scope.py).
    """
    from core.logging import bind_log_context, unbind_log_context
    from core.test_scope import LOG_TEST_SCOPE

    scope = f"test_{uuid.uuid4().hex[:12]}"
    bind_log_context(**{LOG_TEST_SCOPE: scope})
    yield scope
    unbind_log_context(LOG_TEST_SCOPE)


@pytest.fixture(autouse=True)
def enforce_no_test_doubles(request: pytest.FixtureRequest) -> None:
    """Fail closed when a no_test_doubles test requests a known double fixture."""
    if request.node.get_closest_marker("no_test_doubles") is None:
        return
    forbidden = {
        "monkeypatch",
        "mock_context",
        "mock_llm",
        "mock_llm_capture",
        "mock_llm_redis",
        "mock_llm_with_queue",
        "mocker",
    }
    fixture_info = getattr(request.node, "_fixtureinfo", None)
    if fixture_info is None:
        return
    direct_fixture_names = set(getattr(fixture_info, "argnames", ()))
    requested = sorted(forbidden.intersection(direct_fixture_names))
    if requested:
        pytest.fail(f"no_test_doubles test requested forbidden fixtures: {requested}")


@pytest.fixture(autouse=True)
def _inject_test_scope_header(
    request: pytest.FixtureRequest,
    platform_test_scope: str,
) -> None:
    """
    Все httpx-клиенты тестового процесса несут заголовок ``X-Test-Scope``.

    Патчится ``build_request`` — единая точка сборки запроса для ASGI и
    реального HTTP транспорта. Сервисы читают заголовок в AccessLogMiddleware
    и прокидывают дальше (ServiceClient, A2A, TaskIQ labels).
    """
    if request.node.get_closest_marker("no_test_doubles"):
        return

    import httpx

    from core.test_scope import TEST_SCOPE_HEADER

    monkeypatch = request.getfixturevalue("monkeypatch")
    if not isinstance(monkeypatch, pytest.MonkeyPatch):
        raise TypeError("monkeypatch fixture must be pytest.MonkeyPatch")

    original_async_build_request = httpx.AsyncClient.build_request
    original_sync_build_request = httpx.Client.build_request

    def async_build_request_with_scope(self, *args: Any, **kwargs: Any) -> httpx.Request:
        http_request = original_async_build_request(self, *args, **kwargs)
        if TEST_SCOPE_HEADER not in http_request.headers:
            http_request.headers[TEST_SCOPE_HEADER] = platform_test_scope
        return http_request

    def sync_build_request_with_scope(self, *args: Any, **kwargs: Any) -> httpx.Request:
        http_request = original_sync_build_request(self, *args, **kwargs)
        if TEST_SCOPE_HEADER not in http_request.headers:
            http_request.headers[TEST_SCOPE_HEADER] = platform_test_scope
        return http_request

    monkeypatch.setattr(httpx.AsyncClient, "build_request", async_build_request_with_scope)
    monkeypatch.setattr(httpx.Client, "build_request", sync_build_request_with_scope)


@pytest.fixture
def mock_context() -> Context:
    """
    Фикстура для мок Context в тестах.
    Используется когда тесты вызывают process_flow_task напрямую, минуя middleware.
    """
    return Context(
        user=User(user_id="test_user", name="Test User"),
        active_company=make_test_company(company_id="system", name="System"),
        session_id="test_session",
        channel="test",
        metadata={"user_id": "test_user", "email": "test@example.com", "grps": []},
    )


@pytest.fixture
def mock_llm() -> MockLLM:
    """
    Фикстура MockLLM.

    Единственный мок в тестах - имитация ответов LLM.
    Все остальное (state, flow, nodes, tools) - реальные объекты.
    """
    return setup_mock_responses(default_response="Test response")


@pytest.fixture
def mock_llm_with_queue():
    """
    Фабрика для создания MockLLM с очередью ответов.
    Для локального выполнения (sync_tools).

    Пример:
        def test_flow(mock_llm_with_queue, sync_tools):
            mock = mock_llm_with_queue([
                "First response",
                {"type": "tool_call", "tool": "calculator", "args": {"expression": "2+2"}},
                "Final answer"
            ])
    """

    def _factory(responses: List[Any]) -> MockLLM:
        return setup_mock_responses(response_queue=responses)

    return _factory


@pytest_asyncio.fixture
async def mock_llm_capture(container, platform_test_scope):
    """
    Журнал LLM-вызовов MockLLM за текущий тест; возвращает callable-читатель.

    `MockLLM` в любом процессе (granian, TaskIQ workers, локальные вызовы)
    пишет каждый вызов с активным test scope в `mock_llm:capture:<scope>`.
    Запись содержит `model`, `messages` (role + plain text + parts),
    `tools`, `response_format`. Никаких моков продакшна и monkeypatch.

    Пример:
        async def test_smth(mock_llm_capture, mock_llm_redis):
            await mock_llm_redis([{"type": "text", "content": "..."}])
            ...  # запускаем сценарий
            calls = await mock_llm_capture()  # все вызовы LLM в порядке прихода
    """
    from core.clients.llm.mock import (
        read_mock_llm_capture,
        start_mock_llm_capture,
        stop_mock_llm_capture,
    )

    _ = await start_mock_llm_capture(container.redis_client, platform_test_scope)

    async def _read():
        return await read_mock_llm_capture(container.redis_client, platform_test_scope)

    try:
        yield _read
    finally:
        await stop_mock_llm_capture(container.redis_client, platform_test_scope)


@pytest_asyncio.fixture
async def mock_llm_redis(container, platform_test_scope):
    """Очередь mock-ответов LLM, адресованная test scope текущего теста.

    MockLLM в любом процессе снимает ответы строго из
    `mock_llm:responses:<scope>` по scope из своего request-контекста —
    параллельные тесты не пересекаются.

    Пример:
        async def test_integration(mock_llm_redis):
            await mock_llm_redis([
                {"type": "text", "content": "Response"}
            ])
    """
    from core.clients.llm.mock import clear_mock_responses_redis, setup_mock_responses_redis

    async def _factory(responses: List[Any]) -> None:
        await setup_mock_responses_redis(
            container.redis_client, responses, test_scope=platform_test_scope
        )

    yield _factory
    await clear_mock_responses_redis(container.redis_client, test_scope=platform_test_scope)


@pytest.fixture
def state():
    """
    Реальный пустой state для тестов.
    Возвращает ExecutionState с минимальными обязательными полями.
    """
    from core.state import ExecutionState

    return ExecutionState(
        task_id="test-task-id",
        context_id="test-context-id",
        user_id="test-user",
        session_id="test-agent:test-context-id",
    )


@pytest.fixture
def state_with_content():
    """
    Реальный state с content.
    """
    from core.state import ExecutionState

    return ExecutionState(
        task_id="test-task-id",
        context_id="test-context-id",
        user_id="test-user",
        session_id="test-agent:test-context-id",
        content="Test user input",
    )


@pytest.fixture
def make_test_state():
    """
    Фабрика для создания ExecutionState из dict в тестах.
    Автоматически добавляет обязательные поля (task_id, context_id, user_id).

    Пример:
        def test_something(make_test_state):
            state = make_test_state(content="hello", user={"name": "John"})
            result = await node.run(state)
    """
    from core.state import ExecutionState

    def _make_state(**kwargs: Any) -> ExecutionState:
        defaults: dict[str, Any] = {
            "task_id": "test-task-id",
            "context_id": "test-context-id",
            "user_id": "test-user",
            "session_id": "test-agent:test-context-id",
        }
        defaults.update(kwargs)
        if "context_id" in kwargs and "session_id" not in kwargs:
            defaults["session_id"] = f"test-agent:{kwargs['context_id']}"
        return ExecutionState(**defaults)

    return _make_state


@pytest.fixture(autouse=True)
def reset_mock_llm(request: pytest.FixtureRequest):
    """
    Автоматический сброс MockLLM перед каждым тестом.
    Обеспечивает изоляцию тестов.
    """
    yield
    if request.node.get_closest_marker("no_test_doubles"):
        return
    mock = get_global_mock_llm("mock-gpt-4")
    if mock:
        mock.reset()


@pytest.fixture(autouse=True)
def sync_tools(request: pytest.FixtureRequest):
    """
    Выполняет tools и agent tasks синхронно без TaskIQ worker.

    autouse=True - применяется ко всем тестам автоматически.
    Это обеспечивает единообразное поведение во всех тестах.

    Для тестов реального TaskIQ worker используйте маркер:
        @pytest.mark.real_taskiq

    Патчит:
    - ``core.tasks.enqueue`` (и локальные импорты ``enqueue`` в producer-модулях) —
      выполняет задачи синхронно по ``TaskSpec``

    Redis Pub/Sub не подменяется: стриминг идёт через реальный Redis из контейнера.
    """
    if request.node.get_closest_marker("no_test_doubles") or request.node.get_closest_marker(
        "real_taskiq"
    ):
        yield
        return
    monkeypatch = request.getfixturevalue("monkeypatch")
    if not isinstance(monkeypatch, pytest.MonkeyPatch):
        raise TypeError("monkeypatch fixture must be pytest.MonkeyPatch")
    import apps.crm.services.entity_service as crm_entity_service_module
    import apps.crm.services.task_service as crm_task_service_module
    import apps.crm_worker.tasks.analysis_tasks as crm_analysis_tasks
    import apps.crm_worker.tasks.daily_summary_tasks as crm_daily_summary_tasks
    import apps.crm_worker.tasks.draft_repair_tasks as crm_draft_repair_tasks
    import apps.crm_worker.tasks.knowledge_import_tasks as crm_knowledge_import_tasks
    import apps.crm_worker.tasks.namespace_integration_tasks as crm_namespace_integration_tasks
    import apps.crm_worker.tasks.note_markdown_tasks as crm_note_markdown_tasks
    import apps.flows.src.api.v1.company as flows_company_module
    import apps.flows.src.api.v1.tasks as flows_tasks_api_module
    import apps.flows.src.channels.a2a as flows_a2a_channel_module
    import apps.flows.src.channels.base as flows_base_channel_module
    import apps.flows.src.services.employee_inbox_service as flows_employee_inbox_module
    import apps.flows.src.services.handoff_orchestrator_service as flows_handoff_orchestrator_module
    import apps.flows.src.services.hitl_work_item_service as flows_hitl_work_item_module
    import apps.flows.src.triggers.executor as flows_trigger_executor_module
    import apps.idle_worker.tasks.push_notification_tasks as push_notification_tasks
    import apps.office.services.catalog_rag_index_service as office_catalog_rag_index_module
    import apps.rag.api.documents as rag_documents_module
    import apps.rag_worker.tasks.indexing_tasks as rag_indexing_tasks
    import apps.sync.realtime.handlers as sync_handlers_module
    import apps.sync.realtime.notification_tasks as sync_notification_tasks
    import apps.sync.realtime.operations as sync_operations_module
    import apps.sync.realtime.tasks as sync_realtime_tasks
    import core.mail.enqueue as mail_enqueue_module
    import core.tasks.kicker as task_kicker_module
    from apps.crm_worker.tasks.task_names import (
        CRM_FORMAT_NOTE_DESCRIPTION_MARKDOWN,
        CRM_PROCESS_NOTE,
        CRM_REBUILD_DAILY_SUMMARY,
        CRM_REBUILD_PERIOD_SUMMARY,
        CRM_REPAIR_NOTE_ANALYSIS_DRAFT,
        CRM_RUN_KNOWLEDGE_IMPORT,
        CRM_RUN_NAMESPACE_INTEGRATION_JOB,
    )
    from apps.flows.src.tasks import (
        company_init_tasks,
        flow_tasks,
        llm_tasks,
        node_tasks,
        scheduled_tasks,
        tool_tasks,
    )
    from apps.flows.src.tasks.task_names import (
        TASK_EXECUTE_NODE,
        TASK_EXECUTE_SCHEDULED,
        TASK_EXECUTE_TOOL,
        TASK_INIT_COMPANY_RESOURCES,
        TASK_INVOKE_LLM,
        TASK_PROCESS_FLOW,
    )
    from apps.idle_worker.tasks.task_names import (
        TASK_PUSH_CONFIG_DELETE,
        TASK_PUSH_CONFIG_GET,
        TASK_PUSH_CONFIG_LIST,
        TASK_PUSH_CONFIG_SET,
        TASK_PUSH_NOTIFICATION_SEND,
        TASK_SEND_TASK_COMPLETED,
        TASK_SEND_TASK_FAILED,
        TASK_SEND_TASK_INPUT_REQUIRED,
        TASK_SEND_TASK_UPDATE,
    )
    from apps.rag_worker.tasks.task_names import (
        RAG_INDEX_DOCUMENT_S3,
        RAG_INDEX_OFFICE_CATALOG,
    )
    from apps.sync.realtime.task_names import (
        DELIVER_CHANNEL_MESSAGE_NOTIFICATION,
        DELIVER_SYNC_MENTION_NOTIFICATION,
        SYNC_AGGREGATE_CALL_TRANSCRIPT,
        SYNC_FINALIZE_RECORDING,
        SYNC_SPEECH_TO_CHAT_POLL,
        SYNC_TRANSCRIBE_AUDIO_MESSAGE,
        SYNC_TRANSCRIBE_VIDEO_MESSAGE,
    )
    from core.mail.task_names import (
        MAIL_ARCHIVE,
        MAIL_DELETE,
        MAIL_IDLE_SUPERVISOR,
        MAIL_MARK_SEEN,
        MAIL_MARK_UNSEEN,
        MAIL_MOVE,
        MAIL_RAG_INDEX,
        MAIL_SEND,
        MAIL_STAR,
        MAIL_SYNC_BINDING,
        MAIL_SYNC_TICK,
        MAIL_TRASH,
    )
    from core.tasks.registry import TaskSpec, get_task_spec

    class SyncTaskResult:
        """Имитация результата TaskIQ task."""

        def __init__(self, result=None, error=None):
            self._result = result
            self.is_err = error is not None
            self.return_value = result
            self.error = error
            self.task_id = f"sync-task-{uuid.uuid4().hex}"

        async def wait_result(self):
            return self

    async def sync_tool_kiq(tool_id, args, state):
        """Выполняет tool синхронно."""
        from core.context import get_context

        ctx = get_context()
        context_data = ctx.to_dict() if ctx is not None else None
        try:
            result = await tool_tasks.execute_tool(tool_id, args, state, context_data=context_data)
            return SyncTaskResult(result)
        except Exception as exc:
            return SyncTaskResult(error=exc)

    async def sync_agent_kiq(**kwargs):
        """Выполняет agent task синхронно."""
        from core.context import get_context, set_context

        saved_context = get_context()
        try:
            if "context_data" not in kwargs:
                mock_ctx = Context(
                    user=User(user_id="test_user", name="Test User"),
                    active_company=make_test_company(company_id="system", name="System"),
                    session_id="test_session",
                    channel="test",
                    metadata={"user_id": "test_user", "email": "test@example.com", "grps": []},
                )
                kwargs["context_data"] = mock_ctx.model_dump()
            result = await flow_tasks.process_flow_task(**kwargs)
            return SyncTaskResult(result)
        except Exception as exc:
            return SyncTaskResult(error=exc)
        finally:
            if saved_context:
                set_context(saved_context)

    async def _sync_call(task_func, *args, **kwargs):
        try:
            return SyncTaskResult(await task_func(*args, **kwargs))
        except Exception as exc:
            return SyncTaskResult(error=exc)

    crm_background_task_names = frozenset(
        {
            CRM_REBUILD_DAILY_SUMMARY,
            CRM_REBUILD_PERIOD_SUMMARY,
        }
    )

    def _log_background_task_failure(task: asyncio.Task[object]) -> None:
        from core.logging import get_logger

        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            get_logger(__name__).error(
                "sync_tools.background_task_failed",
                task_name=task.get_name(),
                exc_info=exc,
            )

    async def sync_send_task_update_kiq(task_id, context_id, state, message=None, is_final=False):
        """Выполняет send_task_update синхронно."""
        result = await push_notification_tasks.send_task_update(
            task_id, context_id, state, message, is_final
        )
        return SyncTaskResult(result)

    async def sync_send_webhook_kiq(url, payload, token=None, credentials=None):
        """Выполняет send_webhook синхронно. Ошибки игнорируются как в реальном TaskIQ с ретраями."""
        try:
            result = await push_notification_tasks.send_webhook(url, payload, token, credentials)
            return SyncTaskResult(result)
        except Exception:
            return SyncTaskResult({"success": False})

    async def _mail_task_ack(*args, **kwargs):
        _ = (args, kwargs)
        return None

    task_name_handlers = {
        TASK_PROCESS_FLOW: sync_agent_kiq,
        TASK_EXECUTE_TOOL: sync_tool_kiq,
        TASK_EXECUTE_NODE: node_tasks.execute_node,
        TASK_EXECUTE_SCHEDULED: scheduled_tasks.execute_scheduled_task,
        TASK_INVOKE_LLM: llm_tasks.invoke_llm,
        TASK_INIT_COMPANY_RESOURCES: company_init_tasks.init_company_resources,
        TASK_SEND_TASK_UPDATE: sync_send_task_update_kiq,
        TASK_SEND_TASK_COMPLETED: push_notification_tasks.send_task_completed,
        TASK_SEND_TASK_FAILED: push_notification_tasks.send_task_failed,
        TASK_SEND_TASK_INPUT_REQUIRED: push_notification_tasks.send_task_input_required,
        TASK_PUSH_NOTIFICATION_SEND: sync_send_webhook_kiq,
        TASK_PUSH_CONFIG_SET: push_notification_tasks.set_config,
        TASK_PUSH_CONFIG_GET: push_notification_tasks.get_config,
        TASK_PUSH_CONFIG_LIST: push_notification_tasks.list_configs,
        TASK_PUSH_CONFIG_DELETE: push_notification_tasks.delete_config,
        CRM_PROCESS_NOTE: crm_analysis_tasks.process_note_task,
        CRM_REPAIR_NOTE_ANALYSIS_DRAFT: crm_draft_repair_tasks.repair_note_analysis_draft_task,
        CRM_FORMAT_NOTE_DESCRIPTION_MARKDOWN: crm_note_markdown_tasks.format_note_description_markdown_task,
        CRM_RUN_KNOWLEDGE_IMPORT: crm_knowledge_import_tasks.run_knowledge_import_task,
        CRM_RUN_NAMESPACE_INTEGRATION_JOB: crm_namespace_integration_tasks.run_namespace_integration_job,
        CRM_REBUILD_DAILY_SUMMARY: crm_daily_summary_tasks.rebuild_daily_summary_task,
        CRM_REBUILD_PERIOD_SUMMARY: crm_daily_summary_tasks.rebuild_period_summary_task,
        SYNC_TRANSCRIBE_AUDIO_MESSAGE: sync_realtime_tasks.sync_transcribe_audio_message_task,
        SYNC_TRANSCRIBE_VIDEO_MESSAGE: sync_realtime_tasks.sync_transcribe_video_message_task,
        SYNC_AGGREGATE_CALL_TRANSCRIPT: sync_realtime_tasks.sync_aggregate_call_transcript_task,
        SYNC_FINALIZE_RECORDING: sync_realtime_tasks.sync_finalize_recording_task,
        SYNC_SPEECH_TO_CHAT_POLL: sync_realtime_tasks.sync_speech_to_chat_poll_task,
        DELIVER_CHANNEL_MESSAGE_NOTIFICATION: (
            sync_notification_tasks.deliver_channel_message_notification
        ),
        DELIVER_SYNC_MENTION_NOTIFICATION: (
            sync_notification_tasks.deliver_sync_mention_notification
        ),
        RAG_INDEX_DOCUMENT_S3: rag_indexing_tasks.index_rag_document_s3_task,
        RAG_INDEX_OFFICE_CATALOG: rag_indexing_tasks.index_office_catalog_task,
        # Mail worker tasks требуют IdleWorkerContainer + IMAP port теста.
        # Offline-тесты бьют MailService напрямую; worker path — в
        # test_mail_complete_client_taskiq с patched get_container.
        # Здесь только ack, чтобы enqueue не падал на «неизвестный task».
        MAIL_SYNC_TICK: _mail_task_ack,
        MAIL_SYNC_BINDING: _mail_task_ack,
        MAIL_MARK_SEEN: _mail_task_ack,
        MAIL_MARK_UNSEEN: _mail_task_ack,
        MAIL_SEND: _mail_task_ack,
        MAIL_MOVE: _mail_task_ack,
        MAIL_TRASH: _mail_task_ack,
        MAIL_ARCHIVE: _mail_task_ack,
        MAIL_DELETE: _mail_task_ack,
        MAIL_STAR: _mail_task_ack,
        MAIL_RAG_INDEX: _mail_task_ack,
        MAIL_IDLE_SUPERVISOR: _mail_task_ack,
    }

    async def sync_enqueue(
        task,
        *args,
        priority=None,
        override_request_id=None,
        override_trace_id=None,
        service_name=None,
        background_kind=None,
        extra_labels=None,
        **kwargs,
    ):
        _ = (
            priority,
            override_request_id,
            override_trace_id,
            service_name,
            background_kind,
            extra_labels,
        )
        spec = get_task_spec(task) if not isinstance(task, TaskSpec) else task
        handler = task_name_handlers.get(spec)
        if handler is None:
            # Lookup by name for string-keyed callers
            handler = next(
                (h for s, h in task_name_handlers.items() if s.name == spec.name),
                None,
            )
        if handler is None:
            raise AssertionError(f"Неизвестный TaskIQ task: {spec.name!r}")
        if handler is sync_agent_kiq:
            return await sync_agent_kiq(**kwargs)
        if handler is sync_tool_kiq:
            return await sync_tool_kiq(*args, **kwargs)
        if handler is sync_send_task_update_kiq:
            return await sync_send_task_update_kiq(*args, **kwargs)
        if handler is sync_send_webhook_kiq:
            return await sync_send_webhook_kiq(*args, **kwargs)
        if spec in crm_background_task_names:
            bg_task = asyncio.create_task(
                handler(*args, **kwargs),
                name=spec.name,
            )
            bg_task.add_done_callback(_log_background_task_failure)
            return SyncTaskResult(result=None)
        return await _sync_call(handler, *args, **kwargs)

    for module in (
        task_kicker_module,
        mail_enqueue_module,
        flows_base_channel_module,
        flows_handoff_orchestrator_module,
        flows_a2a_channel_module,
        flows_hitl_work_item_module,
        flows_employee_inbox_module,
        flows_trigger_executor_module,
        flows_tasks_api_module,
        flows_company_module,
        crm_task_service_module,
        crm_entity_service_module,
        sync_operations_module,
        sync_handlers_module,
        sync_realtime_tasks,
        rag_documents_module,
        office_catalog_rag_index_module,
        rag_indexing_tasks,
    ):
        monkeypatch.setattr(module, "enqueue", sync_enqueue)
    yield None


def _code_runner_available() -> bool:
    """Проверяет доступность code_runner_python через HTTP health-check."""
    import httpx

    try:
        response = httpx.get(
            "http://127.0.0.1:9017/health",
            timeout=1.0,
        )
        return response.status_code == 200
    except Exception:
        return False


SUPPRESSED_CODE_RUNNER_TESTS: set[str] = set()


@pytest_asyncio.fixture(autouse=True)
async def skip_if_code_runner_unavailable(request: pytest.FixtureRequest) -> None:
    """Пропускает тесты, требующие code_runner, если sandbox-сервисы недоступны.

    Маркеры: @pytest.mark.requires_code_runner — обязательный маркер для skip.
    """
    marker = request.node.get_closest_marker("requires_code_runner")
    if marker is None:
        return
    test_id = request.node.nodeid
    if test_id in SUPPRESSED_CODE_RUNNER_TESTS:
        pytest.skip("code_runner недоступен (проверено ранее). Запустите make app")
    if not _code_runner_available():
        SUPPRESSED_CODE_RUNNER_TESTS.add(test_id)
        pytest.skip("code_runner_python недоступен. Запустите make app")


@pytest_asyncio.fixture(scope="session")
async def app(taskiq_worker, crm_worker):
    """
    Реальное FastAPI приложение с lifespan.
    Загружает flows, инициализирует контейнер.
    Зависит от taskiq_worker/crm_worker — воркеры стека должны быть готовы.

    scope="session" - приложение поднимается один раз на все тесты.
    При pytest-xdist каждый gw-worker поднимает свой lifespan независимо.

    ВАЖНО: Scheduler НЕ запускается автоматически! Тесты которым нужен scheduler
    должны явно использовать фикстуру taskiq_scheduler.
    """
    _ = taskiq_worker, crm_worker
    async with fastapi_app.router.lifespan_context(fastapi_app):
        yield fastapi_app


@pytest_asyncio.fixture(scope="session")
async def client(app, auth_token_system):
    """
    Async HTTP клиент для agents API тестов.
    Поднимает реальный сервис через ASGI.
    Использует авторизацию с компанией "system" т.к. агенты загружаются в system.

    scope="session" - клиент создается один раз на все тесты.
    """
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {auth_token_system}"}
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as ac:
        yield ac


@pytest.fixture(scope="session")
def container(app):
    """
    DI контейнер agents приложения.
    Зависит от app чтобы lifespan уже отработал.
    """
    from apps.flows.src.container import get_container

    c = get_container()
    c.use_worker = False
    return c


@pytest.fixture
def worktracker_container():
    """Worktracker DI: держит autouse test_context при HTTP-клиентах worktracker."""
    from apps.worktracker.container import get_worktracker_container

    return get_worktracker_container()


@pytest.fixture(scope="session")
def frontend_container(frontend_app):
    """
    DI контейнер frontend приложения.
    Используется для тестов frontend API.
    Зависит от frontend_app чтобы использовать тот же контейнер.

    scope="session" - контейнер создается один раз на все тесты.
    """
    from apps.frontend.container import get_container as get_frontend_container

    return get_frontend_container()


@pytest_asyncio.fixture
async def storage(container):
    """
    Storage для тестов репозиториев.
    Использует контейнер приложения для получения storage.
    """
    return container.storage


@pytest_asyncio.fixture
async def storage_shared(container):
    """
    Shared Storage для тестов глобальных репозиториев.
    Используется для is_global=True репозиториев.
    """
    return container.shared_storage


@pytest.fixture(scope="session")
def inline_tools():
    """
    Inline tool конфиги для тестов.

    Возвращает dict с готовыми конфигами встроенных tools.
    Используй вместо строковых ссылок типа "calculator".
    """
    return {
        "calculator": {
            "tool_id": "calculator",
            "description": "Вычисляет математические выражения",
            "parameters_schema": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "Математическое выражение"}
                },
                "required": ["expression"],
            },
            "code": "async def execute(args: dict, state: dict = None):\n    import ast\n    import operator\n    expr = args.get('expression', '0')\n    if not isinstance(expr, str):\n        expr = str(expr)\n    ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}\n    def _eval(node):\n        if isinstance(node, ast.Expression): return _eval(node.body)\n        if isinstance(node, ast.Constant): return node.value\n        if isinstance(node, ast.BinOp): return ops[type(node.op)](_eval(node.left), _eval(node.right))\n        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub): return -_eval(node.operand)\n        raise ValueError(f\"Unsupported: {type(node)}\")\n    return f\"Результат: {_eval(ast.parse(expr, mode='eval'))}\"\n",
        },
        "finish": {
            "tool_id": "finish",
            "description": "Завершает агента и возвращает финальный ответ",
            "parameters_schema": {
                "type": "object",
                "properties": {"answer": {"type": "string", "description": "Финальный ответ"}},
                "required": ["answer"],
            },
            "code": "async def execute(args: dict, state: dict = None):\n    return args.get('answer', '')",
            "react_role": "exit",
        },
        "ask_user": {
            "tool_id": "ask_user",
            "description": "Задает вопрос пользователю",
            "parameters_schema": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "Вопрос для пользователя"}
                },
                "required": ["question"],
            },
            "code": 'async def execute(args: dict, state: dict = None):\n    q = args.get("question")\n    if not q or not str(q).strip():\n        raise ValueError("ask_user: question обязателен")\n    raise FlowInterrupt(question=str(q).strip())\n',
        },
        "reason": {
            "tool_id": "reason",
            "description": "Рассуждение агента",
            "parameters_schema": {
                "type": "object",
                "properties": {"thought": {"type": "string", "description": "Ход мысли"}},
                "required": ["thought"],
            },
            "code": "async def execute(args: dict, state: dict = None):\n    return args.get('thought', '')",
            "react_role": "reason",
        },
    }


@pytest_asyncio.fixture
async def flows_app(app):
    """
    Тот же экземпляр agents-приложения, что и ``app`` (единый lifespan в фикстуре ``app``).

    Раньше ``flows_app`` отдавал приложение без lifespan: HTTP через ``flows_client`` мог
    выполняться до ``container``/``app``, а TaskIQ и Redis для flows оставались в частично
    инициализированном состоянии относительно сессии тестов.
    """
    yield app


@pytest_asyncio.fixture(scope="session")
async def frontend_app():
    """
    FastAPI приложение frontend сервиса для интеграционных тестов.

    Использует:
    - Реальный frontend app
    - Тестовую БД (Redis, Postgres)
    - С lifespan context для правильной инициализации

    scope="session" - приложение создается один раз на все тесты.
    """
    from apps.frontend.main import app

    async with app.router.lifespan_context(app):
        yield app


@pytest_asyncio.fixture
async def flows_client(flows_app):
    """
    HTTP клиент для тестирования agents API.

    Пример:
        async def test_api(flows_client):
            response = await flows_client.get("/flows/api/health")
            assert response.status_code == 200
    """
    async with AsyncClient(
        transport=ASGITransport(app=flows_app), base_url="http://testserver",
        headers={"Host": "humanitec.ru"},
    ) as client:
        yield client


@pytest_asyncio.fixture
async def frontend_client(frontend_app):
    """
    HTTP клиент для тестирования frontend API.

    Пример:
        async def test_api(frontend_client):
            response = await frontend_client.get("/api/health")
            assert response.status_code == 200
    """
    async with AsyncClient(
        transport=ASGITransport(app=frontend_app),
        base_url="http://humanitec.ru",
        follow_redirects=True,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def frontend_client_with_auth(frontend_app, auth_token):
    """
    HTTP клиент с предустановленным auth token в cookies.

    Пример:
        async def test_api(frontend_client_with_auth):
            response = await frontend_client_with_auth.get("/api/something")
            assert response.status_code == 200
    """
    async with AsyncClient(
        transport=ASGITransport(app=frontend_app),
        base_url="http://testserver",
        cookies={"auth_token": auth_token},
        follow_redirects=True,
        headers={"Host": "humanitec.ru"},
    ) as client:
        yield client


@pytest_asyncio.fixture
async def test_agent(app, container):
    """
    Создает тестового агента для API тестов.

    Пример:
        async def test_api(frontend_client, test_agent):
            # test_agent.flow_id == "test_agent"
    """
    from apps.flows.src.models.flow_config import FlowConfig

    agent = FlowConfig(
        flow_id="test_agent",
        name="Test Agent",
        entry="main",
        nodes={"main": {"type": "llm_node", "prompt": "Test prompt", "next": None}},
    )
    await container.flow_repository.set(agent)
    yield agent
    await container.flow_repository.delete("test_agent")


@pytest_asyncio.fixture
async def test_agent_fixture(app, unique_id):
    """
    Создает уникального тестового агента с автоматической очисткой.

    Гарантирует удаление агента даже если тест упал.

    Пример:
        async def test_something(test_agent_fixture):
            flow_id, container = test_agent_fixture
            # Создайте агента с flow_id
            # Очистка произойдёт автоматически
    """
    from apps.flows.src.container import get_container

    container = get_container()
    flow_ids_to_cleanup = []

    def register_agent(flow_id: str):
        """Регистрирует flow_id для последующей очистки."""
        flow_ids_to_cleanup.append(flow_id)
        return flow_id

    yield (register_agent, container)
    for flow_id in flow_ids_to_cleanup:
        try:
            await container.flow_repository.delete(flow_id)
        except Exception:
            pass


@pytest_asyncio.fixture
async def auth_token(frontend_container):
    """
    Создает авторизованного пользователя с компанией и возвращает токен.

    Пример:
        async def test_auth(frontend_client, auth_token):
            response = await frontend_client.get(
                "/api/companies/me",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
    """
    import uuid

    from core.authz.company_sync import sync_company_member_roles
    from core.models.identity_models import Company, User
    from core.utils.tokens import get_token_service

    user_id = f"test_user_{uuid.uuid4().hex[:8]}"
    company_id = f"test_company_{uuid.uuid4().hex[:8]}"
    company_subdomain = f"test-{uuid.uuid4().hex[:8]}"
    company = Company(
        company_id=company_id,
        name="Test Company",
        subdomain=company_subdomain,
        owner_user_id=user_id,
        members={user_id: ["owner", "admin"]},
    )
    await frontend_container.company_repository.set(company)
    await frontend_container.subdomain_repository.set_mapping(company_subdomain, company_id)

    # Сохраняем пользователя ДО обновления system_company.members,
    # чтобы middleware CompanyResolver видел user.companies с "system" при любом порядке выполнения.
    user = User(
        user_id=user_id,
        name="Test User",
        emails=[f"{user_id}@test.com"],
        companies={company_id: ["owner", "admin"], "system": ["admin"]},
        active_company_id=company_id,
    )
    await frontend_container.user_repository.set(user)

    system_company = await frontend_container.company_repository.get("system")
    if system_company is None:
        system_company = Company(
            company_id="system",
            name="System",
            subdomain="system",
            owner_user_id=user_id,
            members={user_id: ["admin"]},
        )
        await frontend_container.company_repository.set(system_company)
        await frontend_container.subdomain_repository.set_mapping("system", "system")
    else:
        if user_id not in system_company.members:
            system_company.members[user_id] = ["admin"]
            await frontend_container.company_repository.set(system_company)

    await sync_company_member_roles(
        frontend_container.authz_service,
        company_id=company_id,
        user_id=user_id,
        roles=["owner", "admin"],
    )
    await sync_company_member_roles(
        frontend_container.authz_service,
        company_id="system",
        user_id=user_id,
        roles=["admin"],
    )

    token_service = get_token_service()
    token = token_service.create_token(user_id, company_id=company_id)
    return token


@pytest_asyncio.fixture
async def auth_headers(auth_token):
    """
    Фикстура для авторизационных заголовков.
    Middleware поддерживает как cookies, так и Authorization header.

    Пример:
        async def test_api(frontend_client, auth_headers):
            response = await frontend_client.get(
                "/api/something",
                headers=auth_headers
            )
    """
    return {"Authorization": f"Bearer {auth_token}"}


@pytest_asyncio.fixture
async def rag_provider_pgvector():
    """
    Реальный pgvector провайдер для тестов.

    Использует PostgreSQL с расширением pgvector для хранения embeddings.
    """
    from apps.rag.container import get_rag_container
    from core.config import get_settings
    from core.config.models import RAGProviderConfig
    from core.files.reader.service import FileReader
    from core.rag.embedding_runtime import resolve_rag_embedding_runtime
    from core.rag.providers.pgvector_provider import PgVectorProvider

    settings = get_settings()
    config = RAGProviderConfig(
        db_url=os.environ.get(
            "DATABASE__RAG_URL",
            "postgresql+asyncpg://platform_user:admin@localhost:54322/platform_rag",
        ),
    )
    embedding_runtime = resolve_rag_embedding_runtime(
        settings.rag.embedding, settings.llm, settings.provider_litserve
    )
    provider = PgVectorProvider(config, embedding_runtime)
    FileReader.configure_asset_persist(get_rag_container().files_service)
    yield provider


@pytest.fixture
def unique_namespace_name(unique_id):
    """
    Уникальное имя namespace для изоляции тестов.

    Пример:
        def test_namespace(rag_client, unique_namespace_name):
            response = await rag_client.post(
                "/rag/api/v1/namespaces",
                json={"name": unique_namespace_name}
            )
    """
    return f"test_namespace_{unique_id}"


@pytest_asyncio.fixture(scope="session", autouse=True)
async def ensure_minio_bucket():
    """
    Гарантирует бакет test-bucket на тестовом MinIO (порт 19002, docker-compose-test).

    Должен совпадать с S3__BUCKETS__TEST-BUCKET__ENDPOINT_URL в этом conftest:
    иначе бакет создаётся на одном хосте, а приложение (conf.json с 19001) пишет в другой — NoSuchBucket.
    """
    try:
        import aioboto3
        from botocore.exceptions import ClientError

        session = aioboto3.Session()
        async with session.client(
            "s3",
            endpoint_url="http://localhost:19002",
            aws_access_key_id="minioadmin",
            aws_secret_access_key="minioadmin",
        ) as client:
            try:
                await client.head_bucket(Bucket="test-bucket")
            except ClientError:
                await client.create_bucket(Bucket="test-bucket")
                print("Created test-bucket in MinIO (localhost:19002)")
    except Exception as e:
        print(f"Failed to ensure MinIO bucket test-bucket on localhost:19002: {e}")
    yield


@pytest.fixture(scope="session")
def test_a2a_sample():
    """
    URL тестового A2A sample из docker-compose-test.yaml.
    Контейнер слушает 8005, на хосте проброшен порт 18052.
    """
    yield "http://localhost:18052"


@pytest_asyncio.fixture
async def test_node_in_db(container, unique_id):
    """Создает тестовую ноду в БД для валидации."""
    from apps.flows.src.models import NodeConfig
    from apps.flows.src.models.enums import NodeType

    node_id = f"test_node_{unique_id}"
    node = NodeConfig(
        node_id=node_id, name="Test Node", type=NodeType.LLM_NODE, prompt="Test prompt"
    )
    await container.node_repository.set(node)
    yield node_id
    await container.node_repository.delete(node_id)


@pytest_asyncio.fixture
async def test_agent_for_tool(container, unique_id):
    """Создает тестового агента для использования как tool."""
    from apps.flows.src.models import FlowConfig

    flow_id = f"test_agent_{unique_id}"
    agent = FlowConfig(
        flow_id=flow_id,
        name="Test Agent as Tool",
        entry="main",
        nodes={"main": {"type": "code", "code": "async def run(args, state):\n    return state"}},
    )
    await container.flow_repository.set(agent)
    yield flow_id
    await container.flow_repository.delete(flow_id)
