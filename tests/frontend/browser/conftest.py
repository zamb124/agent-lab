"""
Async Playwright фикстуры для e2e тестов.

E2E тесты используют async Playwright API для совместимости с pytest-asyncio.

Запуск:
    uv run pytest tests/frontend/browser/ -v --headed  # с браузером
    uv run pytest tests/frontend/browser/ -v           # headless режим

Все серверные фикстуры (agents_server, frontend_server, taskiq_worker) 
наследуются из tests/conftest.py
"""

import os
from pathlib import Path

import pytest
import pytest_asyncio
from playwright.async_api import Page


# === Группировка для pytest-xdist ===
# Все browser тесты запускаются в одном worker'е чтобы разделять сервер

def pytest_collection_modifyitems(items):
    """
    Группирует все browser тесты в один xdist worker.
    Это нужно потому что frontend_server_process имеет session scope
    и не может быть разделен между worker'ами.
    """
    for item in items:
        # Добавляем маркер xdist_group для всех тестов в этой директории
        if "/browser/" in str(item.fspath):
            item.add_marker(pytest.mark.xdist_group("browser"))


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


# === Алиасы для серверных фикстур из tests/conftest.py ===

@pytest.fixture(scope="session")
def agents_server(agents_service):
    """
    Алиас для agents_service из tests/conftest.py.
    Для совместимости с существующими тестами.
    """
    return agents_service


@pytest.fixture(scope="session")
def live_server(migrated_db, e2e_test_data, taskiq_worker_process, agents_service, frontend_server_process):
    """
    Frontend сервер для E2E тестов.
    Зависит от agents_service и taskiq_worker_process.
    """
    return frontend_server_process


@pytest.fixture(scope="session")
def e2e_auth_token(e2e_test_data):
    """Создает JWT токен для e2e тестов"""
    from core.utils.tokens import get_token_service
    
    token_service = get_token_service()
    token = token_service.create_token(
        user_id=e2e_test_data["user_id"],
        company_id=e2e_test_data["company_id"],
        expires_in=86400  # 24 часа в секундах
    )
    return token


@pytest.fixture(scope="session")
def e2e_base_url(live_server, e2e_test_data):
    """
    Базовый URL для E2E тестов с поддоменом компании.
    Формат: http://{subdomain}.localhost:{port}
    """
    subdomain = e2e_test_data["subdomain"]
    return f"http://{subdomain}.localhost:{live_server['port']}"


@pytest.fixture(scope="session")
def server_url(live_server):
    """
    URL сервера для публичных страниц (без поддомена).
    """
    return f"http://localhost:{live_server['port']}"


# === Playwright фикстуры ===

@pytest_asyncio.fixture(scope="session")
async def browser(playwright):
    """Запускает браузер один раз на всю сессию"""
    headless = os.getenv("HEADED", "false").lower() != "true"
    browser = await playwright.chromium.launch(headless=headless)
    yield browser
    await browser.close()


@pytest_asyncio.fixture(scope="function")
async def context(browser, e2e_auth_token, e2e_base_url, e2e_test_data):
    """Создает новый контекст браузера для каждого теста с авторизацией"""
    subdomain = e2e_test_data["subdomain"]
    
    context = await browser.new_context(
        base_url=e2e_base_url,
        viewport={"width": 1280, "height": 720},
    )
    
    # Устанавливаем auth cookie для конкретного субдомена
    await context.add_cookies([{
        "name": "auth_token",
        "value": e2e_auth_token,
        "domain": f"{subdomain}.localhost",  
        "path": "/",
    }])
    
    yield context
    await context.close()


@pytest_asyncio.fixture(scope="function")
async def page(context) -> Page:
    """Создает новую страницу в контексте"""
    page = await context.new_page()
    yield page
    await page.close()


@pytest_asyncio.fixture(scope="function")
async def authenticated_page(page, e2e_base_url) -> Page:
    """
    Страница с проверкой авторизации.
    Переходит на главную и проверяет что пользователь авторизован.
    """
    await page.goto(e2e_base_url)
    
    # Ждем загрузки страницы
    await page.wait_for_load_state("networkidle")
    
    # Проверяем что не редиректнуло на логин
    if "/auth" in page.url:
        raise AssertionError("Пользователь не авторизован - редирект на /auth")
    
    yield page


# === Утилиты для тестов ===

class ScenarioScreenshots:
    """Хелпер для сохранения скриншотов в сценарных тестах"""
    
    def __init__(self, test_name: str, screenshots_dir: Path):
        self.test_name = test_name
        self.screenshots_dir = screenshots_dir
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.counter = 0
    
    async def capture(self, name: str, page):
        """Сохраняет скриншот с именем"""
        self.counter += 1
        filename = f"{self.test_name}_{self.counter:02d}_{name}.png"
        filepath = self.screenshots_dir / filename
        try:
            await page.screenshot(path=str(filepath))
        except Exception:
            pass


@pytest_asyncio.fixture
async def scenario_screenshots(request):
    """Фикстура для сохранения скриншотов в сценарных тестах"""
    test_name = request.node.name.replace("/", "_").replace("::", "_")
    screenshots_dir = Path(__file__).parent / "screenshots" / "scenarios"
    return ScenarioScreenshots(test_name, screenshots_dir)


# === Генератор документации из сценариев ===

# Путь к директории документации
DOCS_DIR = Path(__file__).parent.parent.parent.parent / "docs" / "user_docs" / "user_scenarios"


class ScenarioDocGenerator:
    """
    Генератор пользовательской документации из browser тестов.
    
    Функционал:
    - Автоматическое создание папок для сценариев
    - Визуализация кликов на скриншотах (красная рамка)
    - Сбор markdown описаний шагов
    - Генерация итогового index.md файла
    """
    
    def __init__(self, scenario_name: str, title: str):
        """
        Args:
            scenario_name: Имя папки сценария (английское, snake_case)
            title: Заголовок сценария на русском
        """
        self.scenario_name = scenario_name
        self.title = title
        self.output_dir = DOCS_DIR / scenario_name
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.steps: list[dict] = []
        self.counter = 0
    
    async def step(self, page: Page, title: str, description: str, selector: str = None):
        """
        Записывает шаг сценария.
        
        Args:
            page: Playwright Page
            title: Короткое название шага (например, "Открытие раздела")
            description: Подробное описание шага на русском
            selector: CSS селектор элемента для подсветки (опционально)
        """
        self.counter += 1
        screenshot_name = f"{self.counter:02d}.png"
        screenshot_path = self.output_dir / screenshot_name
        
        if selector:
            await self._highlight_element(page, selector)
        
        await page.screenshot(path=str(screenshot_path))
        
        if selector:
            await self._remove_highlight(page, selector)
        
        self.steps.append({
            "number": self.counter,
            "title": title,
            "description": description,
            "screenshot": screenshot_name,
        })
    
    async def click(self, page: Page, selector: str, title: str, description: str):
        """
        Подсвечивает элемент, делает скриншот, затем кликает.
        
        Args:
            page: Playwright Page
            selector: CSS селектор элемента для клика
            title: Короткое название шага
            description: Подробное описание действия на русском
        """
        await self.step(page, title, description, selector)
        await page.click(selector)
    
    async def fill(self, page: Page, selector: str, value: str, title: str, description: str):
        """
        Подсвечивает поле ввода, делает скриншот, затем заполняет.
        
        Args:
            page: Playwright Page
            selector: CSS селектор поля ввода
            value: Значение для ввода
            title: Короткое название шага
            description: Подробное описание действия на русском
        """
        await self.step(page, title, description, selector)
        await page.fill(selector, value)
    
    async def _highlight_element(self, page: Page, selector: str):
        """Добавляет красную рамку на элемент"""
        await page.evaluate(f"""
            (selector) => {{
                const el = document.querySelector(selector);
                if (el) {{
                    el.dataset.originalOutline = el.style.outline;
                    el.dataset.originalBoxShadow = el.style.boxShadow;
                    el.style.outline = '3px solid #ff0000';
                    el.style.boxShadow = '0 0 15px 5px rgba(255, 0, 0, 0.5)';
                }}
            }}
        """, selector)
        await page.wait_for_timeout(100)
    
    async def _remove_highlight(self, page: Page, selector: str):
        """Убирает подсветку с элемента"""
        await page.evaluate(f"""
            (selector) => {{
                const el = document.querySelector(selector);
                if (el) {{
                    el.style.outline = el.dataset.originalOutline || '';
                    el.style.boxShadow = el.dataset.originalBoxShadow || '';
                    delete el.dataset.originalOutline;
                    delete el.dataset.originalBoxShadow;
                }}
            }}
        """, selector)
    
    def generate_markdown(self) -> str:
        """Генерирует markdown документацию"""
        lines = [
            f"# {self.title}",
            "",
        ]
        
        for step in self.steps:
            lines.extend([
                f"## {step['number']}. {step['title']}",
                "",
                step['description'],
                "",
                f"![{step['title']}]({step['screenshot']})",
                "",
            ])
        
        return "\n".join(lines)
    
    def save(self):
        """Сохраняет index.md файл с документацией"""
        markdown = self.generate_markdown()
        index_path = self.output_dir / "index.md"
        index_path.write_text(markdown, encoding="utf-8")
        return index_path


@pytest_asyncio.fixture
async def doc_generator():
    """
    Фабрика для создания генератора документации.
    
    Использование:
        async def test_my_scenario(doc_generator):
            doc = doc_generator("my_scenario", "Мой сценарий")
            await doc.step(page, "Открываем страницу")
            await doc.click(page, "#button", "Нажимаем кнопку")
            doc.save()
    """
    generators = []
    
    def create(scenario_name: str, title: str) -> ScenarioDocGenerator:
        gen = ScenarioDocGenerator(scenario_name, title)
        generators.append(gen)
        return gen
    
    yield create
    
    for gen in generators:
        gen.save()


@pytest_asyncio.fixture
async def screenshot_on_failure(request, page):
    """Делает скриншот при падении теста"""
    yield
    
    # Проверяем результат теста
    if hasattr(request.node, "rep_call") and request.node.rep_call.failed:
        # Создаем директорию для скриншотов
        screenshot_dir = Path(__file__).parent / "screenshots"
        screenshot_dir.mkdir(exist_ok=True)
        
        # Сохраняем скриншот
        test_name = request.node.name.replace("/", "_").replace("::", "_")
        screenshot_path = screenshot_dir / f"{test_name}.png"
        await page.screenshot(path=str(screenshot_path))
        print(f"Screenshot saved: {screenshot_path}")


@pytest_asyncio.fixture(scope="function")
async def public_page(browser, live_server) -> Page:
    """
    Страница БЕЗ авторизации для тестирования публичных страниц.
    Не устанавливает auth cookie.
    """
    context = await browser.new_context(
        base_url=f"http://localhost:{live_server['port']}",
        viewport={"width": 1280, "height": 720},
    )
    
    page = await context.new_page()
    yield page
    
    await page.close()
    await context.close()
