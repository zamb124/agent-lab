"""
Тесты для CRUD роутера TaskRepository.
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
def test_task_data(test_context):
    """Тестовые данные task"""
    context_dict = test_context.model_dump(
        mode='json',
        exclude={"state", "flow_config", "agent_config", "interface", "container"}
    )
    return {
        "task_id": "test_task_123",
        "flow_id": "test_flow",
        "context": context_dict,
        "status": "pending",
        "input_data": {"message": "Test message"}
    }


@pytest.mark.asyncio
async def test_list_tasks_empty(client):
    """Тест получения списка tasks"""
    response = await client.get("/agents/api/v1/task")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_create_task(client, test_task_data):
    """Тест создания task"""
    response = await client.post("/agents/api/v1/task", json=test_task_data)
    if response.status_code != 200:
        print(f"Response: {response.status_code} - {response.text}")
    assert response.status_code == 200
    
    data = response.json()
    assert data["task_id"] == test_task_data["task_id"]


@pytest.mark.asyncio
async def test_get_task(client, test_task_data):
    """Тест получения task по ID"""
    await client.post("/agents/api/v1/task", json=test_task_data)
    
    response = await client.get(f"/agents/api/v1/task/{test_task_data['task_id']}")
    assert response.status_code == 200
    
    data = response.json()
    assert data["task_id"] == test_task_data["task_id"]


@pytest.mark.asyncio
async def test_delete_task(client, test_task_data):
    """Тест удаления task"""
    await client.post("/agents/api/v1/task", json=test_task_data)
    
    response = await client.delete(f"/agents/api/v1/task/{test_task_data['task_id']}")
    assert response.status_code == 200
    
    get_response = await client.get(f"/agents/api/v1/task/{test_task_data['task_id']}")
    assert get_response.status_code == 404

