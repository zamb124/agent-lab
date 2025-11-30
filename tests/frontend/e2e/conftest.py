"""
Playwright-специфичные фикстуры для e2e тестов.

E2E тесты запускают сервер в отдельном процессе и не используют
async фикстуры из основного conftest.py чтобы избежать конфликта event loop.

Запуск:
    uv run pytest tests/frontend/e2e/ -v --headed  # с браузером
    uv run pytest tests/frontend/e2e/ -v           # headless режим
"""

import os
import pytest
import multiprocessing
import time
import socket


# Отключаем asyncio mode для e2e тестов чтобы избежать конфликта с Playwright
def pytest_configure(config):
    config.addinivalue_line("markers", "playwright: Playwright e2e tests")


# Переопределяем async фикстуры из основного conftest как sync
# чтобы pytest-asyncio их не трогал
@pytest.fixture(scope="session")
def event_loop():
    """Переопределяем event_loop чтобы не конфликтовать с Playwright"""
    return None


@pytest.fixture(scope="session")
def migrated_db():
    """Заглушка - e2e тесты используют свой сервер в отдельном процессе"""
    return None


@pytest.fixture(scope="session")
def frontend_app():
    """Заглушка - e2e тесты используют live_server"""
    return None


@pytest.fixture
def frontend_client():
    """Заглушка - для авторизованных тестов используем authenticated_page"""
    return None


@pytest.fixture(scope="session")
def setup_mock_llm_configs():
    """Переопределяем autouse фикстуру"""
    return None


@pytest.fixture(scope="function")
def cleanup_after_test():
    """Переопределяем autouse фикстуру"""
    yield


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
def live_server():
    """
    Запускает frontend сервер в отдельном процессе.
    Доступен на протяжении всей сессии тестов.
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
def browser_context_args():
    """Настройки контекста браузера Playwright"""
    return {
        "viewport": {"width": 1920, "height": 1080},
        "locale": "ru-RU",
        "timezone_id": "Europe/Moscow",
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


@pytest.fixture
def authenticated_page(page, live_server):
    """
    Страница Playwright с авторизацией.
    Создает тестовые данные синхронно через API сервера.
    """
    import uuid
    import httpx
    
    unique_suffix = uuid.uuid4().hex[:8]
    subdomain = f"pw_{unique_suffix}"
    
    # Создаем JWT токен напрямую
    from core.utils.tokens import get_token_service
    
    token_service = get_token_service()
    auth_token = token_service.create_token(
        user_id=f"pw_user_{unique_suffix}",
        company_id=f"pw_company_{unique_suffix}",
        session_id=f"pw_session_{unique_suffix}"
    )
    
    page.context.add_cookies([
        {
            "name": "auth_token",
            "value": auth_token,
            "domain": "127.0.0.1",
            "path": "/"
        }
    ])
    
    page.subdomain = subdomain
    page.auth_token = auth_token
    page.live_server = live_server
    
    return page
