"""
Async Playwright фикстуры для e2e тестов.

E2E тесты используют async Playwright API для совместимости с pytest-asyncio.

Запуск:
    uv run pytest tests/frontend/e2e/ -v --headed  # с браузером
    uv run pytest tests/frontend/e2e/ -v           # headless режим
"""

import os
import pytest
import multiprocessing
import time
import socket
import uuid


FRONTEND_PORT = int(os.getenv("FRONTEND_PORT", "8002"))


def get_free_port() -> int:
    """Получить свободный порт"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def run_server(host: str, port: int):
    """Запуск uvicorn сервера в отдельном процессе"""
    import uvicorn
    from apps.frontend.main import app
    
    uvicorn.run(app, host=host, port=port, log_level="warning")


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
def live_server(migrated_db):
    """
    Запускает frontend сервер в отдельном процессе.
    Доступен на протяжении всей сессии тестов.
    Зависит от migrated_db чтобы БД была готова.
    """
    port = get_free_port()
    host = "127.0.0.1"
    
    server_process = multiprocessing.Process(
        target=run_server,
        args=(host, port),
        daemon=True
    )
    server_process.start()
    
    if not wait_for_server(host, port):
        server_process.terminate()
        raise RuntimeError(f"Сервер не запустился на {host}:{port}")
    
    yield {"host": host, "port": port, "url": f"http://{host}:{port}"}
    
    server_process.terminate()
    server_process.join(timeout=5)


@pytest.fixture(scope="session")
def e2e_auth_token():
    """Создает JWT токен для e2e тестов (session scope для переиспользования)"""
    from core.utils.tokens import get_token_service
    
    unique_suffix = uuid.uuid4().hex[:8]
    token_service = get_token_service()
    
    return token_service.create_token(
        user_id=f"e2e_user_{unique_suffix}",
        company_id=f"e2e_company_{unique_suffix}",
        session_id=f"e2e_session_{unique_suffix}"
    )


@pytest.fixture(scope="session")
def browser_context_args(e2e_auth_token):
    """Настройки контекста браузера Playwright с авторизацией"""
    return {
        "viewport": {"width": 1920, "height": 1080},
        "locale": "ru-RU",
        "timezone_id": "Europe/Moscow",
        "storage_state": {
            "cookies": [
                {
                    "name": "auth_token",
                    "value": e2e_auth_token,
                    "domain": "127.0.0.1",
                    "path": "/"
                }
            ],
            "origins": []
        }
    }


@pytest.fixture(scope="session")
def browser_type_launch_args():
    """Аргументы запуска браузера"""
    return {
        "headless": os.getenv("HEADED", "").lower() not in ("true", "1"),
        "slow_mo": int(os.getenv("SLOW_MO", "0")),
    }


@pytest.fixture(scope="session")
def server_url(live_server):
    """Базовый URL frontend сервиса (из live_server)"""
    return live_server["url"]


@pytest.fixture(scope="session")
def url_builder(live_server):
    """Фабрика URL с поддержкой поддоменов"""
    port = live_server["port"]
    
    def build_url(path: str, subdomain: str = None) -> str:
        if subdomain:
            return f"http://{subdomain}.127.0.0.1:{port}{path}"
        return f"http://127.0.0.1:{port}{path}"
    
    return build_url
