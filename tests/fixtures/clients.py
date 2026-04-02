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

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# rag_worker импортируется из tests.conftest через pytest
# Он объявлен там как session-scoped фикстура


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


@pytest_asyncio.fixture
async def crm_client(
    app,
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
    - app: Agents service (из tests/conftest.py)
    - rag_app: для инициализации RAG таблиц
    - rag_service: реальный HTTP сервер для inter-service communication (attachments)
    - rag_worker: для обработки загруженных документов
    """
    from apps.crm.main import create_app
    from apps.crm.container import get_crm_container

    from tests.fixtures.crm_test_setup import ensure_crm_per_test_namespace_and_types

    crm_app = create_app()

    container = get_crm_container()
    await container.company_init_service.initialize_company("system")
    await container.company_init_service.initialize_company("company2")

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
    
    Использует реальный HTTP сервер на порту 8000.
    Для E2E тестов всей платформы.
    """
    async with AsyncClient(base_url="http://localhost:8000") as client:
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
async def crm_client_http(crm_service, rag_service):
    """
    HTTP клиент для CRM API (реальный HTTP).
    
    Использует реальный HTTP сервер на порту 8003.
    Для E2E тестов всей платформы.
    Таблицы создаются через миграции в setup_database_before_tests.
    
    Зависимости:
    - rag_service: для attachments через inter-service communication
    """
    from apps.crm.container import get_crm_container
    
    container = get_crm_container()
    await container.company_init_service.initialize_company("system")
    await container.company_init_service.initialize_company("company2")
    
    async with AsyncClient(base_url="http://localhost:8003") as client:
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

