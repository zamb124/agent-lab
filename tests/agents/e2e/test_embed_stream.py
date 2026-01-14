"""
E2E тесты для публичного API встраиваемого виджета.

Тесты РЕАЛЬНОГО SSE стриминга (только MockLLM, без других моков).
Строгая валидация JSON-RPC 2.0 и A2A протокола.
"""

import json
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient

from core.clients.llm import setup_mock_responses
from core.utils.tokens import get_token_service
from core.models.identity_models import User, Company
from core.context import set_context, clear_context, Context


@pytest_asyncio.fixture
async def embed_test_auth(frontend_container):
    """
    Создаёт пользователя, компанию И агента в одной компании для embed тестов.
    Возвращает headers, agents_container, company_id и agent_id для cleanup.
    """
    from apps.agents.src.container import get_container as get_agents_container
    from apps.agents.src.models.agent_config import AgentConfig
    
    company_id = f"test_company_{uuid.uuid4().hex[:8]}"
    company = Company(
        company_id=company_id,
        name="Test Company",
        owner_id="test_user",
    )
    await frontend_container.company_repository.set(company)
    
    user_id = f"test_user_{uuid.uuid4().hex[:8]}"
    user = User(
        user_id=user_id,
        name="Test User",
        email=f"{user_id}@test.com",
        companies={company_id: ["admin"]},
        active_company_id=company_id
    )
    await frontend_container.user_repository.set(user)
    
    set_context(Context(
        user=User(user_id=user_id, name="Test"),
        active_company=Company(company_id=company_id, name="Test Company"),
        session_id="test",
        channel="test",
    ))
    
    agents_container = get_agents_container()
    
    # Создаем уникальный agent_id для изоляции тестов
    test_agent_id = f"test_agent_{company_id}"
    
    agent = AgentConfig(
        agent_id=test_agent_id,
        name="Test Agent",
        entry="main",
        nodes={"main": {"type": "react_node", "prompt": "Test", "llm": {"model": "mock"}}},
        edges=[{"from": "main", "to": None}],
    )
    await agents_container.agent_repository.set(agent)
    clear_context()
    
    token_service = get_token_service()
    token = token_service.create_token(user_id, company_id=company_id)
    
    yield {"Authorization": f"Bearer {token}"}, agents_container, company_id, test_agent_id
    
    set_context(Context(
        user=User(user_id=user_id, name="Test"),
        active_company=Company(company_id=company_id, name="Test Company"),
        session_id="test",
        channel="test",
    ))
    await agents_container.agent_repository.delete(test_agent_id)
    clear_context()


async def create_embed_config(frontend_client: AsyncClient, auth_headers: dict, config_data: dict) -> str:
    """Helper для создания embed конфигурации через frontend API"""
    response = await frontend_client.post(
        "/frontend/api/embed/configs",
        headers=auth_headers,
        json=config_data
    )
    assert response.status_code == 200, f"Failed to create embed config: {response.text}"
    return response.json()["embed_id"]


def _parse_sse(text: str) -> list[dict]:
    """Парсинг SSE событий"""
    events = []
    for line in text.strip().split("\n"):
        if line.startswith("data:"):
            try:
                data = json.loads(line[5:].strip())
                events.append(data)
            except json.JSONDecodeError:
                pass
    return events


def _validate_jsonrpc_response(data: dict) -> None:
    """Валидация JSON-RPC 2.0 ответа"""
    assert "jsonrpc" in data
    assert data["jsonrpc"] == "2.0"
    assert "id" in data
    assert "result" in data or "error" in data


@pytest.mark.asyncio
async def test_embed_settings_endpoint(
    agents_client: AsyncClient,
    frontend_client: AsyncClient,
    embed_test_auth
):
    """Тест публичного endpoint настроек виджета"""

    auth_headers, agents_container, company_id, test_agent_id = embed_test_auth
    
    # Создаем конфигурацию через management API
    embed_id = await create_embed_config(frontend_client, auth_headers, {
        "name": "Settings Test Widget",
        "agent_id": test_agent_id,
        "theme": "dark",
        "position": "bottom-right",
        "show_reasoning": True,
        "show_tool_calls": False,
        "primary_color": "#ff6b6b",
        "greeting_message": "Hello from test!",
        "placeholder": "Test placeholder",
        "branding": False,
    })
    
    # Получаем настройки через публичный endpoint (БЕЗ авторизации)
    settings_response = await agents_client.get(
        f"/agents/api/v1/embed/{embed_id}/settings"
    )
    
    assert settings_response.status_code == 200
    settings = settings_response.json()
    
    # Проверяем что возвращены только публичные настройки
    assert settings["embed_id"] == embed_id
    assert settings["agent_id"] == test_agent_id
    assert settings["theme"] == "dark"
    assert settings["position"] == "bottom-right"
    assert settings["show_reasoning"] is True
    assert settings["show_tool_calls"] is False
    assert settings["primary_color"] == "#ff6b6b"
    assert settings["greeting_message"] == "Hello from test!"
    assert settings["placeholder"] == "Test placeholder"
    assert settings["branding"] is False
    
    # НЕ должны возвращаться внутренние поля
    assert "usage_count" not in settings
    assert "created_by" not in settings
    assert "created_at" not in settings
    
    # Cleanup
    await frontend_client.delete(
        f"/frontend/api/embed/configs/{embed_id}",
        headers=auth_headers
    )


@pytest.mark.asyncio
async def test_embed_settings_disabled_widget(
    agents_client: AsyncClient,
    frontend_client: AsyncClient,
    embed_test_auth
):
    """Тест что отключенный виджет возвращает 403"""
    
    auth_headers, agents_container, company_id, test_agent_id = embed_test_auth
    
    # Создаем отключенную конфигурацию
    embed_id = await create_embed_config(frontend_client, auth_headers, {
        "name": "Disabled Widget",
        "agent_id": test_agent_id,
    })
    
    # Отключаем виджет
    await frontend_client.patch(
        f"/frontend/api/embed/configs/{embed_id}",
        headers=auth_headers,
        json={"status": "disabled"}
    )
    
    # Попытка получить настройки должна вернуть 403
    settings_response = await agents_client.get(
        f"/agents/api/v1/embed/{embed_id}/settings"
    )
    
    assert settings_response.status_code == 403
    assert "отключен" in settings_response.json()["detail"].lower()
    
    # Cleanup
    await agents_client.delete(
        f"/frontend/api/embed/configs/{embed_id}",
        headers=auth_headers
    )


@pytest.mark.asyncio
async def test_embed_settings_nonexistent_widget(agents_client: AsyncClient):
    """Тест что несуществующий виджет возвращает 404"""
    
    response = await agents_client.get(
        "/agents/api/v1/embed/nonexistent_embed_id_12345/settings"
    )
    
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_embed_stream_basic_flow(agents_client: AsyncClient, frontend_client: AsyncClient, embed_test_auth):
    """
    Тест базового потока SSE стриминга.
    
    РЕАЛЬНЫЙ стриминг с MockLLM (БЕЗ других моков).
    """
    
    auth_headers, agents_container, company_id, test_agent_id = embed_test_auth
    
    # Настраиваем Mock LLM
    setup_mock_responses(response_queue=[
        {"type": "text", "text": "Привет! Это тестовый ответ от агента."}
    ])
    
    # Создаем конфигурацию виджета через frontend API
    create_response = await frontend_client.post(
        "/frontend/api/embed/configs",
        headers=auth_headers,
        json={
            "name": "Stream Test Widget",
            "agent_id": test_agent_id,
        }
    )
    
    assert create_response.status_code == 200
    embed_id = create_response.json()["embed_id"]
    
    # Отправляем сообщение через SSE stream (БЕЗ авторизации!)
    stream_response = await agents_client.get(
        f"/agents/api/v1/embed/{embed_id}/stream",
        params={"message": "Привет!"},
        timeout=30.0
    )
    
    assert stream_response.status_code == 200
    assert stream_response.headers["content-type"] == "text/event-stream; charset=utf-8"
    
    # Парсим SSE события
    events = _parse_sse(stream_response.text)
    
    print(f"\n🔍 DEBUG: Получено {len(events)} событий")
    print(f"🔍 DEBUG: Raw response text: {stream_response.text[:500]}")
    for i, event in enumerate(events):
        print(f"🔍 DEBUG: Event {i}: {event}")
    
    assert len(events) > 0, "Должно быть хотя бы одно событие"
    
    # Проверяем формат JSON-RPC 2.0
    for event in events:
        _validate_jsonrpc_response(event)
        
        # Проверяем что нет ошибок
        assert "error" not in event or event.get("error") is None
        
        if "result" in event:
            result = event["result"]
            
            # Проверяем структуру события
            if result.get("kind") == "artifact-update":
                assert "taskId" in result or "task_id" in result
                assert "contextId" in result or "context_id" in result
                assert "artifact" in result
                
                artifact = result["artifact"]
                if artifact.get("parts"):
                    # Проверяем что есть текст
                    text_parts = [p for p in artifact["parts"] if p.get("type") == "text"]
                    if text_parts:
                        text = "".join(p.get("text", "") for p in text_parts)
                        assert len(text) > 0
    
    # Проверяем что есть хотя бы одно artifact-update событие
    artifact_events = [e for e in events if e.get("result", {}).get("kind") == "artifact-update"]
    assert len(artifact_events) > 0, "Должно быть хотя бы одно artifact-update событие"
    
    # Cleanup
    await frontend_client.delete(
        f"/frontend/api/embed/configs/{embed_id}",
        headers=auth_headers
    )


@pytest.mark.asyncio
async def test_embed_stream_usage_count(agents_client: AsyncClient, frontend_client: AsyncClient, embed_test_auth):
    """Тест что usage_count увеличивается при использовании"""
    
    auth_headers, agents_container, company_id, test_agent_id = embed_test_auth
    
    setup_mock_responses(response_queue=[
        {"type": "text", "text": "Test response"}
    ])
    
    # Создаем конфигурацию
    create_response = await frontend_client.post(
        "/frontend/api/embed/configs",
        headers=auth_headers,
        json={
            "name": "Usage Test",
            "agent_id": test_agent_id,
        }
    )
    
    assert create_response.status_code == 200
    embed_id = create_response.json()["embed_id"]
    
    # Проверяем начальное значение
    config = await frontend_client.get(
        f"/frontend/api/embed/configs/{embed_id}",
        headers=auth_headers
    )
    assert config.json()["usage_count"] == 0
    
    # Используем виджет
    await agents_client.get(
        f"/agents/api/v1/embed/{embed_id}/stream",
        params={"message": "Test"},
        timeout=30.0
    )
    
    # Проверяем что счетчик увеличился
    config_after = await frontend_client.get(
        f"/frontend/api/embed/configs/{embed_id}",
        headers=auth_headers
    )
    assert config_after.json()["usage_count"] == 1
    assert config_after.json()["last_used_at"] is not None
    
    # Cleanup
    await frontend_client.delete(
        f"/frontend/api/embed/configs/{embed_id}",
        headers=auth_headers
    )
    
    await agents_client.delete(
        f"/agents/api/v1/agents/usage_test_agent",
        headers=auth_headers
    )


@pytest.mark.asyncio
async def test_embed_stream_disabled_widget(agents_client: AsyncClient, frontend_client: AsyncClient, embed_test_auth):
    """Тест что отключенный виджет не работает"""
    
    auth_headers, agents_container, company_id, test_agent_id = embed_test_auth
    
    # Создаем и отключаем конфигурацию
    create_response = await frontend_client.post(
        "/frontend/api/embed/configs",
        headers=auth_headers,
        json={
            "name": "Disabled Widget",
            "agent_id": test_agent_id,
        }
    )
    
    embed_id = create_response.json()["embed_id"]
    
    await frontend_client.patch(
        f"/frontend/api/embed/configs/{embed_id}",
        headers=auth_headers,
        json={"status": "disabled"}
    )
    
    # Попытка использовать должна вернуть 403
    stream_response = await agents_client.get(
        f"/agents/api/v1/embed/{embed_id}/stream",
        params={"message": "Test"}
    )
    
    assert stream_response.status_code == 403
    
    # Cleanup
    await agents_client.delete(
        f"/frontend/api/embed/configs/{embed_id}",
        headers=auth_headers
    )
    
    await agents_client.delete(
        f"/agents/api/v1/agents/disabled_test_agent",
        headers=auth_headers
    )


@pytest.mark.asyncio
async def test_embed_stream_with_context_id(agents_client: AsyncClient, frontend_client: AsyncClient, embed_test_auth):
    """Тест что context_id сохраняется между запросами"""
    
    auth_headers, agents_container, company_id, test_agent_id = embed_test_auth
    
    setup_mock_responses(response_queue=[
        {"type": "text", "text": "Response 1"},
        {"type": "text", "text": "Response 2"},
    ])
    
    # Создаем конфигурацию
    create_response = await frontend_client.post(
        "/frontend/api/embed/configs",
        headers=auth_headers,
        json={
            "name": "Context Test",
            "agent_id": test_agent_id,
        }
    )
    
    embed_id = create_response.json()["embed_id"]
    context_id = "test_context_123"
    
    # Первый запрос с context_id
    response1 = await agents_client.get(
        f"/agents/api/v1/embed/{embed_id}/stream",
        params={"message": "Message 1", "context_id": context_id},
        timeout=30.0
    )
    
    assert response1.status_code == 200
    events1 = _parse_sse(response1.text)
    
    # Проверяем что context_id присутствует
    context_ids = []
    for event in events1:
        result = event.get("result", {})
        if "contextId" in result:
            context_ids.append(result["contextId"])
        elif "context_id" in result:
            context_ids.append(result["context_id"])
    
    assert context_id in context_ids or any(context_id in cid for cid in context_ids)
    
    # Второй запрос с тем же context_id
    response2 = await agents_client.get(
        f"/agents/api/v1/embed/{embed_id}/stream",
        params={"message": "Message 2", "context_id": context_id},
        timeout=30.0
    )
    
    assert response2.status_code == 200
    
    # Cleanup
    await agents_client.delete(
        f"/frontend/api/embed/configs/{embed_id}",
        headers=auth_headers
    )
    
    await agents_client.delete(
        f"/agents/api/v1/agents/context_test_agent",
        headers=auth_headers
    )


@pytest.mark.asyncio
async def test_embed_stream_nonexistent_widget(agents_client: AsyncClient):
    """Тест с несуществующим виджетом"""
    
    response = await agents_client.get(
        "/agents/api/v1/embed/nonexistent_widget_123/stream",
        params={"message": "Test"}
    )
    
    assert response.status_code == 404

