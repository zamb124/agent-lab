"""
Integration тесты для API управления конфигурациями виджетов.

Тесты БЕЗ моков - проверяем реальные HTTP запросы.
Проверяем изоляцию по компаниям.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient


@pytest_asyncio.fixture
async def test_agent():
    """
    Создает тестового агента для API тестов.
    Использует текущий контекст из test_context или middleware.
    """
    from apps.flows.src.container import get_container
    from apps.flows.src.models.flow_config import FlowConfig
    
    flows_container = get_container()
    
    agent = FlowConfig(
        flow_id="test_agent",
        name="Test Agent",
        entry="main",
        nodes={
            "main": {
                "type": "llm_node",
                "prompt": "Test prompt",
                "next": None
            }
        },
    )
    await flows_container.flow_repository.set(agent)
    
    yield agent
    
    # Cleanup
    await flows_container.flow_repository.delete("test_agent")


@pytest_asyncio.fixture
async def auth_headers_other_company(frontend_client, frontend_container):
    """Фикстура для заголовков другой компании"""
    import uuid
    from core.utils.tokens import get_token_service
    from core.models.identity_models import User, Company
    
    company_id = "other_company"
    
    # Создаем компанию
    company = Company(
        company_id=company_id,
        name="Other Company",
        owner_id="other_user",
    )
    await frontend_container.company_repository.set(company)
    
    user_id = f"test_user_other_{uuid.uuid4().hex[:8]}"
    user = User(
        user_id=user_id,
        name="Other User",
        email=f"{user_id}@test.com",
        companies={company_id: ["admin"]},
        active_company_id=company_id
    )
    
    await frontend_container.user_repository.set(user)
    
    token_service = get_token_service()
    token = token_service.create_token(user_id, company_id=company_id)
    
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def test_auth_with_agent(frontend_container):
    """
    Создаёт пользователя, компанию И агента в одной компании.
    Возвращает headers и flows_container для cleanup.
    """
    import uuid
    from core.utils.tokens import get_token_service
    from core.models.identity_models import User, Company
    from core.context import set_context, clear_context, Context
    from apps.flows.src.container import get_container
    from apps.flows.src.models.flow_config import FlowConfig
    
    # Создаём компанию
    company_id = f"test_company_{uuid.uuid4().hex[:8]}"
    company = Company(
        company_id=company_id,
        name="Test Company",
        owner_id="test_user",
    )
    await frontend_container.company_repository.set(company)
    
    # Создаём юзера
    user_id = f"test_user_{uuid.uuid4().hex[:8]}"
    user = User(
        user_id=user_id,
        name="Test User",
        email=f"{user_id}@test.com",
        companies={company_id: ["admin"]},
        active_company_id=company_id
    )
    await frontend_container.user_repository.set(user)
    
    # Создаём агента В ЭТОЙ ЖЕ КОМПАНИИ
    set_context(Context(
        user=User(user_id=user_id, name="Test"),
        active_company=Company(company_id=company_id, name="Test Company"),
        session_id="test",
        channel="test",
    ))
    
    flows_container = get_container()
    agent = FlowConfig(
        flow_id="test_agent",
        name="Test Agent",
        entry="main",
        nodes={"main": {"type": "llm_node", "prompt": "Test", "next": None}},
    )
    await flows_container.flow_repository.set(agent)
    clear_context()
    
    # Генерируем токен
    token_service = get_token_service()
    token = token_service.create_token(user_id, company_id=company_id)
    
    yield {"Authorization": f"Bearer {token}"}, flows_container, company_id
    
    # Cleanup агента
    set_context(Context(
        user=User(user_id=user_id, name="Test"),
        active_company=Company(company_id=company_id, name="Test Company"),
        session_id="test",
        channel="test",
    ))
    await flows_container.flow_repository.delete("test_agent")
    clear_context()


@pytest_asyncio.fixture
async def test_auth_with_agent_other_company(frontend_container):
    """
    Создаёт ДРУГУЮ компанию с пользователем и агентом для тестирования изоляции.
    """
    import uuid
    from core.utils.tokens import get_token_service
    from core.models.identity_models import User, Company
    from core.context import set_context, clear_context, Context
    from apps.flows.src.container import get_container
    from apps.flows.src.models.flow_config import FlowConfig
    
    # Создаём ДРУГУЮ компанию
    company_id = f"test_company_other_{uuid.uuid4().hex[:8]}"
    company = Company(
        company_id=company_id,
        name="Other Test Company",
        owner_id="test_user_other",
    )
    await frontend_container.company_repository.set(company)
    
    # Создаём другого юзера
    user_id = f"test_user_other_{uuid.uuid4().hex[:8]}"
    user = User(
        user_id=user_id,
        name="Other Test User",
        email=f"{user_id}@test.com",
        companies={company_id: ["admin"]},
        active_company_id=company_id
    )
    await frontend_container.user_repository.set(user)
    
    # Создаём агента В ЭТОЙ ЖЕ КОМПАНИИ
    set_context(Context(
        user=User(user_id=user_id, name="Other Test"),
        active_company=Company(company_id=company_id, name="Other Test Company"),
        session_id="test",
        channel="test",
    ))
    
    flows_container = get_container()
    agent = FlowConfig(
        flow_id="test_agent_other",
        name="Other Test Agent",
        entry="main",
        nodes={"main": {"type": "llm_node", "prompt": "Test", "next": None}},
    )
    await flows_container.flow_repository.set(agent)
    clear_context()
    
    # Генерируем токен
    token_service = get_token_service()
    token = token_service.create_token(user_id, company_id=company_id)
    
    yield {"Authorization": f"Bearer {token}"}, flows_container, company_id
    
    # Cleanup агента
    set_context(Context(
        user=User(user_id=user_id, name="Other Test"),
        active_company=Company(company_id=company_id, name="Other Test Company"),
        session_id="test",
        channel="test",
    ))
    await flows_container.flow_repository.delete("test_agent_other")
    clear_context()


@pytest.mark.asyncio
async def test_create_embed_config(frontend_client: AsyncClient, test_auth_with_agent):
    """Тест создания конфигурации виджета"""
    
    auth_headers, flows_container, company_id = test_auth_with_agent
    
    # Создаем конфигурацию
    response = await frontend_client.post(
        "/frontend/api/embed/configs",
        headers=auth_headers,
        json={
            "name": "Test Widget",
            "flow_id": "test_agent",
            "allowed_origins": ["https://example.com", "https://test.com"],
            "theme": "dark",
            "position": "bottom-right",
            "show_reasoning": True,
            "show_tool_calls": False,
            "primary_color": "#6366f1",
            "greeting_message": "Hello! How can I help?",
            "placeholder": "Type your message...",
            "branding": True,
        }
    )
    
    if response.status_code != 200:
        print(f"❌ Ошибка: {response.status_code}")
        print(f"Ответ: {response.text}")
    
    assert response.status_code == 200
    data = response.json()
    
    # Проверяем ответ
    assert "embed_id" in data
    assert data["name"] == "Test Widget"
    assert data["flow_id"] == "test_agent"
    assert data["allowed_origins"] == ["https://example.com", "https://test.com"]
    assert data["status"] == "active"
    assert data["theme"] == "dark"
    assert data["show_reasoning"] is True
    assert data["show_tool_calls"] is False
    assert data["usage_count"] == 0
    assert data["last_used_at"] is None
    assert "created_at" in data
    assert "created_by" in data
    
    embed_id = data["embed_id"]
    
    # Cleanup
    await frontend_client.delete(
        f"/frontend/api/embed/configs/{embed_id}",
        headers=auth_headers
    )


@pytest.mark.asyncio
async def test_list_embed_configs(frontend_client: AsyncClient, test_auth_with_agent):
    """Тест получения списка конфигураций"""
    
    auth_headers, flows_container, company_id = test_auth_with_agent
    
    # Создаем несколько конфигураций
    embed_ids = []
    for i in range(3):
        response = await frontend_client.post(
            "/frontend/api/embed/configs",
            headers=auth_headers,
            json={
                "name": f"Widget {i}",
                "flow_id": "test_agent",  # Используем существующего агента
            }
        )
        assert response.status_code == 200
        embed_ids.append(response.json()["embed_id"])
    
    # Получаем список
    response = await frontend_client.get(
        "/frontend/api/embed/configs",
        headers=auth_headers
    )
    
    assert response.status_code == 200
    configs = response.json()
    
    assert isinstance(configs, list)
    assert len(configs) >= 3
    
    # Проверяем что наши конфигурации в списке
    config_ids = [c["embed_id"] for c in configs]
    for embed_id in embed_ids:
        assert embed_id in config_ids
    
    # Cleanup
    for embed_id in embed_ids:
        await frontend_client.delete(
            f"/frontend/api/embed/configs/{embed_id}",
            headers=auth_headers
        )


@pytest.mark.asyncio
async def test_get_embed_config(frontend_client: AsyncClient, test_auth_with_agent):
    """Тест получения конкретной конфигурации"""
    
    auth_headers, flows_container, company_id = test_auth_with_agent
    
    # Создаем конфигурацию
    create_response = await frontend_client.post(
        "/frontend/api/embed/configs",
        headers=auth_headers,
        json={
            "name": "Get Test Widget",
            "flow_id": "test_agent",
            "greeting_message": "Test greeting",
        }
    )
    
    assert create_response.status_code == 200
    embed_id = create_response.json()["embed_id"]
    
    # Получаем конфигурацию
    response = await frontend_client.get(
        f"/frontend/api/embed/configs/{embed_id}",
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["embed_id"] == embed_id
    assert data["name"] == "Get Test Widget"
    assert data["flow_id"] == "test_agent"
    assert data["greeting_message"] == "Test greeting"
    
    # Cleanup
    await frontend_client.delete(
        f"/frontend/api/embed/configs/{embed_id}",
        headers=auth_headers
    )


@pytest.mark.asyncio
async def test_update_embed_config(frontend_client: AsyncClient, test_auth_with_agent):
    """Тест обновления конфигурации"""
    
    auth_headers, flows_container, company_id = test_auth_with_agent
    
    # Создаем конфигурацию
    create_response = await frontend_client.post(
        "/frontend/api/embed/configs",
        headers=auth_headers,
        json={
            "name": "Original Name",
            "flow_id": "test_agent",
            "theme": "dark",
        }
    )
    
    assert create_response.status_code == 200
    embed_id = create_response.json()["embed_id"]
    
    # Обновляем конфигурацию
    response = await frontend_client.patch(
        f"/frontend/api/embed/configs/{embed_id}",
        headers=auth_headers,
        json={
            "name": "Updated Name",
            "theme": "light",
            "status": "disabled",
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["embed_id"] == embed_id
    assert data["name"] == "Updated Name"
    assert data["theme"] == "light"
    assert data["status"] == "disabled"
    assert data["flow_id"] == "test_agent"  # Не изменился
    
    # Cleanup
    await frontend_client.delete(
        f"/frontend/api/embed/configs/{embed_id}",
        headers=auth_headers
    )


@pytest.mark.asyncio
async def test_delete_embed_config(frontend_client: AsyncClient, test_auth_with_agent):
    """Тест удаления конфигурации"""
    
    auth_headers, flows_container, company_id = test_auth_with_agent
    
    # Создаем конфигурацию
    create_response = await frontend_client.post(
        "/frontend/api/embed/configs",
        headers=auth_headers,
        json={
            "name": "Delete Test",
            "flow_id": "test_agent",
        }
    )
    
    assert create_response.status_code == 200
    embed_id = create_response.json()["embed_id"]
    
    # Удаляем
    delete_response = await frontend_client.delete(
        f"/frontend/api/embed/configs/{embed_id}",
        headers=auth_headers
    )
    
    assert delete_response.status_code == 200
    data = delete_response.json()
    assert data["success"] is True
    
    # Проверяем что удалилась
    get_response = await frontend_client.get(
        f"/frontend/api/embed/configs/{embed_id}",
        headers=auth_headers
    )
    
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_get_embed_code(frontend_client: AsyncClient, test_auth_with_agent):
    """Тест получения кода для встраивания"""
    
    auth_headers, flows_container, company_id = test_auth_with_agent
    
    # Создаем конфигурацию
    create_response = await frontend_client.post(
        "/frontend/api/embed/configs",
        headers=auth_headers,
        json={
            "name": "Code Test",
            "flow_id": "test_agent",
        }
    )
    
    assert create_response.status_code == 200
    embed_id = create_response.json()["embed_id"]
    
    # Получаем код
    response = await frontend_client.get(
        f"/frontend/api/embed/configs/{embed_id}/code",
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "html_code" in data
    assert "script_url" in data
    assert data["embed_id"] == embed_id
    
    # Проверяем что в коде есть нужные элементы
    html_code = data["html_code"]
    assert "HumanitecChat" in html_code
    assert embed_id in html_code
    assert "chat-widget" in html_code
    
    # Cleanup
    await frontend_client.delete(
        f"/frontend/api/embed/configs/{embed_id}",
        headers=auth_headers
    )


@pytest.mark.asyncio
async def test_company_isolation(
    frontend_client: AsyncClient, 
    test_auth_with_agent,
    test_auth_with_agent_other_company
):
    """
    Тест изоляции по компаниям.
    
    Конфигурации одной компании не должны быть видны другой.
    """
    
    auth_headers, flows_container, company_id = test_auth_with_agent
    auth_headers_other, flows_container_other, company_id_other = test_auth_with_agent_other_company
    
    # Создаем конфигурацию в компании 1
    response1 = await frontend_client.post(
        "/frontend/api/embed/configs",
        headers=auth_headers,
        json={
            "name": "Company 1 Widget",
            "flow_id": "test_agent",
        }
    )
    
    assert response1.status_code == 200
    embed_id_1 = response1.json()["embed_id"]
    
    # Создаем конфигурацию в компании 2
    response2 = await frontend_client.post(
        "/frontend/api/embed/configs",
        headers=auth_headers_other,
        json={
            "name": "Company 2 Widget",
            "flow_id": "test_agent_other",
        }
    )
    
    assert response2.status_code == 200
    embed_id_2 = response2.json()["embed_id"]
    
    # Компания 1 видит только свою конфигурацию
    list_response_1 = await frontend_client.get(
        "/frontend/api/embed/configs",
        headers=auth_headers
    )
    
    assert list_response_1.status_code == 200
    configs_1 = list_response_1.json()
    config_ids_1 = [c["embed_id"] for c in configs_1]
    
    assert embed_id_1 in config_ids_1
    assert embed_id_2 not in config_ids_1
    
    # Компания 2 видит только свою конфигурацию
    list_response_2 = await frontend_client.get(
        "/frontend/api/embed/configs",
        headers=auth_headers_other
    )
    
    assert list_response_2.status_code == 200
    configs_2 = list_response_2.json()
    config_ids_2 = [c["embed_id"] for c in configs_2]
    
    assert embed_id_2 in config_ids_2
    assert embed_id_1 not in config_ids_2
    
    # Компания 1 не может получить конфигурацию компании 2
    get_response_cross = await frontend_client.get(
        f"/frontend/api/embed/configs/{embed_id_2}",
        headers=auth_headers
    )
    
    assert get_response_cross.status_code == 404
    
    # Cleanup
    await frontend_client.delete(
        f"/frontend/api/embed/configs/{embed_id_1}",
        headers=auth_headers
    )
    
    await frontend_client.delete(
        f"/frontend/api/embed/configs/{embed_id_2}",
        headers=auth_headers_other
    )


@pytest.mark.asyncio
async def test_create_config_requires_auth(frontend_client: AsyncClient):
    """Тест что создание требует авторизации"""
    
    response = await frontend_client.post(
        "/frontend/api/embed/configs",
        json={
            "name": "Unauthorized Test",
            "flow_id": "test_agent",
        }
    )
    
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_config_with_nonexistent_agent(frontend_client: AsyncClient, auth_headers):
    """Тест создания с несуществующим агентом"""
    
    response = await frontend_client.post(
        "/frontend/api/embed/configs",
        headers=auth_headers,
        json={
            "name": "Invalid Agent Test",
            "flow_id": "nonexistent_agent_12345",
        }
    )
    
    # Должна быть ошибка 404 - агент не найден
    assert response.status_code == 404
    assert "не найден" in response.json()["detail"].lower()

