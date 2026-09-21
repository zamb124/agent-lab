"""
Integration тесты для API управления конфигурациями виджетов.

Тесты БЕЗ моков - проверяем реальные HTTP запросы.
Проверяем изоляцию по компаниям.
"""

import re
import uuid
from urllib.parse import urlparse

import pytest
import pytest_asyncio
from httpx import AsyncClient

from apps.flows.src.container import FlowContainer, get_container
from apps.flows.src.models.flow_config import FlowConfig
from apps.frontend.container import FrontendContainer
from core.context import clear_context, set_context
from core.models.context_models import Context
from core.models.identity_models import Company, User
from core.utils.tokens import get_token_service
from tests.fixtures.auth import set_test_company_member_roles

_SNIPPET_DATA_ATTRS = frozenset({
    "data-embed-id",
    "data-presentation",
    "data-position",
    "data-theme",
    "data-locale",
    "data-show-launcher",
    "data-flows-base-url",
    "data-platform-ui-origin",
    "data-token-url",
    "data-token-expires-seconds",
    "data-use-credentials",
    "data-toggle-event-name",
    "data-voice-base-url",
    "data-company-id",
})

_DEAD_DATA_ATTRS = (
    "data-assistant-title",
    "data-event-namespace",
    "data-voice-enabled",
    "data-voice-default-on",
    "data-chat-token-url",
)


def _html_data_attrs(html_code: str) -> set[str]:
    return set(re.findall(r"\bdata-[a-z0-9-]+", html_code))


async def _seed_embed_company_flow(
    frontend_container: FrontendContainer,
    *,
    company_id: str,
    user_id: str,
    flow_id: str,
    company_name: str,
    user_name: str,
) -> tuple[dict[str, str], FlowContainer, User, Company]:
    roles = ["admin"]
    user = User(
        user_id=user_id,
        name=user_name,
        emails=[f"{user_id}@test.com"],
        companies={company_id: roles},
        active_company_id=company_id,
    )
    await frontend_container.user_repository.set(user)
    company = Company(
        company_id=company_id,
        name=company_name,
        owner_user_id=user_id,
        members={user_id: roles},
    )
    await frontend_container.company_repository.set(company)
    await set_test_company_member_roles(
        frontend_container.company_repository,
        frontend_container.authz_service,
        company_id=company_id,
        user_id=user_id,
        roles=roles,
    )
    set_context(
        Context(
            user=user,
            active_company=company,
            session_id="test",
            channel="test",
        )
    )
    flows_container = get_container()
    agent = FlowConfig(
        flow_id=flow_id,
        name="Test Agent",
        entry="main",
        nodes={"main": {"type": "llm_node", "prompt": "Test", "next": None}},
    )
    await flows_container.flow_repository.set(agent)
    await flows_container.flow_access_service.sync_flow_saved(
        agent,
        company_id=company_id,
        owner_user_id=user_id,
    )
    clear_context()
    token = get_token_service().create_token(user_id, company_id=company_id, roles=roles)
    return {"Authorization": f"Bearer {token}"}, flows_container, user, company


async def _cleanup_embed_flow(
    flows_container: FlowContainer,
    *,
    user: User,
    company: Company,
    flow_id: str,
) -> None:
    set_context(
        Context(
            user=user,
            active_company=company,
            session_id="test",
            channel="test",
        )
    )
    await flows_container.flow_access_service.sync_flow_deleted(
        flow_id, company_id=company.company_id, branch_ids=[]
    )
    await flows_container.flow_repository.delete(flow_id)
    clear_context()


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
    await flows_container.flow_access_service.sync_flow_saved(
        agent,
        company_id="system",
        owner_user_id="system",
    )

    yield agent

    # Cleanup
    await flows_container.flow_access_service.sync_flow_deleted(
        "test_agent", company_id="system", branch_ids=[]
    )
    await flows_container.flow_repository.delete("test_agent")


@pytest_asyncio.fixture
async def auth_headers_other_company(frontend_container: FrontendContainer) -> dict[str, str]:
    company_id = f"other_company_{uuid.uuid4().hex[:8]}"
    user_id = f"test_user_other_{uuid.uuid4().hex[:8]}"
    roles = ["admin"]
    user = User(
        user_id=user_id,
        name="Other User",
        emails=[f"{user_id}@test.com"],
        companies={company_id: roles},
        active_company_id=company_id,
    )
    await frontend_container.user_repository.set(user)
    company = Company(
        company_id=company_id,
        name="Other Company",
        owner_user_id=user_id,
        members={user_id: roles},
    )
    await frontend_container.company_repository.set(company)
    await set_test_company_member_roles(
        frontend_container.company_repository,
        frontend_container.authz_service,
        company_id=company_id,
        user_id=user_id,
        roles=roles,
    )
    token = get_token_service().create_token(user_id, company_id=company_id, roles=roles)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def test_auth_with_agent(frontend_container: FrontendContainer):
    company_id = f"test_company_{uuid.uuid4().hex[:8]}"
    user_id = f"test_user_{uuid.uuid4().hex[:8]}"
    flow_id = "test_agent"
    headers, flows_container, user, company = await _seed_embed_company_flow(
        frontend_container,
        company_id=company_id,
        user_id=user_id,
        flow_id=flow_id,
        company_name="Test Company",
        user_name="Test User",
    )
    yield headers, flows_container, company_id
    await _cleanup_embed_flow(
        flows_container, user=user, company=company, flow_id=flow_id
    )


@pytest_asyncio.fixture
async def test_auth_with_agent_other_company(frontend_container: FrontendContainer):
    company_id = f"test_company_other_{uuid.uuid4().hex[:8]}"
    user_id = f"test_user_other_{uuid.uuid4().hex[:8]}"
    flow_id = "test_agent_other"
    headers, flows_container, user, company = await _seed_embed_company_flow(
        frontend_container,
        company_id=company_id,
        user_id=user_id,
        flow_id=flow_id,
        company_name="Other Test Company",
        user_name="Other Test User",
    )
    yield headers, flows_container, company_id
    await _cleanup_embed_flow(
        flows_container, user=user, company=company, flow_id=flow_id
    )


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
            "primary_color": "#6366f1",
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
    assert data["presentation"] == "drawer"
    assert data["theme"] == "dark"
    assert data["placeholder"] == "Type your message..."
    assert data["usage_count"] == 0
    assert data["last_used_at"] is None
    assert data["session_share_enabled"] is False
    assert "created_at" in data
    assert "created_by" in data

    embed_id = data["embed_id"]

    # Cleanup
    await frontend_client.delete(
        f"/frontend/api/embed/configs/{embed_id}",
        headers=auth_headers
    )


@pytest.mark.asyncio
async def test_create_embed_config_presentation_page(
    frontend_client: AsyncClient,
    test_auth_with_agent,
):
    auth_headers, _, _ = test_auth_with_agent
    create_response = await frontend_client.post(
        "/frontend/api/embed/configs",
        headers=auth_headers,
        json={
            "name": "Page Widget",
            "flow_id": "test_agent",
            "presentation": "page",
            "show_launcher": True,
            "position": "bottom-left",
        },
    )
    assert create_response.status_code == 200
    created = create_response.json()
    assert created["presentation"] == "page"
    assert created["show_launcher"] is True
    assert created["position"] == "bottom-left"
    embed_id = created["embed_id"]

    code_response = await frontend_client.get(
        f"/frontend/api/embed/configs/{embed_id}/code",
        headers=auth_headers,
    )
    assert code_response.status_code == 200
    code = code_response.json()
    assert code["presentation"] == "page"
    assert code["page_url"].endswith(f"/flow-embed-page?embed={embed_id}")
    assert 'data-presentation="page"' in code["html_code"]
    assert 'data-show-launcher="true"' in code["html_code"]

    await frontend_client.delete(
        f"/frontend/api/embed/configs/{embed_id}",
        headers=auth_headers,
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
            "assistant_title": "Test assistant",
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
    assert data["assistant_title"] == "Test assistant"

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
async def test_embed_config_conversation_crud(frontend_client: AsyncClient, test_auth_with_agent):
    """Настройки беседы embed: create с conversation, PATCH null сброс к flow, PATCH новыми настройками."""

    auth_headers, _, _ = test_auth_with_agent

    create_response = await frontend_client.post(
        "/frontend/api/embed/configs",
        headers=auth_headers,
        json={
            "name": "Conversation settings widget",
            "flow_id": "test_agent",
            "conversation": {"show_reasoning": True, "tool_calls": "detailed"},
        },
    )
    assert create_response.status_code == 200
    created = create_response.json()
    embed_id = created["embed_id"]
    assert created["conversation"]["show_reasoning"] is True
    assert created["conversation"]["tool_calls"] == "detailed"
    assert created["start_page_id"] is None

    patch_reset = await frontend_client.patch(
        f"/frontend/api/embed/configs/{embed_id}",
        headers=auth_headers,
        json={"conversation": None},
    )
    assert patch_reset.status_code == 200
    assert patch_reset.json()["conversation"] is None

    patch_conversation = await frontend_client.patch(
        f"/frontend/api/embed/configs/{embed_id}",
        headers=auth_headers,
        json={"conversation": {"show_files_panel": False}},
    )
    assert patch_conversation.status_code == 200
    conversation = patch_conversation.json()["conversation"]
    assert conversation["show_files_panel"] is False
    assert conversation["show_reasoning"] is False

    await frontend_client.delete(
        f"/frontend/api/embed/configs/{embed_id}",
        headers=auth_headers,
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
    assert data["script_url"].endswith("/flow-ui-embed-autoload.js")
    assert data["presentation"] == "drawer"
    assert data["page_url"].endswith(f"/flow-embed-page?embed={embed_id}")
    assert 'data-presentation="drawer"' in data["html_code"]
    assert 'data-position="bottom-right"' in data["html_code"]

    # Проверяем что в коде есть нужные элементы
    html_code = data["html_code"]
    te_parts = urlparse(data["token_endpoint"])
    apex_from_token = f"{te_parts.scheme}://{te_parts.netloc}"
    assert f'data-platform-ui-origin="{apex_from_token}"' in html_code
    assert "flow-ui-embed-autoload.js" in html_code
    assert "humanitec-embed-autoload.js" not in html_code
    assert 'type="module"' in html_code
    assert "data-embed-id=" in html_code
    assert embed_id in html_code
    assert "flow-id" not in html_code
    assert "skill-id" not in html_code
    assert '<script type="importmap">' not in html_code
    assert "@platform/lib/" not in html_code
    assert "/static/core/assets/js/lit/lit.min.js" not in html_code
    assert 'data-token-url="/api/flow-ui-token"' in html_code
    assert "data-chat-token-url" not in html_code
    assert 'data-token-expires-seconds="300"' in html_code
    assert "session-token" not in html_code
    assert "credentials: 'include'" not in html_code
    assert data["token_endpoint"].endswith(f"/frontend/api/embed/configs/{embed_id}/session-token")
    assert isinstance(data.get("allowed_origins"), list)
    assert data["allowed_origins"] == []
    prox = data["backend_proxy_code"]
    client_snip = data["browser_to_host_backend_code"]
    assert isinstance(prox, str) and prox
    assert isinstance(client_snip, str) and client_snip
    assert data["token_endpoint"] in prox
    assert embed_id in prox
    assert "session-token" in prox
    assert "await fetch(" in prox
    assert "hum_<ISSUER_TOKEN>" in prox
    assert embed_id in client_snip
    assert "expires_in_seconds:" in client_snip
    assert "fetch('/api/flow-ui-token'" in client_snip
    assert 'data-token-expires-seconds="300"' in html_code and "300" in html_code
    assert "data-voice-enabled" not in html_code
    assert "data-voice-default-on" not in html_code
    assert "data-assistant-title" not in html_code
    assert "data-event-namespace" not in html_code
    assert 'data-toggle-event-name="linnex-flow-ui-toggle"' in html_code
    assert "data-voice-base-url=" in html_code
    assert "data-company-id=" in html_code and company_id in html_code
    assert _html_data_attrs(html_code) == _SNIPPET_DATA_ATTRS
    for dead_attr in _DEAD_DATA_ATTRS:
        assert dead_attr not in html_code

    # Cleanup
    await frontend_client.delete(
        f"/frontend/api/embed/configs/{embed_id}",
        headers=auth_headers
    )


@pytest.mark.asyncio
async def test_get_embed_code_backend_snippet_reflects_allowed_origins(
    frontend_client: AsyncClient,
    test_auth_with_agent,
):
    auth_headers, _, _ = test_auth_with_agent
    origin = "https://larashved.ru"
    create_response = await frontend_client.post(
        "/frontend/api/embed/configs",
        headers=auth_headers,
        json={
            "name": "Snippet Origins Widget",
            "flow_id": "test_agent",
            "allowed_origins": [origin],
        },
    )
    assert create_response.status_code == 200
    embed_id = create_response.json()["embed_id"]
    code_response = await frontend_client.get(
        f"/frontend/api/embed/configs/{embed_id}/code",
        headers=auth_headers,
    )
    assert code_response.status_code == 200
    data = code_response.json()
    assert data["allowed_origins"] == [origin]
    assert origin in data["backend_proxy_code"]
    assert "agents:read" in data["backend_proxy_code"]

    await frontend_client.delete(f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_get_embed_code_voice_enabled_wires_assistant(frontend_client: AsyncClient, test_auth_with_agent):
    auth_headers, _, company_id = test_auth_with_agent
    create_response = await frontend_client.post(
        "/frontend/api/embed/configs",
        headers=auth_headers,
        json={
            "name": "Voice Embed Code",
            "flow_id": "test_agent",
            "voice_enabled": True,
            "voice_default_on": True,
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
    assert "data-voice-enabled" not in html_code
    assert "data-voice-default-on" not in html_code
    assert "data-voice-base-url=" in html_code
    assert company_id in html_code

    await frontend_client.delete(f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers)


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

    assert 'data-token-url="/api/flow-ui-token"' in html_code
    assert "data-chat-token-url" not in html_code
    assert "data-token-expires-seconds=" in html_code
    assert "const EMBED_ID =" not in html_code
    assert "getEmbedToken()" not in html_code

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
    assert "not found" in response.json()["detail"].lower()


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

    token_data = get_token_service().validate_token(auth_headers["Authorization"].replace("Bearer ", ""))
    assert token_data is not None
    frontend = get_frontend_container()
    await set_test_company_member_roles(
        frontend.company_repository,
        frontend.authz_service,
        company_id=token_data.company_id,
        user_id=token_data.user_id,
        roles=["admin"],
    )

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
    assert "disabled" in token_response.json()["detail"].lower()

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
    assert "data-assistant-title" not in html_code
    assert 'data-locale="ru"' in html_code
    assert 'data-theme="light"' in html_code
    assert 'data-show-launcher="false"' in html_code

    await frontend_client.delete(f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_get_embed_code_production_urls(
    frontend_client: AsyncClient,
    test_auth_with_agent,
    monkeypatch,
):
    from core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings.server, "env", "production")

    auth_headers, _, company_id = test_auth_with_agent
    create_response = await frontend_client.post(
        "/frontend/api/embed/configs",
        headers=auth_headers,
        json={
            "name": "Production URL Widget",
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
    data = response.json()
    html_code = data["html_code"]

    assert data["script_url"] == "https://cdn.humanitec.ru/lib/embed-flow-ui/flow-ui-embed-autoload.js"
    assert 'data-flows-base-url="https://api.humanitec.ru/flows"' in html_code
    assert 'data-platform-ui-origin="https://api.humanitec.ru"' in html_code
    assert 'data-voice-base-url="https://api.humanitec.ru/voice"' in html_code
    assert data["token_endpoint"].startswith("https://api.humanitec.ru/frontend/api/embed/configs/")
    assert company_id in html_code

    await frontend_client.delete(f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_create_embed_config_allowed_origins_normalized(frontend_client: AsyncClient, test_auth_with_agent):
    auth_headers, flows_container, company_id = test_auth_with_agent
    token_data = get_token_service().validate_token(
        auth_headers["Authorization"].replace("Bearer ", "")
    )
    if token_data is None:
        raise AssertionError("embed auth token is required")
    flow_id = f"test_embed_origins_{uuid.uuid4().hex[:8]}"
    user = User(
        user_id=token_data.user_id,
        name="Test",
        companies={company_id: ["admin"]},
        active_company_id=company_id,
    )
    company = Company(company_id=company_id, name="Test Company", owner_user_id=token_data.user_id)
    flow = FlowConfig(
        flow_id=flow_id,
        name="Test Embed Origins Flow",
        entry="main",
        nodes={"main": {"type": "llm_node", "prompt": "Test", "next": None}},
    )
    set_context(
        Context(
            user=user,
            active_company=company,
            session_id="test",
            channel="test",
        )
    )
    try:
        await flows_container.flow_repository.set(flow)
        await flows_container.flow_access_service.sync_flow_saved(
            flow,
            company_id=company_id,
            owner_user_id=token_data.user_id,
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

    await _cleanup_embed_flow(
        flows_container, user=user, company=company, flow_id=flow_id
    )

