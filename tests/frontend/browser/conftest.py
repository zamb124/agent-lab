"""
Async Playwright фикстуры для e2e тестов.

E2E тесты используют async Playwright API для совместимости с pytest-asyncio.

Запуск:
    uv run pytest tests/frontend/browser/ -v --headed  # с браузером
    uv run pytest tests/frontend/browser/ -v           # headless режим
"""

import os
import pytest
import pytest_asyncio
import multiprocessing
import time
import socket
from pathlib import Path
from playwright.async_api import Page


# === Хук для сохранения статуса теста ===

@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Сохраняем результат теста для использования в фикстурах"""
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


FRONTEND_PORT = int(os.getenv("FRONTEND_PORT", "8002"))

# Фиксированные данные для E2E тестов - пользователь создается один раз через скрипт
E2E_USER_ID = "e2e_browser_test_user"
E2E_COMPANY_ID = "e2e_browser_test_company"
E2E_SESSION_ID = "e2e_browser_test_session"
E2E_SUBDOMAIN = "e2ebrowser"


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


def run_taskiq_worker_subprocess():
    """Запуск TaskIQ воркера через subprocess"""
    import subprocess
    import sys
    
    # Переменные окружения для локального запуска
    env = os.environ.copy()
    env["DATABASE__SHARED_URL"] = "postgresql+asyncpg://agent_user:agent_password@localhost:5432/shared_db"
    env["DATABASE__URL"] = "postgresql+asyncpg://agent_user:agent_password@localhost:5432/agents_db"
    
    # Запускаем воркер через taskiq CLI
    process = subprocess.Popen(
        [sys.executable, "-m", "taskiq", "worker", "core.tasks.worker:broker", "--workers", "1"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(Path(__file__).parent.parent.parent.parent),
        env=env
    )
    return process


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
def e2e_test_data(migrated_db):
    """
    Возвращает данные тестового пользователя для E2E тестов.
    Пользователь создается в migrated_db фикстуре (tests/conftest.py).
    """
    return {
        "user_id": E2E_USER_ID,
        "company_id": E2E_COMPANY_ID,
        "session_id": E2E_SESSION_ID,
        "subdomain": E2E_SUBDOMAIN,
    }


@pytest.fixture(scope="session")
def taskiq_worker_process(migrated_db):
    """
    Запускает TaskIQ воркер в отдельном subprocess для обработки задач.
    Воркер обрабатывает сообщения от чата и отправляет ответы.
    """
    worker_process = run_taskiq_worker_subprocess()
    
    # Даем воркеру время на инициализацию
    time.sleep(3)
    
    if worker_process.poll() is not None:
        stdout, stderr = worker_process.communicate()
        raise RuntimeError(f"TaskIQ воркер не запустился: {stderr.decode()}")
    
    print(f"TaskIQ воркер запущен (PID: {worker_process.pid})")
    
    yield worker_process
    
    worker_process.terminate()
    try:
        worker_process.wait(timeout=5)
    except:
        worker_process.kill()
    print("TaskIQ воркер остановлен")


@pytest.fixture(scope="session")
def live_server(migrated_db, e2e_test_data, taskiq_worker_process):
    """
    Запускает frontend сервер в отдельном процессе.
    Зависит от taskiq_worker_process чтобы воркер был запущен.
    Пользователь уже создан в migrated_db.
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
def e2e_auth_token(e2e_test_data):
    """Создает JWT токен для e2e тестов"""
    from core.utils.tokens import get_token_service
    
    token_service = get_token_service()
    
    return token_service.create_token(
        user_id=e2e_test_data["user_id"],
        company_id=e2e_test_data["company_id"],
        session_id=e2e_test_data["session_id"]
    )


@pytest.fixture(scope="session")
def browser_context_args(e2e_auth_token, e2e_test_data):
    """Настройки контекста браузера Playwright с авторизацией"""
    return {
        "viewport": {"width": 1920, "height": 1080},
        "locale": "ru-RU",
        "timezone_id": "Europe/Moscow",
        # Заголовок X-Company-Id для переопределения компании без поддомена
        "extra_http_headers": {
            "X-Company-Id": e2e_test_data["company_id"]
        },
        "storage_state": {
            "cookies": [
                {
                    "name": "auth_token",
                    "value": e2e_auth_token,
                    "domain": "127.0.0.1",
                    "path": "/"
                },
                {
                    "name": "session_id",
                    "value": e2e_test_data["session_id"],
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


@pytest_asyncio.fixture(scope="session")
async def context(browser, browser_context_args):
    """Создает browser context с авторизацией"""
    ctx = await browser.new_context(**browser_context_args)
    yield ctx
    await ctx.close()


@pytest_asyncio.fixture(scope="function") 
async def page(context, request):
    """Создает новую страницу с авторизацией и логированием консоли"""
    pg = await context.new_page()
    
    # Список для сбора логов консоли
    console_logs = []
    js_errors = []
    
    def handle_console(msg):
        log_entry = f"[{msg.type}] {msg.text}"
        console_logs.append(log_entry)
        # Выводим важные логи сразу
        if msg.type in ("error", "warning"):
            print(f"🌐 Browser {msg.type}: {msg.text}")
    
    def handle_error(error):
        error_entry = f"JS Error: {error}"
        js_errors.append(error_entry)
        print(f"🔴 Browser JS Error: {error}")
    
    pg.on("console", handle_console)
    pg.on("pageerror", handle_error)
    
    yield pg
    
    # После теста выводим все логи если были ошибки
    if js_errors:
        print("\n" + "="*60)
        print("🔴 JavaScript Errors during test:")
        for error in js_errors:
            print(f"  {error}")
        print("="*60)
    
    # Выводим все console.log если тест упал
    rep_call = getattr(request.node, "rep_call", None)
    if rep_call and rep_call.failed:
        print("\n" + "="*60)
        print("📋 All browser console logs:")
        for log in console_logs[-50:]:  # Последние 50 логов
            print(f"  {log}")
        print("="*60)
    
    # Если были WebSocket сообщения, выводим их
    ws_logs = [log for log in console_logs if "WebSocket" in log or "ws" in log.lower()]
    if ws_logs:
        print("\n📡 WebSocket related logs:")
        for log in ws_logs[-20:]:
            print(f"  {log}")
    
    await pg.close()


@pytest.fixture(scope="session")
def server_url(live_server):
    """Базовый URL frontend сервиса"""
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


# === Фикстуры для сценарийных тестов ===

SCREENSHOTS_DIR = Path(__file__).parent.parent.parent.parent / "artifacts" / "screenshots"


@pytest.fixture(scope="function")
def scenario_screenshots(request):
    """
    Менеджер скриншотов для сценарийных тестов.
    Перезаписывает скриншоты при каждом запуске.
    """
    test_name = request.node.name.split("[")[0]
    test_dir = SCREENSHOTS_DIR / test_name
    
    if test_dir.exists():
        import shutil
        shutil.rmtree(test_dir)
    test_dir.mkdir(parents=True, exist_ok=True)
    
    class ScreenshotManager:
        def __init__(self, directory: Path):
            self.directory = directory
            self.step_count = 0
        
        async def capture(self, name: str, page: Page) -> Path:
            """Делает скриншот всей страницы"""
            self.step_count += 1
            step_name = f"{self.step_count:02d}_{name}"
            screenshot_path = self.directory / f"{step_name}.png"
            await page.screenshot(path=str(screenshot_path), full_page=True)
            return screenshot_path
        
        def get_path(self) -> Path:
            return self.directory
    
    return ScreenshotManager(test_dir)
