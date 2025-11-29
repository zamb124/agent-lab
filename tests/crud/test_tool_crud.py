"""
Тесты для CRUD роутера ToolRepository.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient

from apps.agents.main import create_app
from tests.conftest import test_context, save_test_company


@pytest_asyncio.fixture
async def app(migrated_db, test_context, save_test_company):
    """FastAPI приложение для тестов"""
    return create_app()


@pytest_asyncio.fixture
async def client(app):
    """Асинхронный тестовый клиент"""
    from httpx import ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def test_tool_data():
    """Тестовые данные tool"""
    return {
        "tool_id": "test_tool_123",
        "code_mode": "inline_code",
        "inline_code": "def test_tool(): return 'test'",
        "description": "Test tool for CRUD tests"
    }


@pytest.mark.asyncio
async def test_list_tools_empty(client):
    """Тест получения списка tools"""
    response = await client.get("/agents/api/v1/tool")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_create_tool(client, test_tool_data):
    """Тест создания tool"""
    response = await client.post("/agents/api/v1/tool", json=test_tool_data)
    assert response.status_code == 200
    
    data = response.json()
    assert data["tool_id"] == test_tool_data["tool_id"]


@pytest.mark.asyncio
async def test_get_tool(client, test_tool_data):
    """Тест получения tool по ID"""
    await client.post("/agents/api/v1/tool", json=test_tool_data)
    
    response = await client.get(f"/agents/api/v1/tool/{test_tool_data['tool_id']}")
    assert response.status_code == 200
    
    data = response.json()
    assert data["tool_id"] == test_tool_data["tool_id"]


@pytest.mark.asyncio
async def test_delete_tool(client, test_tool_data):
    """Тест удаления tool"""
    await client.post("/agents/api/v1/tool", json=test_tool_data)
    
    response = await client.delete(f"/agents/api/v1/tool/{test_tool_data['tool_id']}")
    assert response.status_code == 200
    
    get_response = await client.get(f"/agents/api/v1/tool/{test_tool_data['tool_id']}")
    assert get_response.status_code == 404

