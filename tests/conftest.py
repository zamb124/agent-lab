"""
Фикстуры для тестов platform.

ПРАВИЛО: Мок только LLM. Все остальное - реальные объекты.
Tools автоматически работают в mock режиме (TESTING=true).
TaskIQ worker запускается автоматически для тестов.

Фикстуры сервисов и клиентов загружаются из tests/fixtures/ через pytest_plugins.
"""

# Подключаем фикстуры из tests/fixtures/
pytest_plugins = [
    "tests.fixtures.services",
    "tests.fixtures.clients",
    "tests.fixtures.auth",
    "tests.fixtures.push",
    "tests.fixtures.mcp_http_stub",
]

import json
import os
import signal
import subprocess
import sys
import time
import uuid
from collections.abc import Generator
from typing import Any, Dict, List

import pytest
import pytest_asyncio
from filelock import FileLock
from httpx import ASGITransport, AsyncClient

from tests.fixtures.test_database_env import TEST_DATABASE_ENV


# Устанавливаем переменные окружения ДО импорта приложения
os.environ["TESTING"] = "true"
# Для macOS с Apple Silicon добавляем путь к Homebrew бинарникам (ffmpeg и т.д.)
if sys.platform == "darwin":
    _brew_path = "/opt/homebrew/bin"
    if _brew_path not in os.environ.get("PATH", ""):
        os.environ["PATH"] = f"{_brew_path}:{os.environ.get('PATH', '')}"

for _db_key, _db_val in TEST_DATABASE_ENV.items():
    os.environ.setdefault(_db_key, _db_val)
os.environ.setdefault("DATABASE__REDIS_URL", "redis://localhost:63792/0")
os.environ.setdefault("TASKS__BROKER_URL", "redis://localhost:63792/1")
# Отключаем проверку permissions по умолчанию для тестов (кроме test_permissions.py)
os.environ.setdefault("AUTH__PERMISSIONS_ENABLED", "false")
# Default tenant для тестов
os.environ.setdefault("SERVER__DEFAULT_TENANT_ID", "test_tenant")
# Порты сервисов для тестов (900X чтобы не конфликтовать с production)
os.environ["SERVER__FLOWS_SERVICE_URL"] = "http://localhost:9001"
os.environ["SERVER__RAG_SERVICE_URL"] = "http://localhost:9002"
os.environ["SERVER__CRM_SERVICE_URL"] = "http://localhost:9003"
os.environ["SERVER__FRONTEND_SERVICE_URL"] = "http://localhost:9004"
os.environ["SERVER__SYNC_SERVICE_URL"] = "http://localhost:9005"
os.environ.setdefault("SERVER__VOICE_SERVICE_URL", "http://localhost:9015")
os.environ.setdefault("STT__PROVIDER", "mock")
os.environ.setdefault("STT__MOCK_TRANSCRIPT_TEXT", "Тестовая транскрипция sync worker")
# S3: дефолтный alias test-bucket и endpoint тестового MinIO (docker-compose-test: 19002).
# В conf.json у test-bucket указан 19001 (dev); без override тесты создавали бакет на 19002, а приложение — на 19001.
os.environ.setdefault("S3__DEFAULT_BUCKET", "test-bucket")
os.environ.setdefault("S3__BUCKETS__TEST-BUCKET__ENDPOINT_URL", "http://localhost:19002")
# OnlyOffice: локально после `make test-up` — порт 18088 (docker-compose-test). В контейнере tests_runner задаётся в compose.
os.environ.setdefault("OFFICE__JWT_SECRET", "test-onlyoffice-jwt-secret")
os.environ.setdefault("OFFICE__DOCUMENT_SERVER_PUBLIC_URL", "http://localhost:18088")
os.environ.setdefault("OFFICE__CALLBACK_PUBLIC_BASE_URL", "http://testserver")
# RAG config для тестов (pgvector в PostgreSQL)
os.environ.setdefault("RAG__ENABLED", "true")
os.environ.setdefault("RAG__DEFAULT_PROVIDER", "pgvector")
os.environ.setdefault("RAG__PROVIDERS__PGVECTOR__ENABLED", "true")
os.environ.setdefault("LLM__OPENROUTER__API_KEY", "sk-test-key")

# Сбрасываем settings singleton чтобы он пересоздался с тестовыми env переменными
import core.config.base
core.config.base._settings_instance = None

# Импорт broker до apps.flows.main: create_broker() читает get_settings() с уже выставленным TEST_DATABASE_ENV.
import apps.flows_worker.broker as platform_broker_module  # noqa: F401

from core.clients.llm import MockLLM, get_global_mock_llm, setup_mock_responses
from core.context import Context, Company, User
from apps.flows.main import app as fastapi_app

from apps.flows.src.tasks.flow_tasks import process_flow_task

if id(process_flow_task.broker) != id(platform_broker_module.broker):
    raise RuntimeError(
        "process_flow_task привязан к другому broker, чем apps.flows_worker.broker: "
        "TaskIQ worker не сможет выполнять kiq из HTTP."
    )


_DB_SETUP_LOCK = "/tmp/platform_test_db_setup.lock"
# Один gw держит lock на DROP + run_migrations_async по всем сервисам; при -n auto остальные ждут дольше 120s.
_DB_SETUP_LOCK_TIMEOUT_SEC = int(os.environ.get("PLATFORM_TEST_DB_LOCK_TIMEOUT", "1800"))


async def _alembic_version_ready(db_url: str) -> bool:
    """Проверяет: таблица alembic_version существует и в ней ровно одна строка."""
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text

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
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text

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
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from pathlib import Path

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
    from core.db.migration_manifest import load_migration_manifest, migration_entry_is_active

    manifest = load_migration_manifest()
    stale: list[str] = []

    for entry in manifest["services"]:
        if not migration_entry_is_active(entry):
            continue
        name = entry["name"]
        script_loc = f"migrations/{name}"
        head = _alembic_head_revision(script_loc)
        if head is None:
            continue

        from core.config import get_settings
        url_key = entry["database_url_key"]
        db_url = getattr(get_settings().database, url_key)
        if not db_url or not str(db_url).strip():
            continue

        current = await _alembic_current_revision(str(db_url))
        if current != head:
            stale.append(name)

    return (len(stale) == 0, stale)


async def _crm_base_schema_ready(db_url: str) -> bool:
    """Базовая CRM-схема (без журнала knowledge import)."""
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text

    engine = create_async_engine(db_url, echo=False)
    try:
        async with engine.begin() as conn:
            namespace_column_row = await conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.columns
                    WHERE table_name = 'entity_types'
                      AND column_name = 'namespace'
                    """
                )
            )
            namespace_templates_table_row = await conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.tables
                    WHERE table_name = 'namespace_templates'
                    """
                )
            )
            namespace_template_types_table_row = await conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.tables
                    WHERE table_name = 'namespace_template_types'
                    """
                )
            )
            namespace_template_icon_column_row = await conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.columns
                    WHERE table_name = 'namespace_templates'
                      AND column_name = 'icon'
                    """
                )
            )
            return (
                (namespace_column_row.scalar() or 0) == 1
                and (namespace_templates_table_row.scalar() or 0) == 1
                and (namespace_template_types_table_row.scalar() or 0) == 1
                and (namespace_template_icon_column_row.scalar() or 0) == 1
            )
    except Exception:
        return False
    finally:
        await engine.dispose()


async def _crm_tasks_table_ready(db_url: str) -> bool:
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text

    engine = create_async_engine(db_url, echo=False)
    try:
        async with engine.begin() as conn:
            row = await conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = 'crm_tasks'
                    """
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
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text

    engine = create_async_engine(db_url, echo=False)
    try:
        async with engine.begin() as conn:
            result = await conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.tables
                    WHERE table_name IN ('calendar_events', 'calendar_integrations', 'integration_credentials')
                    """
                )
            )
            return (result.scalar() or 0) == 3
    except Exception:
        return False
    finally:
        await engine.dispose()


async def _shared_scheduler_schema_ready(db_url: str) -> bool:
    """Проверяет наличие таблицы scheduler_tasks в shared схеме."""
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text

    engine = create_async_engine(db_url, echo=False)
    try:
        async with engine.begin() as conn:
            scheduler_tasks_table_row = await conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.tables
                    WHERE table_name = 'scheduler_tasks'
                    """
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
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text

    engine = create_async_engine(office_db_url, echo=False)
    try:
        async with engine.begin() as conn:
            bindings = await conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = 'office_document_bindings'
                    """
                )
            )
            if (bindings.scalar() or 0) != 1:
                return False
            ns_col = await conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'office_document_bindings'
                      AND column_name = 'namespace'
                    """
                )
            )
            if (ns_col.scalar() or 0) != 1:
                return False
            cat_col = await conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'office_document_bindings'
                      AND column_name = 'catalog_id'
                    """
                )
            )
            if (cat_col.scalar() or 0) != 1:
                return False
            catalogs = await conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = 'office_document_catalogs'
                    """
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
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text

    engine = create_async_engine(tracing_db_url, echo=False)
    try:
        async with engine.begin() as conn:
            row = await conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = 'spans'
                    """
                )
            )
            return (row.scalar() or 0) == 1
    except Exception:
        return False
    finally:
        await engine.dispose()


async def _ensure_postgres_database(admin_url: str, database_name: str) -> None:
    """CREATE DATABASE на том же инстансе, если базы ещё нет (admin_url → обычно …/postgres)."""
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text

    engine = create_async_engine(admin_url, echo=False, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        chk = await conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": database_name},
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
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text
    from filelock import FileLock

    test_ports = [9001, 9002, 9003, 9004, 9005]
    print(f"\n Освобождаем тестовые порты: {test_ports}...")
    for port in test_ports:
        try:
            result = subprocess.run(
                f"lsof -ti:{port} | xargs kill -9 2>/dev/null",
                shell=True,
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                print(f"   Порт {port} освобожден")
        except Exception:
            pass
    time.sleep(0.35)
    print("Все тестовые порты свободны!\n")

    shared_db_url = os.environ.get("DATABASE__SHARED_URL", TEST_DATABASE_ENV["DATABASE__SHARED_URL"])
    tracing_db_url = os.environ.get(
        "DATABASE__TRACING_URL",
        TEST_DATABASE_ENV.get("DATABASE__TRACING_URL", ""),
    )

    if tracing_db_url:
        admin_url = shared_db_url.rsplit("/", 1)[0] + "/postgres"
        await _ensure_postgres_database(admin_url, "platform_tracing")

    from core.db.migration_manifest import bootstrap_migration_registry
    from core.db.migrations import run_migrations_async

    bootstrap_migration_registry()

    all_ok, stale_services = await _all_migrations_up_to_date()

    if all_ok:
        print("Все миграции актуальны, пропуск.\n")
        yield
    else:
        lock = FileLock(_DB_SETUP_LOCK, timeout=_DB_SETUP_LOCK_TIMEOUT_SEC)
        with lock:
            all_ok, stale_services = await _all_migrations_up_to_date()
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
                        result = await conn.execute(text("""
                            SELECT tablename FROM pg_tables
                            WHERE schemaname = 'public'
                        """))
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

    # Teardown: НЕ убиваем порты. При xdist каждый gw-worker имеет свою session,
    # и teardown первого завершившего worker'а убивал серверы, нужные остальным.
    # Стейл от текущего прогона очистится в startup следующего.


@pytest_asyncio.fixture(scope="session", autouse=True)
async def platform_notification_manager_redis(setup_database_before_tests):
    """Redis Pub/Sub для notify_user; без этого CRM и др. падают до старта flows lifespan."""
    from core.websocket.manager import notification_manager

    redis_url = os.environ.get("DATABASE__REDIS_URL", "redis://localhost:63792/0")
    await notification_manager.start_redis_listener(redis_url)
    yield


# Синхронизация session-scoped fixtures для pytest-xdist
# Первый worker инициализирует БД, остальные ждут
_APP_INIT_LOCK = "/tmp/platform_test_app_init.lock"
_APP_INIT_DONE = "/tmp/platform_test_app_init.done"

# TaskIQ worker - только один worker на все pytest workers
_TASKIQ_WORKER_LOCK = "/tmp/platform_test_taskiq_worker.lock"
_TASKIQ_WORKER_PID = "/tmp/platform_test_taskiq_worker.pid"

# RAG worker - только один worker на все pytest workers
_RAG_WORKER_LOCK = "/tmp/platform_test_rag_worker.lock"
_RAG_WORKER_PID = "/tmp/platform_test_rag_worker.pid"


def pytest_configure(config):
    """Очистка маркеров синхронизации при старте тестов."""
    import pathlib
    import time
    
    # Удаляем маркеры если они старше 1 часа (зависли от предыдущего запуска)
    max_age_seconds = 3600
    
    for marker in [
        _DB_SETUP_LOCK,
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
        "/tmp/platform_test_flows_server.pid.ref_count",
        "/tmp/platform_test_rag_server.pid.ref_count",
        "/tmp/platform_test_crm_server.pid.ref_count",
        "/tmp/platform_test_frontend_server.pid.ref_count",
        "/tmp/platform_test_sync_server.pid.ref_count",
    ]:
        path = pathlib.Path(marker)
        if path.exists():
            age = time.time() - path.stat().st_mtime
            # Master процесс удаляет всегда, worker только если файл старый
            if not hasattr(config, "workerinput") or age > max_age_seconds:
                path.unlink(missing_ok=True)
    
    # Создаём директорию для junit.xml если указана опция
    junitxml_path = config.getoption("--junitxml", default=None)
    if junitxml_path:
        junit_path = pathlib.Path(junitxml_path)
        junit_path.parent.mkdir(parents=True, exist_ok=True)


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items: list) -> None:
    """
    Тесты с маркером real_taskiq используют один Redis-ключ mock_llm:responses
    для передачи ответов LLM в TaskIQ worker и в uvicorn тестовых сервисов.
    Без группировки разные gw-workers одновременно портят очередь; без сброса
    PYTEST_XDIST_WORKER у дочернего uvicorn flows читал бы mock_llm:responses:gwN
    и не видел бы очередь, записанную фикстурой mock_llm_redis.

    Решение: все real_taskiq — в xdist_group real_taskiq (последовательно на
    одном gw при --dist=loadgroup); SessionServerManager убирает
    PYTEST_XDIST_WORKER из env процессов 9001–9005; MockLLM снимает элемент
    очереди из Redis одной Lua-транзакцией.

    tryfirst=True обязателен: xdist remote.py тоже регистрирует
    pytest_collection_modifyitems и добавляет @gname к nodeid по существующим
    маркерам. Наш хук должен выполниться ДО xdist, чтобы маркер уже был виден.
    """
    for item in items:
        if item.get_closest_marker("real_taskiq"):
            item.add_marker(pytest.mark.xdist_group("real_taskiq"))
            if item.get_closest_marker("timeout") is None:
                item.add_marker(pytest.mark.timeout(120, func_only=True))
        elif item.nodeid.startswith("tests/sync/"):
            item.add_marker(pytest.mark.xdist_group("sync_db"))
        elif item.nodeid.startswith("tests/rag/test_rag_resource") or item.nodeid.startswith(
            "tests/rag/unit/test_rag_resource"
        ):
            item.add_marker(pytest.mark.xdist_group("rag_resource"))
        elif item.nodeid.startswith("tests/ui/"):
            item.add_marker(pytest.mark.xdist_group("ui_e2e"))


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_call(item) -> Generator[None, object, object]:
    """
    Для real_taskiq: глобальный alarm из pytest_runtest_protocol считает время
    с начала setup — ложные дампы. Снимаем его в начале call и ставим новый
    с тем же faulthandler_timeout только на фазу call (тело теста).
    """
    if not item.get_closest_marker("real_taskiq"):
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
    # Пропускаем для API тестов - там контекст устанавливает middleware
    if 'api' in request.node.nodeid and ('frontend_client' in request.fixturenames or 'flows_client' in request.fixturenames):
        yield None
        return
    
    from core.context import set_context, clear_context
    from core.models.context_models import Context
    from core.models.identity_models import User, Company
    
    test_ctx = Context(
        user=User(user_id="test_user", name="Test User"),
        active_company=Company(company_id="system", name="System"),
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
        active_company=Company(company_id="system", name="System"),
        session_id="test_session",
        channel="test",
        metadata={
            "user_id": "test_user",
            "email": "test@example.com",
            "grps": [],
        },
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

    Usage:
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
async def mock_llm_capture(container, unique_id):
    """
    Включает захват LLM-вызовов MockLLM в Redis на время теста и
    возвращает callable, читающий журнал.

    `MockLLM.stream` в любом процессе (uvicorn flows, TaskIQ workers,
    локальные вызовы) читает один общий ключ `mock_llm:capture:active_scope`
    и пишет каждый вызов как JSON в `mock_llm:capture:<scope>`.
    Запись содержит `model`, `messages` (role + plain text + parts),
    `tools`, `response_format`. Никаких моков продакшна и monkeypatch.

    Usage:
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

    scope = f"test_{unique_id}"
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

    Для real_taskiq тестов используется базовый ключ (без суффикса xdist worker),
    т.к. TaskIQ worker subprocess и uvicorn тестовых HTTP-сервисов (SessionServerManager)
    сбрасывают PYTEST_XDIST_WORKER в env и читают тот же ключ, что и эта фикстура.
    Все real_taskiq тесты в одной xdist_group; параллельный доступ к очереди LLM
    снимает атомарный Lua-pop в MockLLM._get_redis_response.

    Usage:
        async def test_integration(mock_llm_redis):
            await mock_llm_redis([
                {"type": "text", "content": "Response"}
            ])
    """
    from core.clients.llm.mock import setup_mock_responses_redis, clear_mock_responses_redis

    is_real_taskiq = request.node.get_closest_marker("real_taskiq") is not None
    key_override = "mock_llm:responses" if is_real_taskiq else None

    async def _factory(responses: List[Any]) -> None:
        await clear_mock_responses_redis(container.redis_client, key_override=key_override)
        await setup_mock_responses_redis(container.redis_client, responses, key_override=key_override)

    yield _factory

    await clear_mock_responses_redis(container.redis_client, key_override=key_override)




@pytest.fixture
def state():
    """
    Реальный пустой state для тестов.
    Возвращает ExecutionState с минимальными обязательными полями.
    """
    from apps.flows.src.state.execution_state import ExecutionState
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
    from apps.flows.src.state.execution_state import ExecutionState
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
    
    Usage:
        def test_something(make_test_state):
            state = make_test_state(content="hello", user={"name": "John"})
            result = await node.run(state)
    """
    from apps.flows.src.state.execution_state import ExecutionState
    
    def _make_state(**kwargs) -> ExecutionState:
        defaults = {
            "task_id": "test-task-id",
            "context_id": "test-context-id",
            "user_id": "test-user",
            "session_id": "test-agent:test-context-id",
        }
        defaults.update(kwargs)
        # Если передан context_id, но не session_id, создаем session_id из context_id
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
    # Пропускаем для тестов с маркером real_taskiq
    if request.node.get_closest_marker("real_taskiq"):
        yield
        return
    from apps.flows.src.tasks import flow_tasks, tool_tasks
    import apps.idle_worker.tasks.push_notification_tasks as push_notification_tasks
    
    class SyncTaskResult:
        """Имитация результата TaskIQ task."""
        def __init__(self, result=None, error=None):
            self._result = result
            self.is_err = error is not None
            self.return_value = result
            self.error = error
            self.task_id = "sync-task-id"
        
        async def wait_result(self):
            return self
    
    async def sync_tool_kiq(tool_id, args, state):
        """Выполняет tool синхронно."""
        from core.context import get_context

        ctx = get_context()
        context_data = ctx.to_dict() if ctx is not None else None
        try:
            result = await tool_tasks.execute_tool(
                tool_id, args, state, context_data=context_data
            )
            return SyncTaskResult(result)
        except Exception as e:
            return SyncTaskResult(error=e)
    
    async def sync_agent_kiq(**kwargs):
        """Выполняет agent task синхронно."""
        from core.context import get_context, set_context
        
        saved_context = get_context()
        
        try:
            # Создаем мок Context для тестов (если context_data не передан)
            if "context_data" not in kwargs:
                mock_ctx = Context(
                    user=User(user_id="test_user", name="Test User"),
                    active_company=Company(company_id="system", name="System"),
                    session_id="test_session",
                    channel="test",
                    metadata={
                        "user_id": "test_user",
                        "email": "test@example.com",
                        "grps": [],
                    },
                )
                kwargs["context_data"] = mock_ctx.model_dump()
            
            result = await flow_tasks.process_flow_task(**kwargs)
            return SyncTaskResult(result)
        except Exception as e:
            return SyncTaskResult(error=e)
        finally:
            if saved_context:
                set_context(saved_context)
    
    async def sync_send_task_update_kiq(task_id, context_id, state, message=None, is_final=False):
        """Выполняет send_task_update синхронно."""
        result = await push_notification_tasks.send_task_update(task_id, context_id, state, message, is_final)
        return SyncTaskResult(result)
    
    async def sync_send_webhook_kiq(url, payload, token=None, credentials=None):
        """Выполняет send_webhook синхронно. Ошибки игнорируются как в реальном TaskIQ с ретраями."""
        try:
            result = await push_notification_tasks.send_webhook(url, payload, token, credentials)
            return SyncTaskResult(result)
        except Exception:
            # В реальном TaskIQ ретраи обрабатывают ошибки, здесь просто игнорируем
            return SyncTaskResult({"success": False})
    
    # Патчим kiq методы
    monkeypatch.setattr(tool_tasks.execute_tool, "kiq", sync_tool_kiq)
    monkeypatch.setattr(flow_tasks.process_flow_task, "kiq", sync_agent_kiq)
    monkeypatch.setattr(push_notification_tasks.send_task_update, "kiq", sync_send_task_update_kiq)
    monkeypatch.setattr(push_notification_tasks.send_webhook, "kiq", sync_send_webhook_kiq)
    
    yield None


# ============================================================================
# Импорт worker фикстур из отдельного модуля
# ============================================================================

# Worker фикстуры вынесены в tests/fixtures/workers.py для переиспользования
from tests.fixtures.workers import (  # noqa: F401
    crm_worker,
    rag_worker,
    sync_worker,
    taskiq_broker,
    taskiq_scheduler,
    taskiq_worker,
)


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

    # Кратко захватываем lock только чтобы пометить первый запуск.
    # Lock освобождается до yield, поэтому остальные gw-workers не блокируются.
    with lock:
        if not done_marker.exists():
            done_marker.touch()

    # Каждый xdist-worker поднимает свой lifespan (отдельный процесс, своя
    # Redis-сессия). Startup-операции (load_tools_to_db, load_flows_to_db)
    # идемпотентны, параллельное выполнение безопасно.
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
    # В тестах по умолчанию без воркера (локальное выполнение)
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
            "args_schema": {"expression": {"type": "string", "description": "Математическое выражение"}},
            "code": """async def execute(args: dict, state: dict = None):
    import ast
    import operator
    expr = args.get('expression', '0')
    if not isinstance(expr, str):
        expr = str(expr)
    ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
    def _eval(node):
        if isinstance(node, ast.Expression): return _eval(node.body)
        if isinstance(node, ast.Constant): return node.value
        if isinstance(node, ast.BinOp): return ops[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub): return -_eval(node.operand)
        raise ValueError(f"Unsupported: {type(node)}")
    return f"Результат: {_eval(ast.parse(expr, mode='eval'))}"
"""
        },
        "finish": {
            "tool_id": "finish",
            "description": "Завершает агента и возвращает финальный ответ",
            "args_schema": {"answer": {"type": "string", "description": "Финальный ответ"}},
            "code": "async def execute(args: dict, state: dict = None):\n    return args.get('answer', '')",
            "react_role": "exit"
        },
        "ask_user": {
            "tool_id": "ask_user",
            "description": "Задает вопрос пользователю",
            "args_schema": {"question": {"type": "string", "description": "Вопрос для пользователя"}},
            "code": """async def execute(args: dict, state: dict = None):
    from apps.flows.src.runtime.exceptions import FlowInterrupt
    q = args.get("question")
    if not q or not str(q).strip():
        raise ValueError("ask_user: question обязателен")
    raise FlowInterrupt(question=str(q).strip())
"""
        },
        "reason": {
            "tool_id": "reason",
            "description": "Рассуждение агента",
            "args_schema": {"thought": {"type": "string", "description": "Ход мысли"}},
            "code": "async def execute(args: dict, state: dict = None):\n    return args.get('thought', '')",
            "react_role": "reason"
        }
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
    
    Usage:
        async def test_api(flows_client):
            response = await flows_client.get("/flows/api/health")
            assert response.status_code == 200
    """
    async with AsyncClient(
        transport=ASGITransport(app=flows_app),
        base_url="http://testserver"
    ) as client:
        yield client


@pytest_asyncio.fixture
async def frontend_client(frontend_app):
    """
    HTTP клиент для тестирования frontend API.
    
    Usage:
        async def test_api(frontend_client):
            response = await frontend_client.get("/api/health")
            assert response.status_code == 200
    """
    async with AsyncClient(
        transport=ASGITransport(app=frontend_app),
        base_url="http://testserver",
        follow_redirects=True
    ) as client:
        yield client


@pytest_asyncio.fixture
async def frontend_client_with_auth(frontend_app, auth_token):
    """
    HTTP клиент с предустановленным auth token в cookies.
    
    Usage:
        async def test_api(frontend_client_with_auth):
            response = await frontend_client_with_auth.get("/api/something")
            assert response.status_code == 200
    """
    async with AsyncClient(
        transport=ASGITransport(app=frontend_app),
        base_url="http://testserver",
        cookies={"auth_token": auth_token},
        follow_redirects=True
    ) as client:
        yield client


@pytest_asyncio.fixture
async def test_agent(app, container):
    """
    Создает тестового агента для API тестов.
    
    Usage:
        async def test_api(frontend_client, test_agent):
            # test_agent.flow_id == "test_agent"
    """
    from apps.flows.src.models.flow_config import FlowConfig
    
    agent = FlowConfig(
        flow_id="test_agent",
        name="Test Agent",
        entry="main",
        nodes={
            "main": {
                "type": "llm_node",
                "prompt": "Test prompt",
                "next": None
            }
        },
    )
    await container.flow_repository.set(agent)
    
    yield agent
    
    # Cleanup - выполнится даже если тест упал
    await container.flow_repository.delete("test_agent")


@pytest_asyncio.fixture
async def test_agent_fixture(app, unique_id):
    """
    Создает уникального тестового агента с автоматическим cleanup.
    
    Гарантирует удаление агента даже если тест упал.
    
    Usage:
        async def test_something(test_agent_fixture):
            flow_id, container = test_agent_fixture
            # Создайте агента с flow_id
            # Cleanup произойдет автоматически
    """
    from apps.flows.src.container import get_container
    
    container = get_container()
    flow_ids_to_cleanup = []
    
    def register_agent(flow_id: str):
        """Регистрирует flow_id для cleanup"""
        flow_ids_to_cleanup.append(flow_id)
        return flow_id
    
    yield register_agent, container
    
    # Cleanup всех зарегистрированных агентов
    for flow_id in flow_ids_to_cleanup:
        try:
            await container.flow_repository.delete(flow_id)
        except Exception:
            pass  # Игнорируем ошибки cleanup


@pytest_asyncio.fixture
async def auth_token(frontend_container):
    """
    Создает авторизованного пользователя с компанией и возвращает токен.
    
    Usage:
        async def test_auth(frontend_client, auth_token):
            response = await frontend_client.get(
                "/api/companies/me",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
    """
    import uuid
    from core.utils.tokens import get_token_service
    from core.models.identity_models import User, Company
    
    # Создаем тестового пользователя
    user_id = f"test_user_{uuid.uuid4().hex[:8]}"
    
    # Создаем тестовую компанию
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
    
    # Создаем пользователя с компанией
    user = User(
        user_id=user_id,
        name="Test User",
        email=f"{user_id}@test.com",
        companies={company_id: ["owner", "admin"]},
        active_company_id=company_id
    )
    
    await frontend_container.user_repository.set(user)
    await frontend_container.subdomain_repository.set_mapping(company_subdomain, company_id)
    
    # Генерируем токен
    token_service = get_token_service()
    token = token_service.create_token(user_id, company_id=company_id)
    
    return token


@pytest_asyncio.fixture
async def auth_headers(auth_token):
    """
    Фикстура для авторизационных заголовков.
    Middleware поддерживает как cookies, так и Authorization header.
    
    Usage:
        async def test_api(frontend_client, auth_headers):
            response = await frontend_client.get(
                "/api/something",
                headers=auth_headers
            )
    """
    return {"Authorization": f"Bearer {auth_token}"}


# auth_token_system и auth_headers_system перенесены в tests/fixtures/auth.py
# Также добавлены фикстуры для второго пользователя системной компании и пользователей другой компании

# RAG фикстуры (rag_app, rag_client, rag_service) теперь в tests/fixtures/clients.py и tests/fixtures/services.py


@pytest_asyncio.fixture
async def rag_provider_pgvector():
    """
    Реальный pgvector провайдер для тестов.
    
    Использует PostgreSQL с расширением pgvector для хранения embeddings.
    """
    from core.rag.providers.pgvector_provider import PgVectorProvider
    
    config = {
        "db_url": os.environ.get("DATABASE__RAG_URL", "postgresql+asyncpg://platform_user:admin@localhost:54322/platform_rag"),
        "chunk_size": 1000,
        "chunk_overlap": 100
    }
    
    embedding_config = {
        "provider": "openrouter",
        "model": "text-embedding-3-small",
        "dimension": 1024,
        "base_url": "https://api.openai.com/v1",
    }
    
    provider = PgVectorProvider(config, embedding_config)
    yield provider
    
    # Cleanup: удаляем тестовые namespaces
    try:
        namespaces = await provider.list_namespaces()
        for namespace in namespaces:
            if namespace.name.startswith("test_"):
                await provider.delete_namespace(namespace.name)
    except Exception as e:
        # pgvector может быть недоступен при teardown
        pass


@pytest.fixture
def unique_namespace_name(unique_id):
    """
    Уникальное имя namespace для изоляции тестов.
    
    Usage:
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
    
    node_id = f"test_node_{unique_id}"
    node = NodeConfig(
        node_id=node_id,
        name="Test Node",
        type="llm_node",
        prompt="Test prompt",
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
        nodes={
            "main": {
                "type": "code",
                "code": "async def run(state):\n    return state",
            }
        },
    )
    await container.flow_repository.set(agent)
    yield flow_id
    await container.flow_repository.delete(flow_id)



