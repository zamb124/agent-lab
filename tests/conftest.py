"""
Фикстуры для тестов platform.

ПРАВИЛО: Мок только LLM. Все остальное - реальные объекты.
Tools автоматически работают в mock режиме (TESTING=true).
TaskIQ worker запускается автоматически для тестов.

Фикстуры сервисов и клиентов загружаются из tests/fixtures/ через pytest_plugins.
"""

import asyncio
import os
import sys
import uuid
from collections.abc import Generator
from typing import Any, List

import pytest
import pytest_asyncio
from _pytest.nodes import Node
from filelock import FileLock
from httpx import ASGITransport, AsyncClient

from tests.fixtures.test_database_env import TEST_DATABASE_ENV

pytest_plugins = [
    "tests.fixtures.workers",
    "tests.fixtures.services",
    "tests.fixtures.clients",
    "tests.fixtures.auth",
    "tests.fixtures.push",
    "tests.fixtures.mcp_modes_stub",
    "tests.fixtures.mcp_registry_stub",
    "tests.fixtures.embed_e2e",
    "tests.profiling.plugin",
]

os.environ["TESTING"] = "true"
if sys.platform == "darwin":
    _brew_path = "/opt/homebrew/bin"
    if _brew_path not in os.environ.get("PATH", ""):
        os.environ["PATH"] = f"{_brew_path}:{os.environ.get('PATH', '')}"
for _db_key, _db_val in TEST_DATABASE_ENV.items():
    os.environ.setdefault(_db_key, _db_val)
os.environ.setdefault("DATABASE__REDIS_URL", "redis://localhost:63792/0")
os.environ.setdefault("TASKS__BROKER_URL", "redis://localhost:63792/1")
os.environ.setdefault("TRACING__TEMPO_ENABLED", "false")
os.environ.setdefault("AUTH__PERMISSIONS_ENABLED", "false")
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
os.environ.setdefault("VOICE__STT__PROVIDER", "mock")
os.environ.setdefault("VOICE__STT__MOCK_TRANSCRIPT_TEXT", "Тестовая транскрипция sync worker")
os.environ.setdefault("S3__DEFAULT_BUCKET", "test-bucket")
os.environ.setdefault("S3__BUCKETS__TEST-BUCKET__ENDPOINT_URL", "http://localhost:19002")
os.environ.setdefault("OFFICE__JWT_SECRET", "test-onlyoffice-jwt-secret")
os.environ.setdefault("OFFICE__DOCUMENT_SERVER_PUBLIC_URL", "http://localhost:18088")
os.environ.setdefault("OFFICE__CALLBACK_PUBLIC_BASE_URL", "http://testserver")
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
os.environ.setdefault("RAG__DOCUMENT_INDEXING__SEARCH_DEFAULTS__RERANKER__ENABLED", "false")
os.environ.setdefault("LLM__OPENROUTER__API_KEY", "sk-test-key")
import core.config.base  # noqa: E402

core.config.base._settings_instance = None
import apps.flows_worker.broker as platform_broker_module  # noqa: E402
from apps.flows.main import app as fastapi_app  # noqa: E402
from apps.flows.src.tasks.flow_tasks import process_flow_task  # noqa: E402
from core.clients.llm import MockLLM, get_global_mock_llm, setup_mock_responses  # noqa: E402
from core.context import Context, User  # noqa: E402
from core.tracing.provider import shutdown_tracing  # noqa: E402
from tests.fixtures.ai_provider_defaults import make_test_company  # noqa: E402

if id(process_flow_task.broker) != id(platform_broker_module.broker):
    raise RuntimeError(
        "process_flow_task привязан к другому broker, чем apps.flows_worker.broker: TaskIQ worker не сможет выполнять kiq из HTTP."
    )


def pytest_sessionfinish(session, exitstatus):
    shutdown_tracing()
    if hasattr(session.config, "workerinput"):
        return
    from tests.fixtures.workers import release_pytest_controller_session

    release_pytest_controller_session()


_DB_SETUP_LOCK = "/tmp/platform_test_db_setup.lock"
_DB_SETUP_LOCK_TIMEOUT_SEC = int(os.environ.get("PLATFORM_TEST_DB_LOCK_TIMEOUT", "1800"))


def _real_taskiq_mock_llm_lane(node: Node) -> str:
    """Суффикс Redis-ключа mock_llm:responses:<lane> для процесса, где исполняется MockLLM.

    CRM analyze/dedup/graph вызывают LLM через A2A на flows (apps.flows), очередь там же,
    что у tests/flows — lane ``flows``. TaskIQ crm_worker только дергает EntityService и HTTP flows.
    """
    path = str(node.path).replace("\\", "/")
    if "/tests/sync/" in path:
        return "sync"
    if "/tests/rag/" in path:
        return "rag"
    return "flows"


def _real_taskiq_xdist_lane(node: Node) -> str:
    """Суффикс pytest-xdist_group для real_taskiq (очередь Redis по consumers).

    CRM + flows + frontend делят одну очередь mock_llm:responses:flows — группа flows_llm,
    иначе при параллельных gw ответы из Redis крадут друг у друга.
    """
    path = str(node.path).replace("\\", "/")
    if "/tests/sync/" in path:
        return "sync"
    if "/tests/rag/" in path:
        return "rag"
    if "/tests/search/" in path:
        return "search"
    return "flows_llm"


async def _alembic_version_ready(db_url: str) -> bool:
    """Проверяет: таблица alembic_version существует и в ней ровно одна строка."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(db_url, echo=False)
    try:
        async with engine.begin() as conn:
            row = await conn.execute(text("SELECT COUNT(*) FROM alembic_version"))
            count = row.scalar()
            return count == 1
    except Exception:
        return False
    finally:
        await engine.dispose()


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


async def _crm_base_schema_ready(db_url: str) -> bool:
    """Базовая CRM-схема (без журнала knowledge import)."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(db_url, echo=False)
    try:
        async with engine.begin() as conn:
            namespace_column_row = await conn.execute(
                text(
                    "\n                    SELECT COUNT(*)\n                    FROM information_schema.columns\n                    WHERE table_name = 'entity_types'\n                      AND column_name = 'namespace'\n                    "
                )
            )
            namespace_templates_table_row = await conn.execute(
                text(
                    "\n                    SELECT COUNT(*)\n                    FROM information_schema.tables\n                    WHERE table_name = 'namespace_templates'\n                    "
                )
            )
            namespace_template_types_table_row = await conn.execute(
                text(
                    "\n                    SELECT COUNT(*)\n                    FROM information_schema.tables\n                    WHERE table_name = 'namespace_template_types'\n                    "
                )
            )
            namespace_template_icon_column_row = await conn.execute(
                text(
                    "\n                    SELECT COUNT(*)\n                    FROM information_schema.columns\n                    WHERE table_name = 'namespace_templates'\n                      AND column_name = 'icon'\n                    "
                )
            )
            return (
                (namespace_column_row.scalar() or 0) == 1
                and (namespace_templates_table_row.scalar() or 0) == 1
                and ((namespace_template_types_table_row.scalar() or 0) == 1)
                and ((namespace_template_icon_column_row.scalar() or 0) == 1)
            )
    except Exception:
        return False
    finally:
        await engine.dispose()


async def _crm_tasks_table_ready(db_url: str) -> bool:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(db_url, echo=False)
    try:
        async with engine.begin() as conn:
            row = await conn.execute(
                text(
                    "\n                    SELECT COUNT(*)\n                    FROM information_schema.tables\n                    WHERE table_schema = 'public'\n                      AND table_name = 'crm_tasks'\n                    "
                )
            )
            return (row.scalar() or 0) == 1
    except Exception:
        return False
    finally:
        await engine.dispose()


async def _crm_schema_ready(db_url: str) -> bool:
    """Полная готовность CRM-схемы для тестов."""
    return await _crm_base_schema_ready(db_url) and await _crm_tasks_table_ready(db_url)


async def _shared_calendar_schema_ready(db_url: str) -> bool:
    """Проверяет наличие таблиц календаря и integration_credentials в shared схеме."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(db_url, echo=False)
    try:
        async with engine.begin() as conn:
            result = await conn.execute(
                text(
                    "\n                    SELECT COUNT(*)\n                    FROM information_schema.tables\n                    WHERE table_name IN ('calendar_events', 'calendar_integrations', 'integration_credentials')\n                    "
                )
            )
            return (result.scalar() or 0) == 3
    except Exception:
        return False
    finally:
        await engine.dispose()


async def _shared_scheduler_schema_ready(db_url: str) -> bool:
    """Проверяет наличие таблицы scheduler_tasks в shared схеме."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(db_url, echo=False)
    try:
        async with engine.begin() as conn:
            scheduler_tasks_table_row = await conn.execute(
                text(
                    "\n                    SELECT COUNT(*)\n                    FROM information_schema.tables\n                    WHERE table_name = 'scheduler_tasks'\n                    "
                )
            )
            return (scheduler_tasks_table_row.scalar() or 0) == 1
    except Exception:
        return False
    finally:
        await engine.dispose()


async def _office_schema_ready(office_db_url: str) -> bool:
    """platform_office: привязки, колонка catalog_id, таблица каталогов (миграции office_0002+)."""
    if not office_db_url or not office_db_url.strip():
        return True
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(office_db_url, echo=False)
    try:
        async with engine.begin() as conn:
            bindings = await conn.execute(
                text(
                    "\n                    SELECT COUNT(*)\n                    FROM information_schema.tables\n                    WHERE table_schema = 'public'\n                      AND table_name = 'office_document_bindings'\n                    "
                )
            )
            if (bindings.scalar() or 0) != 1:
                return False
            ns_col = await conn.execute(
                text(
                    "\n                    SELECT COUNT(*)\n                    FROM information_schema.columns\n                    WHERE table_schema = 'public'\n                      AND table_name = 'office_document_bindings'\n                      AND column_name = 'namespace'\n                    "
                )
            )
            if (ns_col.scalar() or 0) != 1:
                return False
            cat_col = await conn.execute(
                text(
                    "\n                    SELECT COUNT(*)\n                    FROM information_schema.columns\n                    WHERE table_schema = 'public'\n                      AND table_name = 'office_document_bindings'\n                      AND column_name = 'catalog_id'\n                    "
                )
            )
            if (cat_col.scalar() or 0) != 1:
                return False
            catalogs = await conn.execute(
                text(
                    "\n                    SELECT COUNT(*)\n                    FROM information_schema.tables\n                    WHERE table_schema = 'public'\n                      AND table_name = 'office_document_catalogs'\n                    "
                )
            )
            return (catalogs.scalar() or 0) == 1
    except Exception:
        return False
    finally:
        await engine.dispose()


async def _tracing_schema_ready(tracing_db_url: str) -> bool:
    """platform_tracing: таблица spans (миграции tracing)."""
    if not tracing_db_url or not tracing_db_url.strip():
        return True
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(tracing_db_url, echo=False)
    try:
        async with engine.begin() as conn:
            row = await conn.execute(
                text(
                    "\n                    SELECT COUNT(*)\n                    FROM information_schema.tables\n                    WHERE table_schema = 'public'\n                      AND table_name = 'spans'\n                    "
                )
            )
            return (row.scalar() or 0) == 1
    except Exception:
        return False
    finally:
        await engine.dispose()


async def _ensure_postgres_database(admin_url: str, database_name: str) -> None:
    """CREATE DATABASE на том же инстансе, если базы ещё нет (admin_url → обычно …/postgres)."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(admin_url, echo=False, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        chk = await conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": database_name}
        )
        if chk.first() is None:
            await conn.execute(text(f'CREATE DATABASE "{database_name}"'))
    await engine.dispose()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database_before_tests():
    """
    Глобальная фикстура для подготовки БД перед запуском тестов.

    Логика: сравнивает Alembic head (файлы) с current (БД) для каждого сервиса.
    Если все актуальны — пропуск. Если отстают — инкрементальный upgrade по каждому.
    Если БД пуста (нет alembic_version) — полный дроп + upgrade.
    """
    from filelock import FileLock
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    shared_db_url = os.environ.get(
        "DATABASE__SHARED_URL", TEST_DATABASE_ENV["DATABASE__SHARED_URL"]
    )
    tracing_db_url = os.environ.get(
        "DATABASE__TRACING_URL", TEST_DATABASE_ENV.get("DATABASE__TRACING_URL", "")
    )
    if tracing_db_url:
        admin_url = shared_db_url.rsplit("/", 1)[0] + "/postgres"
        await _ensure_postgres_database(admin_url, "platform_tracing")
    worktracker_db_url = os.environ.get(
        "DATABASE__WORKTRACKER_URL", TEST_DATABASE_ENV.get("DATABASE__WORKTRACKER_URL", "")
    )
    if worktracker_db_url:
        admin_url = shared_db_url.rsplit("/", 1)[0] + "/postgres"
        await _ensure_postgres_database(admin_url, "platform_worktracker")
    from core.db.migration_manifest import bootstrap_migration_registry
    from core.db.migrations import run_migrations_async

    bootstrap_migration_registry()
    (all_ok, stale_services) = await _all_migrations_up_to_date()
    if all_ok:
        print("Все миграции актуальны, пропуск.\n")
        yield
    else:
        lock = FileLock(_DB_SETUP_LOCK, timeout=_DB_SETUP_LOCK_TIMEOUT_SEC)
        with lock:
            (all_ok, stale_services) = await _all_migrations_up_to_date()
            if all_ok:
                print("Миграции применены другим процессом, пропуск.\n")
                yield
            else:
                has_any_schema = await _alembic_version_ready(shared_db_url)
                if has_any_schema:
                    for svc_name in stale_services:
                        print(f"Догрузка миграций сервиса {svc_name}...")
                        await run_migrations_async(service=svc_name)
                        print(f"Миграции {svc_name} применены!")
                    print()
                    yield
                else:
                    print("Подготовка БД для тестов (первичная инициализация)...")
                    engine = create_async_engine(shared_db_url, echo=False)
                    async with engine.begin() as conn:
                        result = await conn.execute(
                            text(
                                "\n                            SELECT tablename FROM pg_tables\n                            WHERE schemaname = 'public'\n                        "
                            )
                        )
                        tables = [row[0] for row in result.fetchall()]
                        if tables:
                            await conn.execute(text("SET session_replication_role = 'replica'"))
                            for table in tables:
                                await conn.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))
                            await conn.execute(text("SET session_replication_role = 'origin'"))
                            print(f"   Удалено {len(tables)} таблиц")
                    await engine.dispose()
                    print("Применение всех миграций...")
                    await run_migrations_async()
                    print("Миграции применены!\n")
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


_APP_INIT_LOCK = "/tmp/platform_test_app_init.lock"
_APP_INIT_DONE = "/tmp/platform_test_app_init.done"
_TASKIQ_WORKER_LOCK = "/tmp/platform_test_taskiq_worker.lock"
_TASKIQ_WORKER_PID = "/tmp/platform_test_taskiq_worker.pid"
_RAG_WORKER_LOCK = "/tmp/platform_test_rag_worker.lock"
_RAG_WORKER_PID = "/tmp/platform_test_rag_worker.pid"
_TEST_SERVER_MARKERS = (
    "/tmp/platform_test_flows_server.pid",
    "/tmp/platform_test_flows_server.pid.ref_count",
    "/tmp/platform_test_flows_server.pid.envsig",
    "/tmp/platform_test_rag_server.pid",
    "/tmp/platform_test_rag_server.pid.ref_count",
    "/tmp/platform_test_rag_server.pid.envsig",
    "/tmp/platform_test_crm_server.pid",
    "/tmp/platform_test_crm_server.pid.ref_count",
    "/tmp/platform_test_crm_server.pid.envsig",
    "/tmp/platform_test_frontend_server.pid",
    "/tmp/platform_test_frontend_server.pid.ref_count",
    "/tmp/platform_test_frontend_server.pid.envsig",
    "/tmp/platform_test_sync_server.pid",
    "/tmp/platform_test_sync_server.pid.ref_count",
    "/tmp/platform_test_sync_server.pid.envsig",
    "/tmp/platform_test_office_server.pid",
    "/tmp/platform_test_office_server.pid.ref_count",
    "/tmp/platform_test_office_server.pid.envsig",
    "/tmp/platform_test_search_server.pid",
    "/tmp/platform_test_search_server.pid.ref_count",
    "/tmp/platform_test_search_server.pid.envsig",
    "/tmp/platform_test_voice_server.pid",
    "/tmp/platform_test_voice_server.pid.ref_count",
    "/tmp/platform_test_voice_server.pid.envsig",
    "/tmp/platform_test_provider_litserve_server.pid",
    "/tmp/platform_test_provider_litserve_server.pid.ref_count",
    "/tmp/platform_test_provider_litserve_server.pid.envsig",
    "/tmp/platform_test_capability_gateway_server.pid",
    "/tmp/platform_test_capability_gateway_server.pid.ref_count",
    "/tmp/platform_test_capability_gateway_server.pid.envsig",
    "/tmp/platform_test_code_runner_python_server.pid",
    "/tmp/platform_test_code_runner_python_server.pid.ref_count",
    "/tmp/platform_test_code_runner_python_server.pid.envsig",
    "/tmp/platform_test_code_runner_node_server.pid",
    "/tmp/platform_test_code_runner_node_server.pid.ref_count",
    "/tmp/platform_test_code_runner_node_server.pid.envsig",
    "/tmp/platform_test_code_runner_go_server.pid",
    "/tmp/platform_test_code_runner_go_server.pid.ref_count",
    "/tmp/platform_test_code_runner_go_server.pid.envsig",
    "/tmp/platform_test_code_runner_csharp_server.pid",
    "/tmp/platform_test_code_runner_csharp_server.pid.ref_count",
    "/tmp/platform_test_code_runner_csharp_server.pid.envsig",
    "/tmp/platform_test_worktracker_server.pid",
    "/tmp/platform_test_worktracker_server.pid.ref_count",
    "/tmp/platform_test_worktracker_server.pid.envsig",
)


def pytest_configure(config):
    """Очистка маркеров синхронизации при старте тестов."""
    import pathlib
    import time

    if not hasattr(config, "workerinput"):
        from tests.fixtures.workers import prepare_pytest_controller_session

        try:
            prepare_pytest_controller_session()
        except RuntimeError as exc:
            raise pytest.UsageError(str(exc)) from exc

    max_age_seconds = 3600
    for marker in [
        _DB_SETUP_LOCK,
        "/tmp/platform_test_runet_index_seed.lock",
        _APP_INIT_LOCK,
        _APP_INIT_DONE,
        _TASKIQ_WORKER_LOCK,
        _TASKIQ_WORKER_PID,
        f"{_TASKIQ_WORKER_PID}.refs",
        _RAG_WORKER_LOCK,
        _RAG_WORKER_PID,
        f"{_RAG_WORKER_PID}.refs",
        "/tmp/platform_test_sync_taskiq_worker.pid.refs",
        "/tmp/platform_test_crm_taskiq_worker.pid.refs",
        *_TEST_SERVER_MARKERS,
    ]:
        path = pathlib.Path(marker)
        try:
            marker_stat = path.stat()
        except FileNotFoundError:
            continue
        age = time.time() - marker_stat.st_mtime
        if not hasattr(config, "workerinput") or age > max_age_seconds:
            path.unlink(missing_ok=True)
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
    """Session-scoped code-runner/capability_gateway на фиксированных портах — один xdist worker."""
    if nodeid.startswith("tests/capabilities/"):
        return True
    if nodeid.startswith("tests/flows/integration/"):
        return True
    return any(nodeid.startswith(prefix) for prefix in _CODE_RUNNER_TEST_PREFIXES)


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """
    Тесты с маркером real_taskiq передают ответы LLM через Redis; ключ mock_llm:responses:<lane>
    задаётся MOCK_LLM_REDIS_KEY у session workers и uvicorn (fixtures).

    flows_llm (CRM/flows/frontend/office real_taskiq + sandbox/code-runner) не получают xdist_group:
    один gw на всю очередь давал 20+ мин starvation и таймауты TaskIQ/code-runner к концу прогона.
    Доступ к session flows:9001, capability_gateway:9016, code-runner-* и mock_llm:responses:flows
    сериализует pytest_runtest_protocol + _SHARED_FLOWS_CONTOUR_FILE_LOCK между всеми gw.

    sync/rag/search real_taskiq — отдельные xdist_group (свои Redis mock lanes).

    SessionServerManager сбрасывает PYTEST_XDIST_WORKER у subprocess; фикстура mock_llm_redis
    для real_taskiq пишет в ключ по _real_taskiq_mock_llm_lane.

    tryfirst=True обязателен: xdist remote.py тоже регистрирует
    pytest_collection_modifyitems и добавляет @gname к nodeid по существующим
    маркерам. Наш хук должен выполниться ДО xdist, чтобы маркер уже был виден.
    """
    for item in items:
        if item.get_closest_marker("real_taskiq"):
            lane = _real_taskiq_xdist_lane(item)
            if lane == "flows_llm":
                item.add_marker(pytest.mark.xdist_group(_SHARED_FLOWS_RUNTIME_XDIST_GROUP))
            else:
                item.add_marker(pytest.mark.xdist_group(f"real_taskiq_{lane}"))
            if item.get_closest_marker("timeout") is None:
                item.add_marker(pytest.mark.timeout(120, func_only=True))
        elif _is_sandbox_runtime_test(item.nodeid):
            if item.get_closest_marker("xdist_group") is None:
                item.add_marker(pytest.mark.xdist_group(_SHARED_FLOWS_RUNTIME_XDIST_GROUP))
            if item.get_closest_marker("timeout") is None:
                item.add_marker(pytest.mark.timeout(180, func_only=True))
        elif item.nodeid.startswith("tests/sync/"):
            item.add_marker(pytest.mark.xdist_group("sync_db"))
        elif item.nodeid.startswith("tests/rag/test_rag_resource") or item.nodeid.startswith(
            "tests/rag/unit/test_rag_resource"
        ):
            item.add_marker(pytest.mark.xdist_group("rag_resource"))
        elif item.nodeid.startswith("tests/ui/"):
            item.add_marker(pytest.mark.xdist_group("ui_e2e"))


_SHARED_FLOWS_CONTOUR_FILE_LOCK = "/tmp/platform_shared_flows_contour.lock"


def _uses_shared_flows_contour_lock(item: pytest.Item) -> bool:
    """Session flows HTTP + capability_gateway + code-runner-* + mock_llm:responses:flows — один контур."""
    if _is_sandbox_runtime_test(item.nodeid):
        return True
    return (
        item.get_closest_marker("real_taskiq") is not None
        and _real_taskiq_mock_llm_lane(item) == "flows"
    )


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_protocol(item, nextitem):
    """Сериализует shared flows contour между pytest-xdist workers (фиксированные порты 9001/9016–9020)."""
    if not _uses_shared_flows_contour_lock(item):
        yield
        return
    from filelock import FileLock

    lock = FileLock(_SHARED_FLOWS_CONTOUR_FILE_LOCK, timeout=600)
    lock.acquire()
    try:
        yield
    finally:
        lock.release()


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_call(item) -> Generator[None, object, object]:
    """
    Для real_taskiq: глобальный alarm из pytest_runtest_protocol считает время
    с начала setup — ложные дампы. Снимаем его в начале call и ставим новый
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


@pytest.fixture(autouse=True)
def test_context(request):
    """
    Автоматически устанавливает тестовый контекст для всех тестов.
    Это необходимо для работы с репозиториями, которые требуют активную компанию.

    Не применяется к API тестам (они используют middleware).
    """
    if "api" in request.node.nodeid and (
        "frontend_client" in request.fixturenames or "flows_client" in request.fixturenames
    ):
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


_MOCK_LLM_CAPTURE_FILE_LOCK = "/tmp/platform_mock_llm_capture.lock"


@pytest_asyncio.fixture
async def mock_llm_capture(container, unique_id):
    """
    Включает захват LLM-вызовов MockLLM в Redis на время теста и
    возвращает callable, читающий журнал.

    `MockLLM.stream` в любом процессе (uvicorn flows, TaskIQ workers,
    локальные вызовы) читает один общий ключ `mock_llm:capture:active_scope`
    и пишет каждый вызов как JSON в `mock_llm:capture:<scope>`.
    Запись содержит `model`, `messages` (role + plain text + parts),
    `tools`, `response_format`. Никаких моков продакшна и monkeypatch.

    FileLock на время теста: при pytest-xdist несколько gw могут одновременно
    ставить `active_scope` и перезаписывать глобальный ключ; worker тогда пишет
    журнал не в тот scope.

    Пример:
        async def test_smth(mock_llm_capture, mock_llm_redis):
            await mock_llm_redis([{"type": "text", "content": "..."}])
            ...  # запускаем сценарий
            calls = await mock_llm_capture()  # все вызовы LLM в порядке прихода
    """
    from filelock import FileLock

    from core.clients.llm.mock import (
        read_mock_llm_capture,
        start_mock_llm_capture,
        stop_mock_llm_capture,
    )

    scope = f"test_{unique_id}"
    lock = FileLock(_MOCK_LLM_CAPTURE_FILE_LOCK, timeout=420)
    with lock:
        await start_mock_llm_capture(container.redis_client, scope)

        async def _read():
            return await read_mock_llm_capture(container.redis_client, scope)

        try:
            yield _read
        finally:
            await stop_mock_llm_capture(container.redis_client, scope)


@pytest_asyncio.fixture
async def mock_llm_redis(container, request):
    """
    Фабрика для создания MockLLM через Redis.
    Для интеграционных тестов с реальным worker.

    НЕ использовать с sync_tools!

    Для real_taskiq ключ mock_llm:responses:<lane> по _real_taskiq_mock_llm_lane
    (tests/crm используют lane flows — LLM на сервисе flows через A2A).

    Пример:
        async def test_integration(mock_llm_redis):
            await mock_llm_redis([
                {"type": "text", "content": "Response"}
            ])
    """
    from core.clients.llm.mock import clear_mock_responses_redis, setup_mock_responses_redis

    is_real_taskiq = request.node.get_closest_marker("real_taskiq") is not None
    key_override = (
        f"mock_llm:responses:{_real_taskiq_mock_llm_lane(request.node)}" if is_real_taskiq else None
    )

    async def _factory(responses: List[Any]) -> None:
        await clear_mock_responses_redis(container.redis_client, key_override=key_override)
        await setup_mock_responses_redis(
            container.redis_client, responses, key_override=key_override
        )

    yield _factory
    await clear_mock_responses_redis(container.redis_client, key_override=key_override)


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
def reset_mock_llm():
    """
    Автоматический сброс MockLLM перед каждым тестом.
    Обеспечивает изоляцию тестов.
    """
    yield
    mock = get_global_mock_llm("mock-gpt-4")
    if mock:
        mock.reset()


@pytest.fixture(autouse=True)
def sync_tools(request, monkeypatch):
    """
    Выполняет tools и agent tasks синхронно без TaskIQ worker.

    autouse=True - применяется ко всем тестам автоматически.
    Это обеспечивает единообразное поведение во всех тестах.

    Для тестов реального TaskIQ worker используйте маркер:
        @pytest.mark.real_taskiq

    Патчит:
    - execute_tool.kiq - выполняет tools напрямую
    - process_flow_task.kiq - выполняет agent tasks напрямую
    - send_task_update.kiq - выполняет push notifications напрямую
    - send_webhook.kiq - выполняет webhooks напрямую

    Redis Pub/Sub не подменяется: стриминг идёт через реальный Redis из контейнера.
    """
    if request.node.get_closest_marker("real_taskiq"):
        yield
        return
    import apps.crm.services.entity_service as crm_entity_service_module
    import apps.crm.services.task_service as crm_task_service_module
    import apps.crm_worker.tasks.analysis_tasks as crm_analysis_tasks
    import apps.crm_worker.tasks.daily_summary_tasks as crm_daily_summary_tasks
    import apps.crm_worker.tasks.draft_repair_tasks as crm_draft_repair_tasks
    import apps.crm_worker.tasks.knowledge_import_tasks as crm_knowledge_import_tasks
    import apps.crm_worker.tasks.namespace_integration_tasks as crm_namespace_integration_tasks
    import apps.crm_worker.tasks.note_markdown_tasks as crm_note_markdown_tasks
    import apps.flows.src.api.v1.internal_work_items as flows_internal_work_items_module
    import apps.flows.src.channels.a2a as flows_a2a_channel_module
    import apps.flows.src.channels.base as flows_base_channel_module
    import apps.flows.src.services.hitl_work_item_service as flows_hitl_work_item_module
    import apps.flows.src.triggers.executor as flows_trigger_executor_module
    import apps.idle_worker.tasks.push_notification_tasks as push_notification_tasks
    import apps.office.services.catalog_rag_index_service as office_catalog_rag_index_module
    import apps.rag.api.documents as rag_documents_module
    import apps.rag_worker.tasks.indexing_tasks as rag_indexing_tasks
    import apps.sync.realtime.handlers as sync_handlers_module
    import apps.sync.realtime.operations as sync_operations_module
    import apps.sync.realtime.tasks as sync_realtime_tasks
    import core.tasks.kicker as task_kicker_module
    from apps.crm_worker.task_names import (
        CRM_FORMAT_NOTE_DESCRIPTION_MARKDOWN_TASK_NAME,
        CRM_PROCESS_NOTE_TASK_NAME,
        CRM_REBUILD_DAILY_SUMMARY_TASK_NAME,
        CRM_REBUILD_PERIOD_SUMMARY_TASK_NAME,
        CRM_REPAIR_NOTE_ANALYSIS_DRAFT_TASK_NAME,
        CRM_RUN_KNOWLEDGE_IMPORT_TASK_NAME,
        CRM_RUN_NAMESPACE_INTEGRATION_JOB_TASK_NAME,
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
    from apps.sync.realtime.task_names import (
        SYNC_AGGREGATE_CALL_TRANSCRIPT_TASK_NAME,
        SYNC_FINALIZE_RECORDING_TASK_NAME,
        SYNC_SPEECH_TO_CHAT_POLL_TASK_NAME,
        SYNC_TRANSCRIBE_AUDIO_MESSAGE_TASK_NAME,
        SYNC_TRANSCRIBE_VIDEO_MESSAGE_TASK_NAME,
    )

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
            CRM_REBUILD_DAILY_SUMMARY_TASK_NAME,
            CRM_REBUILD_PERIOD_SUMMARY_TASK_NAME,
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
        CRM_PROCESS_NOTE_TASK_NAME: crm_analysis_tasks.process_note_task,
        CRM_REPAIR_NOTE_ANALYSIS_DRAFT_TASK_NAME: crm_draft_repair_tasks.repair_note_analysis_draft_task,
        CRM_FORMAT_NOTE_DESCRIPTION_MARKDOWN_TASK_NAME: crm_note_markdown_tasks.format_note_description_markdown_task,
        CRM_RUN_KNOWLEDGE_IMPORT_TASK_NAME: crm_knowledge_import_tasks.run_knowledge_import_task,
        CRM_RUN_NAMESPACE_INTEGRATION_JOB_TASK_NAME: crm_namespace_integration_tasks.run_namespace_integration_job,
        CRM_REBUILD_DAILY_SUMMARY_TASK_NAME: crm_daily_summary_tasks.rebuild_daily_summary_task,
        CRM_REBUILD_PERIOD_SUMMARY_TASK_NAME: crm_daily_summary_tasks.rebuild_period_summary_task,
        SYNC_TRANSCRIBE_AUDIO_MESSAGE_TASK_NAME: sync_realtime_tasks.sync_transcribe_audio_message_task,
        SYNC_TRANSCRIBE_VIDEO_MESSAGE_TASK_NAME: sync_realtime_tasks.sync_transcribe_video_message_task,
        SYNC_AGGREGATE_CALL_TRANSCRIPT_TASK_NAME: sync_realtime_tasks.sync_aggregate_call_transcript_task,
        SYNC_FINALIZE_RECORDING_TASK_NAME: sync_realtime_tasks.sync_finalize_recording_task,
        SYNC_SPEECH_TO_CHAT_POLL_TASK_NAME: sync_realtime_tasks.sync_speech_to_chat_poll_task,
        rag_indexing_tasks.RAG_INDEX_DOCUMENT_S3_TASK_NAME: rag_indexing_tasks.index_rag_document_s3_task,
        rag_indexing_tasks.RAG_INDEX_OFFICE_CATALOG_TASK_NAME: rag_indexing_tasks.index_office_catalog_task,
    }

    async def sync_task_name_kiq(
        task_name,
        broker,
        *args,
        override_request_id=None,
        override_trace_id=None,
        service_name=None,
        background_kind=None,
        extra_labels=None,
        **kwargs,
    ):
        _ = (
            broker,
            override_request_id,
            override_trace_id,
            service_name,
            background_kind,
            extra_labels,
        )
        handler = task_name_handlers.get(task_name)
        if handler is None:
            raise AssertionError(f"Неизвестный TaskIQ task-name: {task_name!r}")
        if handler is sync_agent_kiq:
            return await sync_agent_kiq(**kwargs)
        if handler is sync_tool_kiq:
            return await sync_tool_kiq(*args, **kwargs)
        if handler is sync_send_task_update_kiq:
            return await sync_send_task_update_kiq(*args, **kwargs)
        if handler is sync_send_webhook_kiq:
            return await sync_send_webhook_kiq(*args, **kwargs)
        if task_name in crm_background_task_names:
            task = asyncio.create_task(
                handler(*args, **kwargs),
                name=task_name,
            )
            task.add_done_callback(_log_background_task_failure)
            return SyncTaskResult(result=None)
        return await _sync_call(handler, *args, **kwargs)

    monkeypatch.setattr(tool_tasks.execute_tool, "kiq", sync_tool_kiq)
    monkeypatch.setattr(flow_tasks.process_flow_task, "kiq", sync_agent_kiq)
    monkeypatch.setattr(push_notification_tasks.send_task_update, "kiq", sync_send_task_update_kiq)
    monkeypatch.setattr(push_notification_tasks.send_webhook, "kiq", sync_send_webhook_kiq)
    for module in (
        task_kicker_module,
        flows_base_channel_module,
        flows_a2a_channel_module,
        flows_hitl_work_item_module,
        flows_internal_work_items_module,
        flows_trigger_executor_module,
        crm_task_service_module,
        crm_entity_service_module,
        sync_operations_module,
        sync_handlers_module,
        rag_documents_module,
        office_catalog_rag_index_module,
        rag_indexing_tasks,
    ):
        monkeypatch.setattr(module, "kiq_task_name_with_context", sync_task_name_kiq)
    yield None


@pytest_asyncio.fixture(scope="session")
async def app(taskiq_worker, crm_worker):
    """
    Реальное FastAPI приложение с lifespan.
    Загружает flows, инициализирует контейнер.
    Зависит от taskiq_worker - worker запускается автоматически.

    scope="session" - приложение поднимается один раз на все тесты.

    При pytest-xdist каждый gw-worker поднимает свой lifespan независимо.
    Первый worker касается маркера (только для логирования), lock отпускается
    до yield — все воркеры работают параллельно.

    ВАЖНО: Scheduler НЕ запускается автоматически! Тесты которым нужен scheduler
    должны явно использовать фикстуру taskiq_scheduler.
    """
    import pathlib

    done_marker = pathlib.Path(_APP_INIT_DONE)
    lock = FileLock(_APP_INIT_LOCK, timeout=300)
    with lock:
        if not done_marker.exists():
            done_marker.touch()
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
            "code": 'async def execute(args: dict, state: dict = None):\n    from apps.flows.src.runtime.exceptions import FlowInterrupt\n    q = args.get("question")\n    if not q or not str(q).strip():\n        raise ValueError("ask_user: question обязателен")\n    raise FlowInterrupt(question=str(q).strip())\n',
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
        transport=ASGITransport(app=flows_app), base_url="http://testserver"
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
        base_url="http://testserver",
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
    user = User(
        user_id=user_id,
        name="Test User",
        emails=[f"{user_id}@test.com"],
        companies={company_id: ["owner", "admin"]},
        active_company_id=company_id,
    )
    await frontend_container.user_repository.set(user)
    await frontend_container.subdomain_repository.set_mapping(company_subdomain, company_id)
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
    from core.config import get_settings
    from core.config.models import RAGProviderConfig
    from core.rag.embedding_runtime import resolve_rag_embedding_runtime
    from core.rag.providers.pgvector_provider import PgVectorProvider

    settings = get_settings()
    config = RAGProviderConfig(
        db_url=os.environ.get(
            "DATABASE__RAG_URL",
            "postgresql+asyncpg://platform_user:admin@localhost:54322/platform_rag",
        ),
        chunk_size=1000,
        chunk_overlap=100,
    )
    embedding_runtime = resolve_rag_embedding_runtime(
        settings.rag.embedding, settings.llm, settings.provider_litserve
    )
    provider = PgVectorProvider(config, embedding_runtime)
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
