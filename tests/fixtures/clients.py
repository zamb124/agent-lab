"""
HTTP клиенты для тестирования сервисов платформы.

Каждый клиент:
- Использует AsyncClient для async HTTP запросов
- Поддерживает как ASGI transport (для быстрых unit тестов), так и реальный HTTP (для E2E тестов)
- Автоматически настраивает base_url для соответствующего сервиса
- Поддерживает аутентификацию через headers

Использование:

    # Unit тесты (ASGI transport)
    async def test_api(flows_client):
        response = await flows_client.get("/flows/api/v1/flows")
        assert response.status_code == 200

    # E2E тесты (реальный HTTP)
    async def test_e2e(flows_client_http):
        response = await flows_client_http.get("/flows/api/v1/flows")
        assert response.status_code == 200
"""

from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# rag_worker импортируется из tests.conftest через pytest
# Он объявлен там как session-scoped фикстура


@pytest.fixture(autouse=True)
def patch_service_clients_asgi(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Универсальный патч для ServiceClient, направляющий запросы между сервисами
    через ASGITransport, если соответствующее приложение доступно.
    """
    if request.node.get_closest_marker("no_service_client_patch"):
        return

    from httpx import ASGITransport, AsyncClient

    from core.clients.service_client import ServiceClient

    _apps_cache = {}

    def get_service_app(service: str) -> Any:
        if service in _apps_cache:
            return _apps_cache[service]

        try:
            if service == "flows":
                from apps.flows.main import app
                _apps_cache[service] = app
            elif service == "rag":
                from apps.rag.main import app
                _apps_cache[service] = app
            elif service == "crm":
                from apps.crm.main import create_app
                _apps_cache[service] = create_app()
            elif service == "frontend":
                from apps.frontend.main import app
                _apps_cache[service] = app
            elif service == "sync":
                from apps.sync.main import app
                _apps_cache[service] = app
            elif service == "office":
                from apps.office.main import app
                _apps_cache[service] = app
            elif service == "voice":
                # Как voice_app: batch /transcribe идёт в STTClient, без mock-бэкенда
                # упрётся в реальный HTTP (litserve/cloud) и падает ConnectError.
                monkeypatch.setenv("VOICE__STT__PROVIDER", "mock")
                monkeypatch.setenv("VOICE__TTS__PROVIDER", "mock")
                monkeypatch.setenv("VOICE__VAD__PROVIDER", "mock")
                import core.config.base as config_base
                from apps.voice.config import reset_voice_settings
                from apps.voice.container import reset_voice_container
                from core.clients.voice_resolver import reset_voice_resolver_for_tests

                monkeypatch.setattr(config_base, "_settings_instance", None)
                reset_voice_resolver_for_tests()
                reset_voice_settings()
                reset_voice_container()
                import importlib

                import apps.voice.main as voice_main_mod

                importlib.reload(voice_main_mod)
                _apps_cache[service] = voice_main_mod.app
            else:
                return None
        except ImportError:
            return None
        return _apps_cache.get(service)

    original_request = ServiceClient.request

    async def mocked_request(self: ServiceClient, service: str, method: str, path: str, **kwargs: Any) -> Any:
        app = get_service_app(service)
        if not app:
            # Если приложение не найдено (или это внешний сервис), используем оригинальный HTTP-запрос
            return await original_request(self, service, method, path, **kwargs)

        # Собираем заголовки из контекста (как в оригинальном ServiceClient)
        include_content_type = "files" not in kwargs
        headers = self._build_headers(include_content_type=include_content_type)
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))

        timeout = kwargs.pop("timeout", 30.0)
        req_kwargs = {k: v for k, v in kwargs.items() if k != "headers"}

        transport = ASGITransport(app=app)
        # В тестах все роутеры примонтированы с префиксом /{service}/api/v1.
        # ServiceClient обычно вызывается с путем /api/v1/..., поэтому добавляем префикс если его нет.
        request_path = path
        if not path.startswith(f"/{service}/"):
            request_path = f"/{service}{path}"

        async with AsyncClient(transport=transport, base_url="http://testserver", timeout=timeout) as client:
            response = await client.request(method, request_path, headers=headers, **req_kwargs)
            # Мы не используем response.raise_for_status() здесь, так как оригинальный request
            # обрабатывает ошибки самостоятельно (ServiceClientError)
            if response.is_error:
                from core.clients.service_client import ServiceClientError
                raise ServiceClientError(
                    f"HTTP {response.status_code} при запросе к {service} (ASGI): {response.text}"
                )

            if response.content:
                return response.json()
            return None

    monkeypatch.setattr(ServiceClient, "request", mocked_request)


# ==============================================================================
# ASGI Clients (для unit тестов)
# ==============================================================================

@pytest_asyncio.fixture
async def flows_client():
    """
    HTTP клиент для Agents API (ASGI transport).

    Использует ASGI transport для быстрых unit тестов без запуска реального сервера.
    Таблицы создаются через миграции в setup_database_before_tests.
    """
    from apps.flows.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest_asyncio.fixture
async def rag_app():
    """
    FastAPI приложение RAG сервиса.

    Используется как зависимость для rag_client (ASGI transport).
    Таблицы создаются через миграции в setup_database_before_tests.
    """
    from apps.rag.main import app

    yield app


@pytest_asyncio.fixture
async def rag_client(rag_app, rag_worker):
    """
    HTTP клиент для RAG API (ASGI transport).

    Использует ASGI transport для быстрых unit тестов без запуска реального сервера.

    Зависимости:
    - rag_app: FastAPI приложение
    - rag_worker: для обработки документов
    """
    transport = ASGITransport(app=rag_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest_asyncio.fixture(scope="session")
async def crm_companies_initialized(app, auth_token_system, auth_token_company2):
    """
    Инициализирует компании system и company2 один раз за сессию.

    initialize_company идемпотентна — при повторном вызове проверяет существование
    и пропускает уже созданные типы. Session scope убирает ~240 лишних вызовов
    initialize_company при 60 CRM тестах * 4 xdist workers.

    Зависит от auth_token_system и auth_token_company2 чтобы гарантировать, что
    записи company:system и company:company2 уже существуют в storage до инициализации.

    Контекст устанавливается вручную: test_context — function-scoped,
    а эта фикстура — session-scoped, поэтому test_context ещё не существует.
    """
    from apps.crm.container import get_crm_container
    from core.context import clear_context, set_context
    from core.models.context_models import Context
    from core.models.identity_models import User
    from tests.fixtures.ai_provider_defaults import make_test_company

    set_context(Context(
        user=User(user_id="test_user", name="Test User"),
        active_company=make_test_company(company_id="system", name="System"),
        session_id="test_session",
        channel="test",
        metadata={"user_id": "test_user", "email": "test@example.com", "grps": []},
    ))

    container = get_crm_container()
    await container.company_init_service.initialize_company("system")

    set_context(Context(
        user=User(user_id="test_user", name="Test User"),
        active_company=make_test_company(company_id="company2", name="Company2"),
        session_id="test_session",
        channel="test",
        metadata={"user_id": "test_user", "email": "test@example.com", "grps": []},
    ))

    await container.company_init_service.initialize_company("company2")

    clear_context()


@pytest_asyncio.fixture
async def crm_client(
    crm_companies_initialized,
    rag_app,
    rag_service,
    flows_service,
    rag_worker,
    unique_id,
    auth_headers_system,
    auth_headers_company2,
):
    """
    HTTP клиент для CRM API (ASGI transport).

    Использует ASGI transport для быстрых unit тестов без запуска реального сервера.
    Таблицы создаются через миграции в setup_database_before_tests.

    Зависимости:
    - crm_companies_initialized: session-scoped, system/company2 компании
    - rag_app: для инициализации RAG таблиц
    - rag_service: реальный HTTP сервер для inter-service communication (attachments)
    - rag_worker: для обработки загруженных документов
    """
    from apps.crm.main import create_app
    from tests.fixtures.crm_test_setup import ensure_crm_per_test_namespace_and_types

    crm_app = create_app()

    transport = ASGITransport(app=crm_app)
    async with AsyncClient(transport=transport, base_url="http://testserver", follow_redirects=True) as client:
        await ensure_crm_per_test_namespace_and_types(
            client,
            unique_id,
            auth_headers_system,
            auth_headers_company2,
        )
        yield client


@pytest_asyncio.fixture
async def frontend_client():
    """
    HTTP клиент для Frontend API (ASGI transport).

    Использует ASGI transport для быстрых unit тестов без запуска реального сервера.
    """
    from apps.frontend.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest_asyncio.fixture
async def sync_app():
    """FastAPI приложение Sync (ASGI)."""
    from apps.sync.main import app

    yield app


@pytest_asyncio.fixture
async def office_app():
    """FastAPI приложение office (Documents / OnlyOffice BFF + UI, ASGI)."""
    from apps.office.main import app

    yield app


@pytest_asyncio.fixture
async def office_client(office_app):
    """HTTP-клиент для BFF office (ASGI). Миграции platform_office — в setup_database_before_tests."""
    transport = ASGITransport(app=office_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture
def voice_app(monkeypatch: pytest.MonkeyPatch):
    """
    FastAPI приложение voice с mock-провайдерами STT/TTS/VAD.

    Используется как sync fixture — доступна и для sync (TestClient / WS),
    и для async (voice_client) тестов.

    Устанавливает provider = 'mock' для всех провайдеров через monkeypatch env,
    сбрасывает синглтон ``core.config.get_settings``, кэш ``voice_resolver``,
    затем локальные синглтоны ``VoiceServiceSettings`` и контейнера voice.
    Провайдеры — реальные классы (MockSTTProvider / MockTTSProvider / MockVADProvider),
    не unittest.mock. Внешние ML-модели и cloud.ru API не используются.

    Имена переменных окружения следуют вложенности `BaseSettings` с
    `env_nested_delimiter="__"`: например `VOICE__STT__PROVIDER`,
    `VOICE__TTS__PROVIDER`, `VOICE__VAD__PROVIDER` задают deployment-default
    в `settings.voice.{stt,tts,vad}.provider`.
    """
    monkeypatch.setenv("VOICE__STT__PROVIDER", "mock")
    monkeypatch.setenv("VOICE__TTS__PROVIDER", "mock")
    monkeypatch.setenv("VOICE__VAD__PROVIDER", "mock")

    import core.config.base as config_base
    from apps.voice.config import reset_voice_settings
    from apps.voice.container import reset_voice_container
    from core.clients.voice_resolver import reset_voice_resolver_for_tests

    monkeypatch.setattr(config_base, "_settings_instance", None)
    reset_voice_resolver_for_tests()
    reset_voice_settings()
    reset_voice_container()

    from apps.voice.main import app

    yield app

    reset_voice_resolver_for_tests()
    reset_voice_container()
    reset_voice_settings()


@pytest_asyncio.fixture
async def voice_client(voice_app):
    """HTTP-клиент для voice API (ASGI)."""
    transport = ASGITransport(app=voice_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest_asyncio.fixture
async def sync_client(sync_app, sync_worker):
    """
    HTTP клиент для Sync API (ASGI, lifespan включён).

    Зависит от sync_worker: эндпоинты с handle_command.kiq() ждут очередь sync.
    """
    transport = ASGITransport(app=sync_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


# ==============================================================================
# HTTP Clients (для E2E тестов с реальными серверами)
# ==============================================================================

@pytest_asyncio.fixture
async def flows_client_http(flows_service):
    """
    HTTP клиент для Agents API (реальный HTTP).

    Использует реальный HTTP сервер на порту 9001.
    Для E2E тестов всей платформы.
    """
    async with AsyncClient(base_url="http://localhost:9001") as client:
        yield client


@pytest_asyncio.fixture
async def rag_client_http(rag_service):
    """
    HTTP клиент для RAG API (реальный HTTP).

    Использует реальный HTTP сервер на порту 8004.
    Для E2E тестов всей платформы.
    """
    async with AsyncClient(base_url="http://localhost:8004") as client:
        yield client


@pytest_asyncio.fixture
async def crm_client_http(crm_service, crm_companies_initialized, rag_service, flows_service):
    """
    HTTP клиент для CRM API (реальный HTTP).

    Использует реальный HTTP сервер на порту 9003.
    Для E2E тестов всей платформы.
    Таблицы создаются через миграции в setup_database_before_tests.

    Зависимости:
    - crm_companies_initialized: session-scoped, system/company2 компании
    - rag_service: для attachments через inter-service communication
    - flows_service: HTTP flows на 9001 для TaskIQ/worker и CRM→flows вызовов
    """
    async with AsyncClient(base_url="http://localhost:9003") as client:
        yield client


@pytest_asyncio.fixture
async def frontend_client_http(frontend_service):
    """
    HTTP клиент для Frontend API (реальный HTTP).

    Использует реальный HTTP сервер на порту 8001.
    Для E2E тестов всей платформы.
    """
    async with AsyncClient(base_url="http://localhost:8001") as client:
        yield client


@pytest_asyncio.fixture
async def office_client_http(office_service):
    """
    HTTP клиент для Documents/Office API (реальный HTTP).

    Использует реальный HTTP сервер на порту 9008.
    """
    async with AsyncClient(base_url="http://localhost:9008") as client:
        yield client


# ==============================================================================
# Convenience фикстуры
# ==============================================================================

@pytest_asyncio.fixture
async def all_clients_http(
    flows_client_http,
    rag_client_http,
    crm_client_http,
    frontend_client_http
):
    """
    Все HTTP клиенты для E2E тестов.

    Возвращает dict с клиентами для всех сервисов.
    """
    return {
        "flows": flows_client_http,
        "rag": rag_client_http,
        "crm": crm_client_http,
        "frontend": frontend_client_http,
    }
