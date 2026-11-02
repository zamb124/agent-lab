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
from httpx2 import ASGITransport, AsyncClient

from tests.fixtures.service_processes import ServiceProcesses, import_service_app

# ASGI-клиенты с Host: linnex.io получают 307 на apex домен; base_url должен
# совпадать с Host, иначе httpx2 сбрасывает Authorization при cross-host redirect.
_PLATFORM_ASGI_BASE_URL = "http://linnex.io"
_PLATFORM_ASGI_HOST_HEADERS = {"Host": "linnex.io"}
# Real HTTP e2e: очередь granian под -n10. httpx2 default 5s → ReadTimeout на enable/enqueue.
# Длинный граф всё равно SendMessage returnImmediately + GetTask poll (a2a.mdc § Клиенты).
_E2E_HTTP_TIMEOUT_SECONDS = 60.0

# rag_worker импортируется из tests.conftest через pytest
# Он объявлен там как session-scoped фикстура


@pytest.fixture(autouse=True)
def patch_service_clients_asgi(
    request: pytest.FixtureRequest,
    service_processes: ServiceProcesses,
) -> None:
    """
    Универсальный патч для ServiceClient, направляющий запросы между сервисами
    через ASGITransport в приложение того же процесса с запущенным lifespan.
    """
    if request.node.get_closest_marker("no_test_doubles") or request.node.get_closest_marker(
        "no_service_client_patch"
    ):
        return

    monkeypatch = request.getfixturevalue("monkeypatch")
    if not isinstance(monkeypatch, pytest.MonkeyPatch):
        raise TypeError("monkeypatch fixture must be pytest.MonkeyPatch")

    from httpx2 import ASGITransport, AsyncClient

    from core.clients.service_client import ServiceClient
    from core.config import get_settings, set_settings
    from core.config.base import BaseSettings
    from core.internal_context_headers import (
        HEADER_COMPANY_ID,
        HEADER_SIGNATURE,
        HEADER_USER_ID,
        build_internal_context_headers,
    )

    _voice_app: dict[str, Any] = {}

    def get_voice_app() -> Any:
        # Как voice_app: batch /transcribe идёт в STTClient, без mock-бэкенда
        # упрётся в реальный HTTP (litserve/cloud) и падает ConnectError.
        if "voice" in _voice_app:
            return _voice_app["voice"]
        monkeypatch.setenv("VOICE__STT__PROVIDER", "mock")
        monkeypatch.setenv("VOICE__TTS__PROVIDER", "mock")
        monkeypatch.setenv("VOICE__VAD__PROVIDER", "mock")
        import importlib

        import core.config.base as config_base
        from apps.voice.config import reset_voice_settings
        from core.ai.runtime import reset_voice_runtime_for_tests

        monkeypatch.setattr(config_base, "_settings_instance", None)
        reset_voice_runtime_for_tests()
        reset_voice_settings()
        import apps.voice.main as voice_main_mod

        # Voice reload намеренно кладёт mock STT/TTS в глобальный settings.
        importlib.reload(voice_main_mod)
        _voice_app["voice"] = voice_main_mod.app
        return voice_main_mod.app

    async def get_service_app(service: str) -> Any:
        if service == "voice":
            return get_voice_app()
        if import_service_app(service) is None:
            return None
        return await service_processes.app(service)

    original_request = ServiceClient.request

    async def mocked_request(self: ServiceClient, service: str, method: str, path: str, **kwargs: Any) -> Any:
        app = await get_service_app(service)
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
        # Роутеры create_service_app: /{url_route_segment}/api/v1.
        # Публичный сегмент иногда ≠ ключ ServiceClient (office→documents, …).
        # ServiceClient часто зовёт /api/v1/... — дописываем префикс; полный /documents/... не трогаем.
        _asgi_path_prefix: dict[str, str] = {
            "office": "documents",
            "capability_gateway": "capability-gateway",
            "provider_litserve": "litserve",
        }
        service_prefix = _asgi_path_prefix.get(service, service)
        request_path = path
        if not path.startswith(f"/{service_prefix}/"):
            request_path = f"/{service_prefix}{path}"

        preserved: BaseSettings = get_settings()
        service_settings = getattr(app.state, "settings", None)
        if isinstance(service_settings, BaseSettings):
            set_settings(service_settings)
            # Headers were signed under caller settings; target app verifies with
            # its own settings.jwt_secret_key. Re-sign after the switch.
            context_company_id = headers.get(HEADER_COMPANY_ID)
            context_user_id = headers.get(HEADER_USER_ID)
            if (
                HEADER_SIGNATURE in headers
                and isinstance(context_company_id, str)
                and context_company_id.strip()
                and isinstance(context_user_id, str)
                and context_user_id.strip()
            ):
                headers.update(
                    build_internal_context_headers(
                        company_id=context_company_id,
                        user_id=context_user_id,
                    )
                )
        try:
            async with AsyncClient(
                transport=transport,
                base_url=_PLATFORM_ASGI_BASE_URL,
                timeout=timeout,
                headers=_PLATFORM_ASGI_HOST_HEADERS,
            ) as client:
                response = await client.request(method, request_path, headers=headers, **req_kwargs)
            # Мы не используем response.raise_for_status() здесь, так как оригинальный request
            # обрабатывает ошибки самостоятельно (ServiceClientError)
            if response.is_error:
                from core.clients.service_client import ServiceClientError

                raise ServiceClientError(
                    f"HTTP {response.status_code} при запросе к {service} (ASGI): {response.text}",
                    status_code=response.status_code,
                    response_text=response.text,
                )

            if response.content:
                return response.json()
            return None
        finally:
            set_settings(preserved)

    monkeypatch.setattr(ServiceClient, "request", mocked_request)


# ==============================================================================
# ASGI-клиенты (для unit-тестов)
# ==============================================================================

@pytest_asyncio.fixture
async def rag_app(service_processes: ServiceProcesses):
    """FastAPI приложение RAG с lifespan (``service_processes``)."""
    return await service_processes.app("rag")


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
    async with AsyncClient(
        transport=transport,
        base_url=_PLATFORM_ASGI_BASE_URL,
        headers=_PLATFORM_ASGI_HOST_HEADERS,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def search_app(service_processes: ServiceProcesses):
    """FastAPI приложение search с lifespan (``service_processes``)."""
    return await service_processes.app("search")


@pytest_asyncio.fixture
async def search_client(search_app, setup_database_before_tests, auth_headers_system):
    """HTTP клиент для Search API (ASGI transport)."""
    _ = setup_database_before_tests
    transport = ASGITransport(app=search_app)
    async with AsyncClient(
        transport=transport,
        base_url=_PLATFORM_ASGI_BASE_URL,
        headers={**_PLATFORM_ASGI_HOST_HEADERS, **auth_headers_system},
    ) as client:
        yield client


@pytest_asyncio.fixture(scope="session")
async def crm_companies_initialized(app, auth_token_system, auth_token_company2, crm_di):
    """
    Инициализирует компании system и company2 один раз за сессию.

    initialize_company идемпотентна и insert-only: существующие типы/шаблоны
    не переписываются. Session scope убирает повторные вызовы на одном gw;
    под xdist каждый gw всё равно зовёт init — без insert-only это reseed
    ``system`` + personal namespace всех members → ERROR setup crm_client.

    Зависит от auth_token_system и auth_token_company2 чтобы гарантировать, что
    записи company:system и company:company2 уже существуют в storage до инициализации.

    Контекст устанавливается вручную: test_context — function-scoped,
    а эта фикстура — session-scoped, поэтому test_context ещё не существует.
    """
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

    await crm_di.company_init_service.initialize_company("system")

    set_context(Context(
        user=User(user_id="test_user", name="Test User"),
        active_company=make_test_company(company_id="company2", name="Company2"),
        session_id="test_session",
        channel="test",
        metadata={"user_id": "test_user", "email": "test@example.com", "grps": []},
    ))

    await crm_di.company_init_service.initialize_company("company2")

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
    service_processes: ServiceProcesses,
):
    """
    HTTP клиент для CRM API (ASGI transport, lifespan из ``service_processes``).

    Использует ASGI transport для быстрых unit тестов без запуска реального сервера.
    Таблицы создаются через миграции в setup_database_before_tests.

    Зависимости:
    - crm_companies_initialized: session-scoped, system/company2 компании
    - rag_app: для инициализации RAG таблиц
    - rag_service: реальный HTTP сервер для inter-service communication (attachments)
    - rag_worker: для обработки загруженных документов
    """
    from tests.fixtures.crm_test_setup import ensure_crm_per_test_namespace_and_types

    crm_app = await service_processes.app("crm")
    transport = ASGITransport(app=crm_app)
    async with AsyncClient(
        transport=transport,
        base_url=_PLATFORM_ASGI_BASE_URL,
        follow_redirects=True,
        headers=_PLATFORM_ASGI_HOST_HEADERS,
    ) as client:
        await ensure_crm_per_test_namespace_and_types(
            client,
            unique_id,
            auth_headers_system,
            auth_headers_company2,
        )
        yield client


@pytest_asyncio.fixture
async def sync_app(service_processes: ServiceProcesses):
    """FastAPI приложение Sync с lifespan (``service_processes``)."""
    return await service_processes.app("sync")


@pytest_asyncio.fixture
async def office_app(service_processes: ServiceProcesses):
    """FastAPI приложение office (Documents / OnlyOffice BFF + UI) с lifespan."""
    return await service_processes.app("office")


@pytest_asyncio.fixture
async def office_client(office_app):
    """HTTP-клиент для BFF office (ASGI). Миграции platform_office — в setup_database_before_tests."""
    transport = ASGITransport(app=office_app)
    async with AsyncClient(
        transport=transport,
        base_url=_PLATFORM_ASGI_BASE_URL,
        headers=_PLATFORM_ASGI_HOST_HEADERS,
    ) as client:
        yield client


@pytest.fixture
def voice_app(monkeypatch: pytest.MonkeyPatch):
    """
    FastAPI приложение voice с mock-провайдерами STT/TTS/VAD.

    Используется как sync fixture — доступна и для sync (TestClient / WS),
    и для async (voice_client) тестов.

    Устанавливает provider = 'mock' для всех провайдеров через monkeypatch env,
    сбрасывает синглтон ``core.config.get_settings``, кэш ``voice_resolver``,
    затем локальные синглтоны ``VoiceServiceSettings`` и voice.
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
    from core.ai.runtime import reset_voice_runtime_for_tests

    monkeypatch.setattr(config_base, "_settings_instance", None)
    reset_voice_runtime_for_tests()
    reset_voice_settings()

    from core.context import clear_context

    clear_context()

    from apps.voice.main import app

    yield app

    clear_context()
    reset_voice_runtime_for_tests()
    reset_voice_settings()


@pytest_asyncio.fixture
async def voice_client(voice_app):
    """HTTP-клиент для voice API (ASGI) внутри lifespan приложения этого теста."""
    transport = ASGITransport(app=voice_app)
    async with (
        voice_app.router.lifespan_context(voice_app),
        AsyncClient(
            transport=transport,
            base_url=_PLATFORM_ASGI_BASE_URL,
            headers=_PLATFORM_ASGI_HOST_HEADERS,
        ) as client,
    ):
        yield client


@pytest_asyncio.fixture
async def worktracker_client(worktracker_app, auth_headers_system):
    """HTTP клиент для Worktracker API (ASGI transport)."""
    transport = ASGITransport(app=worktracker_app)
    async with AsyncClient(
        transport=transport,
        base_url=_PLATFORM_ASGI_BASE_URL,
        headers={**_PLATFORM_ASGI_HOST_HEADERS, **auth_headers_system},
    ) as client:
        yield client


@pytest_asyncio.fixture
async def worktracker_app(service_processes: ServiceProcesses):
    """FastAPI приложение worktracker с lifespan (``service_processes``)."""
    return await service_processes.app("worktracker")


@pytest_asyncio.fixture
async def secrets_app(service_processes: ServiceProcesses):
    """FastAPI приложение secrets с lifespan (``service_processes``)."""
    return await service_processes.app("secrets")


@pytest_asyncio.fixture
async def secrets_client(secrets_app, setup_database_before_tests, auth_headers_system):
    """HTTP клиент для Secrets API (ASGI transport)."""
    _ = setup_database_before_tests
    transport = ASGITransport(app=secrets_app)
    async with AsyncClient(
        transport=transport,
        base_url=_PLATFORM_ASGI_BASE_URL,
        headers={**_PLATFORM_ASGI_HOST_HEADERS, **auth_headers_system},
    ) as client:
        yield client


@pytest_asyncio.fixture
async def sync_client(sync_app, sync_worker):
    """
    HTTP клиент для Sync API (ASGI, lifespan включён).

    Зависит от sync_worker: эндпоинты с enqueue(SYNC_*) ждут очередь sync.
    """
    transport = ASGITransport(app=sync_app)
    async with AsyncClient(
        transport=transport,
        base_url=_PLATFORM_ASGI_BASE_URL,
        headers=_PLATFORM_ASGI_HOST_HEADERS,
    ) as client:
        yield client


# ==============================================================================
# HTTP-клиенты (для E2E-тестов с реальными серверами)
# ==============================================================================

@pytest_asyncio.fixture
async def flows_client_http(flows_service):
    """
    HTTP клиент для Agents API (реальный HTTP).

    Использует реальный HTTP сервер на порту 9001.
    Для E2E тестов всей платформы.
    """
    async with AsyncClient(
        base_url="http://localhost:9001",
        timeout=_E2E_HTTP_TIMEOUT_SECONDS,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def office_client_http(office_service):
    """
    HTTP клиент для Documents/Office API (реальный HTTP).

    Использует реальный HTTP сервер на порту 9008.
    """
    async with AsyncClient(
        base_url="http://localhost:9008",
        timeout=_E2E_HTTP_TIMEOUT_SECONDS,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def sync_client_http(sync_service):
    """HTTP клиент Sync API (реальный Granian :9005)."""
    _ = sync_service
    async with AsyncClient(
        base_url="http://127.0.0.1:9005",
        timeout=_E2E_HTTP_TIMEOUT_SECONDS,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def frontend_client_http(frontend_service):
    """HTTP клиент Frontend API (реальный Granian :9004)."""
    _ = frontend_service
    async with AsyncClient(
        base_url="http://localhost:9004",
        timeout=_E2E_HTTP_TIMEOUT_SECONDS,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def secrets_client_http(secrets_service):
    """HTTP клиент Secrets API (реальный Granian :9022)."""
    _ = secrets_service
    async with AsyncClient(
        base_url="http://localhost:9022",
        timeout=_E2E_HTTP_TIMEOUT_SECONDS,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def scheduler_client_http(scheduler_service):
    """HTTP клиент Scheduler API (реальный Granian :9006)."""
    _ = scheduler_service
    async with AsyncClient(
        base_url="http://localhost:9006",
        timeout=_E2E_HTTP_TIMEOUT_SECONDS,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def search_client_http(search_service):
    """HTTP клиент Search API (реальный Granian :9010)."""
    _ = search_service
    async with AsyncClient(
        base_url="http://localhost:9010",
        timeout=_E2E_HTTP_TIMEOUT_SECONDS,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def wiki_client_http(wiki_service_http):
    """HTTP клиент Wiki API (реальный Granian :9023)."""
    _ = wiki_service_http
    async with AsyncClient(
        base_url="http://localhost:9023",
        timeout=_E2E_HTTP_TIMEOUT_SECONDS,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def rag_client_http(rag_service):
    """HTTP клиент RAG API (реальный Granian :9002)."""
    _ = rag_service
    async with AsyncClient(
        base_url="http://localhost:9002",
        timeout=_E2E_HTTP_TIMEOUT_SECONDS,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def worktracker_client_http(worktracker_http_service):
    """
    HTTP клиент для Worktracker API (реальный HTTP).

    Использует реальный HTTP сервер на порту 9021.
    """
    async with AsyncClient(
        base_url="http://localhost:9021",
        timeout=_E2E_HTTP_TIMEOUT_SECONDS,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def crm_client_http(crm_service):
    """HTTP клиент CRM API (реальный Granian :9003)."""
    _ = crm_service
    async with AsyncClient(
        base_url="http://localhost:9003",
        timeout=_E2E_HTTP_TIMEOUT_SECONDS,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def shop_client_http(shop_service):
    """HTTP клиент Shop API (реальный Granian :9027)."""
    _ = shop_service
    async with AsyncClient(
        base_url="http://127.0.0.1:9027",
        timeout=_E2E_HTTP_TIMEOUT_SECONDS,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def realtime_client_http(realtime_service):
    """HTTP клиент bus `realtime` (реальный Granian :9025)."""
    async with AsyncClient(
        base_url="http://localhost:9025",
        timeout=_E2E_HTTP_TIMEOUT_SECONDS,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def realtime_session_client(realtime_service, auth_headers_system):
    """SESSION JWT → bus :9025, как SPA GET /events."""
    async with AsyncClient(
        base_url="http://localhost:9025",
        timeout=_E2E_HTTP_TIMEOUT_SECONDS,
        headers=auth_headers_system,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def realtime_session_client_user2(realtime_service, auth_headers_system_user2):
    async with AsyncClient(
        base_url="http://localhost:9025",
        timeout=_E2E_HTTP_TIMEOUT_SECONDS,
        headers=auth_headers_system_user2,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def centrifugo_http(centrifugo_service):
    """HTTP health Centrifugo :19000 (тот же процесс, что user WS)."""
    _ = centrifugo_service
    async with AsyncClient(
        base_url="http://127.0.0.1:19000",
        timeout=10.0,
    ) as client:
        yield client
