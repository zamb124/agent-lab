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
    assert data["branch_id"] == "default"
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
    configs = response.json()["items"]
    
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
    assert "platform-lara-assistant" in html_code
    assert embed_id in html_code
    assert "embed-id" in html_code
    assert "flow-id" not in html_code
    assert "skill-id" not in html_code
    assert "/static/core/lib/embed-chat/platform-lara-assistant.js" in html_code
    assert "fetch('/api/chat-token'" in html_code
    assert "embed_id: EMBED_ID" in html_code
    assert "session-token" not in html_code
    assert "credentials: 'include'" not in html_code
    assert "window.humanitecEmbed" in html_code
    assert "setTheme: setEmbedTheme" in html_code
    assert "setLocale: setEmbedLocale" in html_code
    assert "setLauncherVisible: setEmbedLauncherVisible" in html_code
    assert "setAssistantTitle: setEmbedAssistantTitle" in html_code
    assert "setMetadataHooks: setEmbedMetadataHooks" in html_code
    assert "setAuthProvider: setEmbedAuthProvider" in html_code
    assert data["token_endpoint"].endswith(f"/frontend/api/embed/configs/{embed_id}/session-token")
    
    # Cleanup
    await frontend_client.delete(
        f"/frontend/api/embed/configs/{embed_id}",
        headers=auth_headers
    )


@pytest.mark.asyncio
async def test_get_embed_code_has_no_browser_direct_fallback_patterns(
    frontend_client: AsyncClient,
    test_auth_with_agent,
):
    auth_headers, _, _ = test_auth_with_agent
    create_response = await frontend_client.post(
        "/frontend/api/embed/configs",
        headers=auth_headers,
        json={
            "name": "Code Contract Test",
            "flow_id": "test_agent",
        },
    )
    assert create_response.status_code == 200
    embed_id = create_response.json()["embed_id"]

    response = await frontend_client.get(
        f"/frontend/api/embed/configs/{embed_id}/code",
        headers=auth_headers,
    )
    assert response.status_code == 200
    html_code = response.json()["html_code"]

    assert "fetch('/api/chat-token'" in html_code
    assert "const EMBED_ID =" in html_code
    assert "getEmbedToken()" in html_code

    assert "fetch(\"http" not in html_code
    assert "fetch(\"https" not in html_code
    assert "/frontend/api/embed/configs/" not in html_code
    assert "/session-token" not in html_code
    assert "credentials: 'include'" not in html_code

    await frontend_client.delete(
        f"/frontend/api/embed/configs/{embed_id}",
        headers=auth_headers,
    )


@pytest.mark.asyncio
async def test_issue_embed_session_token(frontend_client: AsyncClient, test_auth_with_agent):
    auth_headers, flows_container, company_id = test_auth_with_agent

    create_response = await frontend_client.post(
        "/frontend/api/embed/configs",
        headers=auth_headers,
        json={
            "name": "Session Token Widget",
            "flow_id": "test_agent",
            "allowed_origins": ["https://larashved.ru"],
        },
    )
    assert create_response.status_code == 200
    embed_id = create_response.json()["embed_id"]

    token_response = await frontend_client.post(
        f"/frontend/api/embed/configs/{embed_id}/session-token",
        headers=auth_headers,
        json={"origin": "https://larashved.ru", "expires_in_seconds": 300},
    )
    assert token_response.status_code == 200
    payload = token_response.json()
    assert payload["token"]
    assert payload["token_type"] == "Bearer"
    assert payload["flow_id"] == "test_agent"
    assert payload["branch_id"] == "default"

    deny_response = await frontend_client.post(
        f"/frontend/api/embed/configs/{embed_id}/session-token",
        headers=auth_headers,
        json={"origin": "https://evil.example", "expires_in_seconds": 300},
    )
    assert deny_response.status_code == 403

    await frontend_client.delete(
        f"/frontend/api/embed/configs/{embed_id}",
        headers=auth_headers,
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
    configs_1 = list_response_1.json()["items"]
    config_ids_1 = [c["embed_id"] for c in configs_1]
    
    assert embed_id_1 in config_ids_1
    assert embed_id_2 not in config_ids_1
    
    # Компания 2 видит только свою конфигурацию
    list_response_2 = await frontend_client.get(
        "/frontend/api/embed/configs",
        headers=auth_headers_other
    )
    
    assert list_response_2.status_code == 200
    configs_2 = list_response_2.json()["items"]
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


@pytest.mark.asyncio
async def test_create_config_rejects_invalid_interface_locale(frontend_client: AsyncClient, test_auth_with_agent):
    auth_headers, _, _ = test_auth_with_agent
    response = await frontend_client.post(
        "/frontend/api/embed/configs",
        headers=auth_headers,
        json={
            "name": "Invalid Locale Widget",
            "flow_id": "test_agent",
            "interface_locale": "de",
        },
    )
    assert response.status_code == 400
    assert "interface_locale" in response.json()["detail"]


@pytest.mark.asyncio
async def test_issue_embed_session_token_requires_auth(frontend_client: AsyncClient, test_auth_with_agent):
    auth_headers, _, _ = test_auth_with_agent
    create_response = await frontend_client.post(
        "/frontend/api/embed/configs",
        headers=auth_headers,
        json={"name": "No Auth Token", "flow_id": "test_agent"},
    )
    assert create_response.status_code == 200
    embed_id = create_response.json()["embed_id"]

    unauthorized = await frontend_client.post(
        f"/frontend/api/embed/configs/{embed_id}/session-token",
        json={"origin": "https://larashved.ru", "expires_in_seconds": 300},
    )
    assert unauthorized.status_code == 401

    await frontend_client.delete(f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_issue_embed_session_token_with_hum_api_key(frontend_client: AsyncClient, test_auth_with_agent):
    auth_headers, _, _ = test_auth_with_agent
    create_response = await frontend_client.post(
        "/frontend/api/embed/configs",
        headers=auth_headers,
        json={
            "name": "Hum API Key Token Widget",
            "flow_id": "test_agent",
            "allowed_origins": ["http://localhost:8000"],
        },
    )
    assert create_response.status_code == 200
    embed_id = create_response.json()["embed_id"]

    from apps.frontend.container import get_frontend_container
    from core.utils.tokens import get_token_service

    token_data = get_token_service().validate_token(auth_headers["Authorization"].replace("Bearer ", ""))
    assert token_data is not None
    company = await get_frontend_container().company_repository.get(token_data.company_id)
    assert company is not None
    members = dict(company.members or {})
    members[token_data.user_id] = ["admin"]
    company.members = members
    await get_frontend_container().company_repository.set(company)

    api_key_response = await frontend_client.post(
        "/frontend/api/api-keys",
        headers=auth_headers,
        json={"name": "Embed issuer key", "scopes": ["agents:read"]},
    )
    assert api_key_response.status_code == 200
    api_key_secret = api_key_response.json()["secret"]
    assert api_key_secret.startswith("hum_")

    token_response = await frontend_client.post(
        f"/frontend/api/embed/configs/{embed_id}/session-token",
        headers={"Authorization": f"Bearer {api_key_secret}"},
        json={"origin": "http://localhost:8000", "expires_in_seconds": 300},
    )
    assert token_response.status_code == 200
    token_data = token_response.json()
    assert token_data["token_type"] == "Bearer"
    assert token_data["flow_id"] == "test_agent"

    await frontend_client.delete(f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_issue_embed_session_token_for_disabled_config(frontend_client: AsyncClient, test_auth_with_agent):
    auth_headers, _, _ = test_auth_with_agent
    create_response = await frontend_client.post(
        "/frontend/api/embed/configs",
        headers=auth_headers,
        json={"name": "Disabled Token Widget", "flow_id": "test_agent"},
    )
    assert create_response.status_code == 200
    embed_id = create_response.json()["embed_id"]

    disable_response = await frontend_client.patch(
        f"/frontend/api/embed/configs/{embed_id}",
        headers=auth_headers,
        json={"status": "disabled"},
    )
    assert disable_response.status_code == 200

    token_response = await frontend_client.post(
        f"/frontend/api/embed/configs/{embed_id}/session-token",
        headers=auth_headers,
        json={"origin": "https://larashved.ru", "expires_in_seconds": 300},
    )
    assert token_response.status_code == 403
    assert "отключена" in token_response.json()["detail"]

    await frontend_client.delete(f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_embed_code_includes_assistant_title_and_locale(frontend_client: AsyncClient, test_auth_with_agent):
    auth_headers, _, _ = test_auth_with_agent
    create_response = await frontend_client.post(
        "/frontend/api/embed/configs",
        headers=auth_headers,
        json={
            "name": "Code Params Widget",
            "flow_id": "test_agent",
            "assistant_title": "Lara QA",
            "interface_locale": "ru",
            "theme": "light",
            "show_launcher": False,
        },
    )
    assert create_response.status_code == 200
    embed_id = create_response.json()["embed_id"]

    code_response = await frontend_client.get(
        f"/frontend/api/embed/configs/{embed_id}/code",
        headers=auth_headers,
    )
    assert code_response.status_code == 200
    html_code = code_response.json()["html_code"]
    assert "assistant.setAttribute('assistant-title', \"Lara QA\")" in html_code
    assert "assistant.setAttribute('locale', \"ru\")" in html_code
    assert "assistant.setAttribute('theme', \"light\")" in html_code
    assert "assistant.showLauncher = false;" in html_code

    await frontend_client.delete(f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_create_embed_config_allowed_origins_normalized(frontend_client: AsyncClient, test_auth_with_agent):
    auth_headers, flows_container, company_id = test_auth_with_agent
    import uuid
    from core.context import Context, clear_context, set_context
    from core.models.identity_models import Company, User
    from apps.flows.src.models.flow_config import FlowConfig

    flow_id = f"test_embed_origins_{uuid.uuid4().hex[:8]}"
    set_context(
        Context(
            user=User(user_id="test_user", name="Test"),
            active_company=Company(company_id=company_id, name="Test Company"),
            session_id="test",
            channel="test",
        )
    )
    try:
        await flows_container.flow_repository.set(
            FlowConfig(
                flow_id=flow_id,
                name="Test Embed Origins Flow",
                entry="main",
                nodes={"main": {"type": "llm_node", "prompt": "Test", "next": None}},
            )
        )
    finally:
        clear_context()

    response = await frontend_client.post(
        "/frontend/api/embed/configs",
        headers=auth_headers,
        json={
            "name": "Embed Origins Widget",
            "flow_id": flow_id,
            "allowed_origins": [
                "  http://localhost:8000 ",
                "https://larashved.ru",
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["allowed_origins"] == [
        "http://localhost:8000",
        "https://larashved.ru",
    ]

    await frontend_client.delete(f"/frontend/api/embed/configs/{data['embed_id']}", headers=auth_headers)

    set_context(
        Context(
            user=User(user_id="test_user", name="Test"),
            active_company=Company(company_id=company_id, name="Test Company"),
            session_id="test",
            channel="test",
        )
    )
    try:
        await flows_container.flow_repository.delete(flow_id)
    finally:
        clear_context()

