"""
Фикстуры TaskIQ-воркеров: только readiness-проверки готового стека.

Все процессы тестового стека (granian HTTP-сервисы + TaskIQ-воркеры) стартует
`make test-up` через `scripts/testing/stack.py up` — единственный владелец
процессов. pytest ничего не запускает и не убивает: фикстуры проверяют
готовность и падают с подсказкой выполнить `make test-up`.

Исключение — `taskiq_scheduler`: платформенный scheduler не входит в стек
(его тики мешали бы остальным тестам), интеграционный тест поднимает его
subprocess'ом на время сессии.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import pytest
import redis
import redis.exceptions as redis_exceptions

from tests.fixtures.test_database_env import TEST_DATABASE_ENV

_TASKIQ_REDIS_URL = "redis://localhost:63792/1"
_TASKIQ_CONSUMER_GROUP = "taskiq"
_READINESS_RETRY_SEC = 5.0

_PLATFORM_TEST_CONTROLLER_PID = Path("/tmp/platform_test_pytest_controller.pid")


def _pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def claim_pytest_controller_session() -> None:
    if _PLATFORM_TEST_CONTROLLER_PID.exists():
        try:
            existing_pid = int(
                _PLATFORM_TEST_CONTROLLER_PID.read_text(encoding="utf-8").strip()
            )
        except ValueError:
            existing_pid = -1
        if existing_pid > 0 and _pid_is_alive(existing_pid):
            raise RuntimeError(
                "pytest controller уже запущен "
                f"(pid={existing_pid}). Дождитесь завершения make test "
                "или завершите процесс вручную."
            )
        _PLATFORM_TEST_CONTROLLER_PID.unlink(missing_ok=True)
    _PLATFORM_TEST_CONTROLLER_PID.write_text(str(os.getpid()), encoding="utf-8")


def release_pytest_controller_session() -> None:
    if not _PLATFORM_TEST_CONTROLLER_PID.exists():
        return
    try:
        recorded_pid = int(
            _PLATFORM_TEST_CONTROLLER_PID.read_text(encoding="utf-8").strip()
        )
    except ValueError:
        _PLATFORM_TEST_CONTROLLER_PID.unlink(missing_ok=True)
        return
    if recorded_pid == os.getpid():
        _PLATFORM_TEST_CONTROLLER_PID.unlink(missing_ok=True)


def prepare_pytest_controller_session() -> None:
    claim_pytest_controller_session()


def _redis_client() -> redis.Redis:
    parsed = urlparse(_TASKIQ_REDIS_URL)
    if parsed.hostname is None or parsed.port is None:
        raise ValueError(f"Некорректный Redis URL: {_TASKIQ_REDIS_URL}")
    db_part = parsed.path.lstrip("/")
    return redis.Redis(
        host=parsed.hostname,
        port=parsed.port,
        db=int(db_part) if db_part else 0,
        decode_responses=True,
    )


def _taskiq_consumer_ready(client: redis.Redis, stream_name: str) -> bool:
    if not client.exists(stream_name):
        return False
    try:
        groups_response = client.xinfo_groups(stream_name)
    except redis_exceptions.ResponseError:
        return False
    if not isinstance(groups_response, list):
        raise TypeError(f"XINFO GROUPS вернул не list: {type(groups_response)!r}")
    for group in groups_response:
        if not isinstance(group, dict):
            raise TypeError(f"XINFO GROUPS элемент не dict: {type(group)!r}")
        if str(group.get("name")) != _TASKIQ_CONSUMER_GROUP:
            continue
        consumers_raw = group.get("consumers")
        if consumers_raw is None:
            raise ValueError(f"XINFO GROUPS group {_TASKIQ_CONSUMER_GROUP!r} missing consumers")
        return int(consumers_raw) >= 1
    return False


def require_taskiq_worker(worker_name: str, stream_name: str) -> None:
    """Проверяет, что TaskIQ-воркер стека слушает свой стрим; иначе pytest.fail."""
    client = _redis_client()
    deadline = time.monotonic() + _READINESS_RETRY_SEC
    try:
        while time.monotonic() < deadline:
            try:
                if _taskiq_consumer_ready(client, stream_name):
                    return
            except redis_exceptions.ConnectionError:
                pass
            time.sleep(0.25)
    finally:
        client.close()
    pytest.fail(
        f"TaskIQ-воркер {worker_name} не запущен (нет consumer в стриме {stream_name!r}, "
        f"{_TASKIQ_REDIS_URL}) — выполните make test-up",
        pytrace=False,
    )


@pytest.fixture(scope="session")
def taskiq_worker(sandbox_services):
    """flows_worker стека: исполняет flow/code задачи (нужны sandbox-сервисы)."""
    _ = sandbox_services
    require_taskiq_worker("flows_worker", "flows_worker")


@pytest.fixture(scope="session")
def rag_worker(provider_litserve_service):
    """rag_worker стека: индексация документов в pgvector через provider_litserve."""
    _ = provider_litserve_service
    require_taskiq_worker("rag_worker", "rag")


@pytest.fixture(scope="session")
def search_worker(rag_worker, rag_service, search_service):
    """search_worker стека: crawl orchestrator tick, discover/fetch, RAG ingest по HTTP."""
    _ = rag_worker, rag_service, search_service
    require_taskiq_worker("search_worker", "search")


@pytest.fixture(scope="session")
def sync_worker(frontend_service):
    """sync_worker стека: транскрипция сообщений/звонков, файлы через frontend."""
    _ = frontend_service
    require_taskiq_worker("sync_worker", "sync")


@pytest.fixture(scope="session")
def crm_worker():
    """crm_worker (analyze/import) и crm_summary_worker (daily/period summary)."""
    require_taskiq_worker("crm_worker", "crm")
    require_taskiq_worker("crm_summary_worker", "crm_summary")


@pytest.fixture(scope="session")
def shop_worker(shop_service):
    """shop_worker стека: пересборка снапшотов витрин, домены, уведомления."""
    _ = shop_service
    require_taskiq_worker("shop_worker", "shop")


@pytest.fixture(scope="session")
def geo_worker(geo_service):
    """geo_worker стека: OSM-импорт справочника и графа (bootstrap + тики)."""
    _ = geo_service
    require_taskiq_worker("geo_worker", "geo")


@pytest.fixture
def taskiq_broker(rag_worker):
    """
    Возвращает TaskIQ broker для RAG тестов.

    Зависит от rag_worker - гарантирует что worker запущен.
    """
    from core.tasks.registry import queue_broker

    broker = queue_broker("flows_worker")
    if broker is None:
        raise RuntimeError("flows_worker broker is not registered")
    return broker


def _terminate_process_group_or_pid(pid: int, *, graceful_timeout: float = 0.2) -> None:
    """Завершает группу subprocess-процесса, запущенного с start_new_session=True."""
    try:
        pgid = os.getpgid(pid)
    except OSError:
        return

    if pgid == pid:
        try:
            os.killpg(pgid, signal.SIGTERM)
        except OSError:
            return
        time.sleep(graceful_timeout)
        try:
            os.killpg(pgid, signal.SIGKILL)
        except OSError:
            pass
        return

    try:
        os.kill(pid, signal.SIGTERM)
        time.sleep(graceful_timeout)
        try:
            os.kill(pid, 0)
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    except OSError:
        pass


@pytest.fixture(scope="session")
def taskiq_scheduler():
    """
    Запускает TaskIQ scheduler как subprocess.
    Scheduler проверяет scheduled tasks и отправляет их worker-у.

    scope="session" - scheduler запускается один раз на все тесты.
    """
    import tempfile

    log_dir = tempfile.mkdtemp(prefix="taskiq_scheduler_")
    stdout_log = open(f"{log_dir}/stdout.log", "w")
    stderr_log = open(f"{log_dir}/stderr.log", "w")

    scheduler_process = subprocess.Popen(
        [sys.executable, "-m", "taskiq", "scheduler", "apps.scheduler.scheduler:scheduler"],
        stdout=stdout_log,
        stderr=stderr_log,
        env={
            **os.environ,
            **TEST_DATABASE_ENV,
            "TESTING": "true",
            "DATABASE__REDIS_URL": "redis://localhost:63792/0",
            "TASKS__BROKER_URL": "redis://localhost:63792/1",
        },
        start_new_session=True,
    )

    # Ждём пока scheduler стартанёт
    time.sleep(2)

    # Проверяем что scheduler запустился
    if scheduler_process.poll() is not None:
        stdout_log.close()
        stderr_log.close()
        with open(f"{log_dir}/stdout.log") as f:
            stdout = f.read()
        with open(f"{log_dir}/stderr.log") as f:
            stderr = f.read()
        print(f"Scheduler stdout: {stdout}")
        print(f"Scheduler stderr: {stderr}")
        raise RuntimeError(f"Планировщик TaskIQ не запустился: {stderr}")

    yield scheduler_process

    _terminate_process_group_or_pid(scheduler_process.pid, graceful_timeout=0.5)
    try:
        scheduler_process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        scheduler_process.kill()
        scheduler_process.wait(timeout=2)
    finally:
        stdout_log.close()
        stderr_log.close()
