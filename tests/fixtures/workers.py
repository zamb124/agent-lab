"""
Фикстуры для управления worker процессами в тестах.

Этот модуль содержит:
- SessionWorkerManager: универсальный класс для управления worker процессами
- Фикстуры для TaskIQ worker и RAGWorker
"""

import os
import signal
import socket
import subprocess
import sys
import time
import asyncio
from urllib.parse import urlparse
from pathlib import Path
from typing import Any, Dict, List

import pytest
import redis.asyncio as redis_asyncio
from filelock import FileLock

from tests.fixtures.test_database_env import TEST_DATABASE_ENV


# Константы для файлов блокировки и PID
_TASKIQ_WORKER_LOCK = "/tmp/platform_test_taskiq_worker.lock"
_TASKIQ_WORKER_PID = "/tmp/platform_test_taskiq_worker.pid"
_RAG_WORKER_LOCK = "/tmp/platform_test_rag_worker.lock"
_RAG_WORKER_PID = "/tmp/platform_test_rag_worker.pid"

_SYNC_WORKER_LOCK = "/tmp/platform_test_sync_taskiq_worker.lock"
_SYNC_WORKER_PID = "/tmp/platform_test_sync_taskiq_worker.pid"
_CRM_WORKER_LOCK = "/tmp/platform_test_crm_taskiq_worker.lock"
_CRM_WORKER_PID = "/tmp/platform_test_crm_taskiq_worker.pid"


def _force_restart_sync_worker() -> None:
    subprocess.run(["pkill", "-f", "apps.sync_worker.worker:worker_app"], capture_output=True, text=True)
    Path(_SYNC_WORKER_PID).unlink(missing_ok=True)
    Path(f"{_SYNC_WORKER_PID}.refs").unlink(missing_ok=True)
    print("🔄 Принудительный перезапуск sync worker: старые процессы и PID-файлы очищены")


def _clear_taskiq_stream(stream_name: str, redis_url: str) -> None:
    parsed = urlparse(redis_url)
    if parsed.hostname is None or parsed.port is None:
        raise ValueError(f"Некорректный Redis URL для очистки очереди: {redis_url}")
    db_part = parsed.path.lstrip("/")
    db_index = db_part if db_part != "" else "0"
    async def _reset_stream() -> int:
        client = redis_asyncio.Redis(
            host=parsed.hostname,
            port=parsed.port,
            db=int(db_index),
            decode_responses=True,
        )
        stream_exists = bool(await client.exists(stream_name))
        if stream_exists:
            await client.xtrim(stream_name, maxlen=0, approximate=False)
        else:
            await client.xadd(stream_name, {"init": "1"})
            await client.xtrim(stream_name, maxlen=0, approximate=False)

        groups = await client.xinfo_groups(stream_name)
        group_names = {str(group["name"]) for group in groups}
        if "taskiq" not in group_names:
            await client.xgroup_create(name=stream_name, groupname="taskiq", id="$", mkstream=True)
        await client.aclose()
        return 1

    reset_done = asyncio.run(_reset_stream())
    print(f"🧹 Очистка очереди {stream_name}: reset -> {reset_done}, group=taskiq")


class SessionWorkerManager:
    """
    Универсальный менеджер для запуска и управления worker процессами в pytest.
    
    Поддерживает:
    - Запуск worker один раз на всю сессию тестов
    - Переиспользование worker несколькими pytest worker'ами (pytest-xdist)
    - Reference counting для корректной остановки worker
    - Очистку старых процессов перед запуском
    - Убийство дочерних процессов (multiprocessing)
    
    Примеры использования:
    
    1. TaskIQ worker:
        manager = SessionWorkerManager(
            name="TaskIQ",
            lock_file="/tmp/taskiq.lock",
            pid_file="/tmp/taskiq.pid",
            command=[sys.executable, "-m", "taskiq", "worker", "apps.flows_worker.worker:worker_app"],
            env={"TESTING": "true"},
            cleanup_patterns=["taskiq.*worker", "multiprocessing.spawn"],
            startup_wait=3
        )
        
        @pytest.fixture(scope="session")
        def taskiq_worker():
            with manager.start() as process:
                yield process
    
    2. Custom worker:
        manager = SessionWorkerManager(
            name="MyWorker",
            lock_file="/tmp/my_worker.lock",
            pid_file="/tmp/my_worker.pid",
            command=[sys.executable, "-m", "my_app.worker"],
            env={"ENV": "test"},
            cleanup_patterns=["my_app.worker"],
            startup_wait=5,
            log_file="/tmp/my_worker.log",
            err_file="/tmp/my_worker_err.log"
        )
        
        @pytest.fixture(scope="session")
        def my_worker():
            with manager.start() as process:
                yield process
    
    Как это работает:
    - При первом запуске теста: создается lock, запускается worker, PID сохраняется, ref_count = 1
    - При параллельном запуске (pytest-xdist): другие pytest worker'ы видят PID, увеличивают ref_count
    - При завершении теста: ref_count уменьшается
    - Когда ref_count становится 0: последний pytest worker убивает worker процесс
    """
    
    def __init__(
        self,
        name: str,
        lock_file: str,
        pid_file: str,
        command: List[str],
        env: Dict[str, str] = None,
        cleanup_patterns: List[str] = None,
        startup_wait: float = 2.0,
        log_file: str = None,
        err_file: str = None,
    ):
        """
        Args:
            name: Название worker (для логов)
            lock_file: Путь к файлу блокировки
            pid_file: Путь к файлу с PID
            command: Команда для запуска worker
            env: Переменные окружения
            cleanup_patterns: Паттерны для pkill (очистка старых процессов)
            startup_wait: Верхняя граница ожидания живого процесса после Popen (секунды)
            log_file: Путь к файлу stdout логов
            err_file: Путь к файлу stderr логов
        """
        self.name = name
        self.lock_file = lock_file
        self.pid_file = pid_file
        self.ref_count_file = f"{pid_file}.refs"
        self.command = command
        self.env = env or {}
        self.cleanup_patterns = cleanup_patterns or []
        self.startup_wait = startup_wait
        self.log_file = log_file or f"/tmp/{name.lower()}_worker.log"
        self.err_file = err_file or f"/tmp/{name.lower()}_worker_err.log"
        
        self.lock = FileLock(self.lock_file, timeout=300)
        self.pid_path = Path(self.pid_file)
        self.ref_count_path = Path(self.ref_count_file)
    
    def _cleanup_old_processes(self):
        """Убивает старые worker процессы по паттернам."""
        print(f"🧹 Очистка старых {self.name} worker процессов...")
        
        for pattern in self.cleanup_patterns:
            subprocess.run(
                ["pkill", "-9", "-f", pattern],
                check=False,
                capture_output=True
            )
        
        time.sleep(0.05)
        print(f"✅ Старые {self.name} worker процессы очищены")
    
    def _increment_ref_count(self) -> int:
        """Увеличивает счетчик ссылок. Возвращает новое значение."""
        ref_count = 1
        if self.ref_count_path.exists():
            try:
                ref_count = int(self.ref_count_path.read_text().strip()) + 1
            except (ValueError, OSError):
                ref_count = 1
        self.ref_count_path.write_text(str(ref_count))
        return ref_count
    
    def _decrement_ref_count(self) -> int:
        """Уменьшает счетчик ссылок. Возвращает новое значение."""
        ref_count = 0
        if self.ref_count_path.exists():
            try:
                ref_count = int(self.ref_count_path.read_text().strip()) - 1
            except (ValueError, OSError):
                ref_count = 0
        
        if ref_count > 0:
            self.ref_count_path.write_text(str(ref_count))
        else:
            self.ref_count_path.unlink(missing_ok=True)
        
        return ref_count
    
    def _check_existing_worker(self) -> bool:
        """
        Проверяет существующий worker.
        
        Returns:
            True если worker запущен и можно его переиспользовать
        """
        if self.pid_path.exists():
            try:
                existing_pid = int(self.pid_path.read_text().strip())
                os.kill(existing_pid, 0)  # Проверка что процесс жив
                return True
            except (OSError, ValueError):
                # Процесс не существует или PID невалидный
                self.pid_path.unlink(missing_ok=True)
                self.ref_count_path.unlink(missing_ok=True)
        return False
    
    def _start_worker(self) -> subprocess.Popen:
        """Запускает новый worker процесс."""
        self._cleanup_old_processes()
        
        # Логи
        worker_log = open(self.log_file, "w")
        worker_err = open(self.err_file, "w")
        
        # Запускаем worker
        worker_process = subprocess.Popen(
            self.command,
            stdout=worker_log,
            stderr=worker_err,
            env={**os.environ, **self.env},
        )
        
        # Живой процесс без немедленного exit достаточен; дальше taskiq поднимется сам.
        # Не держим секунды sleep: при pytest-xdist lock общий, другие gw ждут здесь же.
        bootstrap_ok_at = min(0.35, self.startup_wait)
        started = time.monotonic()
        while True:
            if worker_process.poll() is not None:
                worker_log.close()
                worker_err.close()
                with open(self.err_file, "r") as f:
                    err_content = f.read()
                raise RuntimeError(
                    f"{self.name} worker failed to start. Error log:\n{err_content}"
                )
            elapsed = time.monotonic() - started
            if elapsed >= self.startup_wait:
                break
            if elapsed >= bootstrap_ok_at:
                break
            time.sleep(0.05)
        
        # Сохраняем PID
        self.pid_path.write_text(str(worker_process.pid))
        print(f"✅ {self.name} worker started (PID: {worker_process.pid})")
        
        return worker_process
    
    def _stop_worker(self, pid: int):
        """Останавливает worker и его дочерние процессы."""
        print(f"🛑 Останавливаем {self.name} worker (PID: {pid}, последний ref)...")
        
        # Убиваем процесс
        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(0.2)
            try:
                os.kill(pid, 0)  # Проверка что еще жив
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        except OSError:
            pass
        
        # Убиваем все дочерние процессы
        print(f"🧹 Очистка оставшихся child процессов {self.name}...")
        for pattern in self.cleanup_patterns:
            subprocess.run(
                ["pkill", "-9", "-f", pattern],
                check=False,
                capture_output=True
            )
        
        self.pid_path.unlink(missing_ok=True)
        print(f"✅ {self.name} worker stopped (PID: {pid})")
    
    def start(self):
        """
        Контекстный менеджер для запуска worker.
        
        Usage:
            with manager.start() as process:
                yield process
        """
        worker_process = None
        is_owner = False
        
        with self.lock:
            # Проверяем существующий worker
            if self._check_existing_worker():
                existing_pid = int(self.pid_path.read_text().strip())
                ref_count = self._increment_ref_count()
                print(
                    f"✅ Переиспользуем существующий {self.name} worker "
                    f"(PID: {existing_pid}, refs: {ref_count})"
                )
            else:
                # Мы первые - запускаем worker
                is_owner = True
                self.ref_count_path.write_text("1")
                worker_process = self._start_worker()
        
        # Контекстный менеджер для cleanup
        class _WorkerContext:
            def __init__(ctx_self, manager, process):
                ctx_self.manager = manager
                ctx_self.process = process
            
            def __enter__(ctx_self):
                return ctx_self.process
            
            def __exit__(ctx_self, exc_type, exc_val, exc_tb):
                # Уменьшаем счетчик ссылок под блокировкой
                with ctx_self.manager.lock:
                    ref_count = ctx_self.manager._decrement_ref_count()
                    
                    if ref_count > 0:
                        print(f"📉 {ctx_self.manager.name} worker refs: {ref_count}")
                    else:
                        # Мы последние - убиваем worker
                        if ctx_self.manager.pid_path.exists():
                            try:
                                worker_pid = int(
                                    ctx_self.manager.pid_path.read_text().strip()
                                )
                                ctx_self.manager._stop_worker(worker_pid)
                            except (ValueError, OSError) as e:
                                print(
                                    f"⚠️  Ошибка при остановке {ctx_self.manager.name} "
                                    f"worker: {e}"
                                )
                                ctx_self.manager.pid_path.unlink(missing_ok=True)
        
        return _WorkerContext(self, worker_process)


# ============================================================================
# Фикстуры для worker'ов
# ============================================================================

@pytest.fixture(scope="session")
def taskiq_worker():
    """
    Запускает TaskIQ worker для тестов.
    
    В Docker: использует существующий flows_worker_test контейнер
    Локально: запускает worker как subprocess через SessionWorkerManager
    
    scope="session" - worker запускается один раз на все тесты.
    
    При pytest-xdist используется filelock для синхронизации - 
    первый worker запускает TaskIQ worker, остальные ждут и переиспользуют его.
    """
    # В Docker worker уже запущен
    if os.environ.get("EXTERNAL_AGENT_TEST_URL"):
        yield None
        return
    
    # Используем SessionWorkerManager для управления worker
    manager = SessionWorkerManager(
        name="TaskIQ",
        lock_file=_TASKIQ_WORKER_LOCK,
        pid_file=_TASKIQ_WORKER_PID,
        # Один процесс: mock LLM в Redis (mock_llm:responses) без атомарного pop — при -w 2
        # параллельные задачи крадут ответы друг у друга и E2E (триггеры, RAG) падают.
        command=[sys.executable, "-m", "taskiq", "worker", "apps.flows_worker.worker:worker_app", "-w", "1"],
        env={
            **TEST_DATABASE_ENV,
            "TESTING": "true",
            "DATABASE__REDIS_URL": "redis://localhost:63792/0",
            "TASKS__BROKER_URL": "redis://localhost:63792/1",
            "AUTH__PERMISSIONS_ENABLED": "false",
            "CALLS__LIVEKIT_URL": "ws://localhost:7890",
            "CALLS__LIVEKIT_PUBLIC_URL": "http://localhost:7890",
            "CALLS__LIVEKIT_API_KEY": "devkey",
            "CALLS__LIVEKIT_API_SECRET": "secret",
        },
        cleanup_patterns=[
            "taskiq.*apps.flows_worker.worker:worker_app",
            "multiprocessing.spawn.*spawn_main",
            "multiprocessing.resource_tracker",
        ],
        log_file="/tmp/taskiq_worker_test.log",
        err_file="/tmp/taskiq_worker_test_err.log",
    )
    
    with manager.start() as worker_process:
        yield worker_process


@pytest.fixture(scope="session")
def rag_worker():
    """
    Запускает RAGWorker для обработки RAG задач в тестах.
    
    RAGWorker обрабатывает задачи индексации документов в pgvector через SessionWorkerManager.
    
    scope="session" - worker запускается один раз на все тесты.
    
    При pytest-xdist используется filelock для синхронизации - 
    первый worker запускает RAGWorker, остальные ждут и переиспользуют его.
    """
    # В Docker worker уже запущен
    if os.environ.get("EXTERNAL_AGENT_TEST_URL"):
        yield None
        return
    
    # Один процесс: меньше гонок при нагрузочном прогоне и общей БД/S3.
    manager = SessionWorkerManager(
        name="RAGWorker",
        lock_file=_RAG_WORKER_LOCK,
        pid_file=_RAG_WORKER_PID,
        command=[sys.executable, "-m", "taskiq", "worker", "apps.rag_worker.worker:worker_app", "-w", "1"],
        env={
            **TEST_DATABASE_ENV,
            "TESTING": "true",
            "DATABASE__REDIS_URL": "redis://localhost:63792/0",
            "TASKS__BROKER_URL": "redis://localhost:63792/1",
            "AUTH__PERMISSIONS_ENABLED": "false",
            "S3__DEFAULT_BUCKET": "test-bucket",
            "S3__BUCKETS__TEST-BUCKET__ENDPOINT_URL": "http://localhost:19002",
            "RAG__PROVIDERS__PGVECTOR__MOCK_EMBEDDINGS": "true",
        },
        cleanup_patterns=[
            "apps.rag_worker.worker",
            "multiprocessing.spawn.*spawn_main",
            "multiprocessing.resource_tracker",
        ],
        log_file="/tmp/rag_worker_test.log",
        err_file="/tmp/rag_worker_test_err.log",
    )
    
    with manager.start() as worker_process:
        yield worker_process


@pytest.fixture(scope="session")
def sync_worker():
    """
    TaskIQ worker очереди sync (apps.sync_worker.worker:worker_app).

    Нужен для REST/WS, где вызывается handle_command.kiq() (создание space/channel и т.д.).
    """
    if os.environ.get("EXTERNAL_AGENT_TEST_URL"):
        yield None
        return

    _force_restart_sync_worker()
    _clear_taskiq_stream("sync", "redis://localhost:63792/1")

    manager = SessionWorkerManager(
        name="SyncTaskIQ",
        lock_file=_SYNC_WORKER_LOCK,
        pid_file=_SYNC_WORKER_PID,
        command=[
            sys.executable,
            "-m",
            "taskiq",
            "worker",
            "apps.sync_worker.worker:worker_app",
            "-w",
            "2",
        ],
        env={
            **TEST_DATABASE_ENV,
            "TESTING": "true",
            "DATABASE__REDIS_URL": "redis://localhost:63792/0",
            "TASKS__BROKER_URL": "redis://localhost:63792/1",
            "AUTH__PERMISSIONS_ENABLED": "false",
            "CALLS__LIVEKIT_URL": "ws://localhost:7890",
            "CALLS__LIVEKIT_PUBLIC_URL": "http://localhost:7890",
            "CALLS__LIVEKIT_API_KEY": "devkey",
            "CALLS__LIVEKIT_API_SECRET": "secret",
            "S3__ENABLED": "true",
            "S3__DEFAULT_BUCKET": "test-bucket",
            "S3__BUCKETS__TEST-BUCKET__ENDPOINT_URL": "http://localhost:19002",
            "S3__BUCKETS__TEST-BUCKET__ACCESS_KEY_ID": "minioadmin",
            "S3__BUCKETS__TEST-BUCKET__SECRET_ACCESS_KEY": "minioadmin",
            "S3__BUCKETS__TEST-BUCKET__REGION_NAME": "us-east-1",
            "S3__BUCKETS__TEST-BUCKET__PROVIDER": "minio",
            "STT__PROVIDER": "mock",
            "STT__MOCK_TRANSCRIPT_TEXT": "Тестовая транскрипция sync worker",
        },
        cleanup_patterns=[
            "apps.sync_worker.worker",
            "taskiq.*apps.sync_worker.worker:worker_app",
            "multiprocessing.spawn.*spawn_main",
            "multiprocessing.resource_tracker",
        ],
        log_file="/tmp/sync_taskiq_worker_test.log",
        err_file="/tmp/sync_taskiq_worker_test_err.log",
    )

    with manager.start() as worker_process:
        yield worker_process


@pytest.fixture(scope="session")
def crm_worker():
    """
    TaskIQ worker очереди crm (apps.crm_worker.worker:worker_app).
    """
    if os.environ.get("EXTERNAL_AGENT_TEST_URL"):
        yield None
        return

    manager = SessionWorkerManager(
        name="CRMTaskIQ",
        lock_file=_CRM_WORKER_LOCK,
        pid_file=_CRM_WORKER_PID,
        command=[
            sys.executable,
            "-m",
            "taskiq",
            "worker",
            "apps.crm_worker.worker:worker_app",
            "-w",
            "1",
        ],
        env={
            **TEST_DATABASE_ENV,
            "TESTING": "true",
            "DATABASE__REDIS_URL": "redis://localhost:63792/0",
            "TASKS__BROKER_URL": "redis://localhost:63792/1",
            "AUTH__PERMISSIONS_ENABLED": "false",
        },
        cleanup_patterns=[
            "apps.crm_worker.worker",
            "taskiq.*apps.crm_worker.worker:worker_app",
            "multiprocessing.spawn.*spawn_main",
            "multiprocessing.resource_tracker",
        ],
        log_file="/tmp/crm_taskiq_worker_test.log",
        err_file="/tmp/crm_taskiq_worker_test_err.log",
    )

    with manager.start() as worker_process:
        yield worker_process


@pytest.fixture
def taskiq_broker(rag_worker):
    """
    Возвращает TaskIQ broker для RAG тестов.
    
    Зависит от rag_worker - гарантирует что worker запущен.
    """
    from apps.flows_worker.broker import broker
    return broker


@pytest.fixture(scope="session")
def taskiq_scheduler():
    """
    Запускает TaskIQ scheduler как subprocess.
    Scheduler проверяет scheduled tasks и отправляет их worker-у.
    
    scope="session" - scheduler запускается один раз на все тесты.
    """
    import tempfile
    
    # В Docker scheduler может быть отдельным контейнером
    if os.environ.get("EXTERNAL_AGENT_TEST_URL"):
        yield None
        return
    
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
            "AUTH__PERMISSIONS_ENABLED": "false",
        },
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
        raise RuntimeError(f"Scheduler failed to start: {stderr}")

    yield scheduler_process
    
    scheduler_process.terminate()
    try:
        scheduler_process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        scheduler_process.kill()
        scheduler_process.wait(timeout=2)
    finally:
        stdout_log.close()
        stderr_log.close()


class SessionServerManager:
    """
    Универсальный менеджер для запуска HTTP серверов в pytest.
    
    Аналог SessionWorkerManager но для uvicorn серверов.
    Запускает сервер один раз на всю сессию тестов с поддержкой pytest-xdist.
    
    Пример использования:
        manager = SessionServerManager(
            name="RAG",
            lock_file="/tmp/rag_server.lock",
            pid_file="/tmp/rag_server.pid",
            app_path="apps.rag.main:app",
            port=8004,
            startup_wait=2.0
        )
        
        @pytest.fixture(scope="session")
        def rag_server():
            with manager.start():
                yield
    """
    
    def __init__(
        self,
        name: str,
        lock_file: str,
        pid_file: str,
        app_path: str,
        port: int,
        host: str = "127.0.0.1",
        startup_wait: float = 2.0,
        log_file: str = None,
        err_file: str = None,
        env: Dict[str, str] = None,
    ):
        """
        Args:
            name: Название сервера (для логов)
            lock_file: Путь к файлу блокировки
            pid_file: Путь к файлу с PID
            app_path: Путь к ASGI приложению (e.g. "apps.rag.main:app")
            port: Порт для сервера
            host: Хост для сервера
            startup_wait: Время ожидания запуска сервера
            log_file: Путь к файлу логов
            err_file: Путь к файлу ошибок
            env: Дополнительные переменные окружения
        """
        self.name = name
        self.lock_file = lock_file
        self.pid_path = Path(pid_file)
        self.ref_count_path = Path(f"{pid_file}.ref_count")
        self.app_path = app_path
        self.port = port
        self.host = host
        self.startup_wait = startup_wait
        self.log_file = log_file or f"/tmp/{name.lower()}_server_test.log"
        self.err_file = err_file or f"/tmp/{name.lower()}_server_test_err.log"
        self.env = env or {}
        self.lock = FileLock(self.lock_file, timeout=60)
    
    def _cleanup_old_processes(self):
        """Убивает старые процессы сервера перед запуском"""
        print(f"🧹 Очистка старых {self.name} server процессов...")
        
        subprocess.run(
            ["pkill", "-9", "-f", f"uvicorn.*{self.app_path}"],
            check=False,
            capture_output=True
        )
        
        self.pid_path.unlink(missing_ok=True)
        self.ref_count_path.unlink(missing_ok=True)
        
        print(f"✅ Старые {self.name} server процессы очищены")
    
    def _increment_ref_count(self) -> int:
        """Увеличивает счетчик ссылок"""
        if self.ref_count_path.exists():
            count = int(self.ref_count_path.read_text().strip())
        else:
            count = 0
        
        count += 1
        self.ref_count_path.write_text(str(count))
        
        return count
    
    def _decrement_ref_count(self) -> int:
        """Уменьшает счетчик ссылок"""
        if self.ref_count_path.exists():
            count = int(self.ref_count_path.read_text().strip())
        else:
            return 0
        
        count = max(0, count - 1)
        
        if count > 0:
            self.ref_count_path.write_text(str(count))
        else:
            self.ref_count_path.unlink(missing_ok=True)
        
        return count
    
    def _check_existing_server(self) -> bool:
        """Проверяет существующий server"""
        if self.pid_path.exists():
            try:
                existing_pid = int(self.pid_path.read_text().strip())
                os.kill(existing_pid, 0)
                if not self._wait_for_port(timeout=0.5):
                    self.pid_path.unlink(missing_ok=True)
                    self.ref_count_path.unlink(missing_ok=True)
                    return False
                return True
            except (OSError, ValueError):
                self.pid_path.unlink(missing_ok=True)
                self.ref_count_path.unlink(missing_ok=True)
        return False
    
    def _wait_for_port(self, timeout: float = 30.0) -> bool:
        """Ждет пока порт станет доступен"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                with socket.create_connection((self.host, self.port), timeout=1.0):
                    return True
            except (socket.error, OSError):
                time.sleep(0.1)
        return False
    
    def _start_server(self) -> subprocess.Popen:
        """Запускает новый uvicorn server"""
        self._cleanup_old_processes()
        
        server_log = open(self.log_file, "w")
        server_err = open(self.err_file, "w")
        
        command = [
            sys.executable, "-m", "uvicorn",
            self.app_path,
            "--host", self.host,
            "--port", str(self.port),
            "--log-level", "error"
        ]
        
        full_env = {**os.environ, **self.env}
        
        server_process = subprocess.Popen(
            command,
            stdout=server_log,
            stderr=server_err,
            env=full_env,
        )
        
        # Ждем пока порт станет доступен
        if not self._wait_for_port(timeout=self.startup_wait):
            server_process.kill()
            server_log.close()
            server_err.close()
            with open(self.err_file, "r") as f:
                err_content = f.read()
            raise RuntimeError(
                f"{self.name} server failed to start (port {self.port} not available). Error log:\n{err_content}"
            )
        
        if server_process.poll() is not None:
            server_log.close()
            server_err.close()
            with open(self.err_file, "r") as f:
                err_content = f.read()
            raise RuntimeError(
                f"{self.name} server failed to start. Error log:\n{err_content}"
            )
        
        self.pid_path.write_text(str(server_process.pid))
        print(f"✅ {self.name} server started (PID: {server_process.pid}, port: {self.port})")
        
        return server_process
    
    def _stop_server(self, pid: int):
        """Останавливает server"""
        print(f"🛑 Останавливаем {self.name} server (PID: {pid}, последний ref)...")
        
        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(0.2)
            try:
                os.kill(pid, 0)
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        except OSError:
            pass
        
        self.pid_path.unlink(missing_ok=True)
        print(f"✅ {self.name} server stopped (PID: {pid})")
    
    def start(self):
        """
        Контекстный менеджер для запуска server.
        
        Usage:
            with manager.start():
                yield
        """
        server_process = None
        is_owner = False
        
        with self.lock:
            if self._check_existing_server():
                existing_pid = int(self.pid_path.read_text().strip())
                ref_count = self._increment_ref_count()
                print(
                    f"✅ Переиспользуем существующий {self.name} server "
                    f"(PID: {existing_pid}, port: {self.port}, refs: {ref_count})"
                )
            else:
                is_owner = True
                self.ref_count_path.write_text("1")
                server_process = self._start_server()
        
        class _ServerContext:
            def __init__(ctx_self, manager):
                ctx_self.manager = manager
            
            def __enter__(ctx_self):
                return None
            
            def __exit__(ctx_self, exc_type, exc_val, exc_tb):
                with ctx_self.manager.lock:
                    ref_count = ctx_self.manager._decrement_ref_count()
                    
                    if ref_count == 0:
                        if ctx_self.manager.pid_path.exists():
                            pid = int(ctx_self.manager.pid_path.read_text().strip())
                            ctx_self.manager._stop_server(pid)
                    else:
                        print(
                            f"✅ {ctx_self.manager.name} server сохранен "
                            f"(осталось refs: {ref_count})"
                        )
        
        return _ServerContext(self)
