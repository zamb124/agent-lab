"""
Конфигурация для frontend тестов.

Основные фикстуры наследуются из tests/conftest.py.
Здесь только специфичные для frontend настройки.
"""

import os
import pytest
import multiprocessing
import time
import socket


def get_free_port() -> int:
    """Получить свободный порт"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def run_agents_server(host: str, port: int):
    """Запуск agents uvicorn сервера в отдельном процессе"""
    import uvicorn
    uvicorn.run(
        "apps.agents.main:app",
        host=host,
        port=port,
        log_level="warning"
    )


def wait_for_server(host: str, port: int, timeout: float = 30.0) -> bool:
    """Ждать пока сервер станет доступен"""
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.2)
    return False


@pytest.fixture(scope="session")
def agents_service(migrated_db):
    """
    Запускает agents сервис в отдельном процессе.
    
    Нужен для тестов где frontend делает HTTP запросы к agents.
    Например: Repository Gateway, межсервисное взаимодействие.
    """
    port = get_free_port()
    host = "127.0.0.1"
    
    os.environ["AGENTS_SERVICE_HOST"] = host
    os.environ["AGENTS_SERVICE_PORT"] = str(port)
    os.environ["TEST_AGENTS_SERVICE_URL"] = f"http://{host}:{port}"
    
    server_process = multiprocessing.Process(
        target=run_agents_server,
        args=(host, port),
        daemon=True
    )
    server_process.start()
    
    if not wait_for_server(host, port):
        server_process.terminate()
        raise RuntimeError(f"Agents сервис не запустился на {host}:{port}")
    
    print(f"\nAgents сервис запущен на http://{host}:{port}")
    
    yield {"host": host, "port": port, "url": f"http://{host}:{port}"}
    
    server_process.terminate()
    server_process.join(timeout=5)
    print("Agents сервис остановлен")
