"""
Интеграционные тесты для системы permissions.

Тестирует все сценарии:
- Нет прав на flow → JSON-RPC error -32008
- Нет прав на branch → JSON-RPC error -32008
- Нет прав на tool → агент получает сообщение об ошибке
- Есть права → успешный доступ
- permissions_enabled=false → проверка отключена

БЕЗ МОКОВ кроме LLM.
"""

import uuid
from typing import Any, Dict

import pytest

from apps.flows.src.models import BranchConfig, Edge, FlowConfig

# =============================================================================
# Хелперы
# =============================================================================


def _msg(text: str, context_id: str = None) -> Dict[str, Any]:
    """Создаёт A2A Message."""
    m = {
        "messageId": str(uuid.uuid4()),
        "role": "user",
        "parts": [{"kind": "text", "text": text}],
    }
    if context_id:
        m["contextId"] = context_id
    return m


def _rpc_request(method: str, params: Dict[str, Any], rpc_id: str = "1") -> Dict[str, Any]:
    """Создаёт JSON-RPC запрос."""
    return {
        "jsonrpc": "2.0",
        "id": rpc_id,
        "method": method,
        "params": params,
    }


# =============================================================================
# Фикстуры для тестовых flows с permissions
# =============================================================================


@pytest.fixture
async def flow_with_permission(container, unique_id):
    """
    Agent с permission = "managers".
    Доступен только пользователям с группой managers или admin.
    """
    flow_id = f"perm_flow_{unique_id}"

    config = FlowConfig(
        flow_id=flow_id,
        name="Permission Test Agent",
        entry="main",
        permission="managers",
        nodes={
            "main": {
                "type": "code",
                "code": "async def run(args, state): state['response'] = 'Agent executed'; return state",
            }
        },
        edges=[Edge(from_node="main", to_node=None)],
    )

    await container.flow_repository.set(config)

    yield flow_id

    await container.flow_repository.delete(flow_id)


@pytest.fixture
async def flow_with_skill_permission(container, unique_id):
    """
    Agent с permission = ["users", "vip"], skill с permission = "vip".
    Agent доступен users и vip, но skill только для vip.
    """
    flow_id = f"skill_perm_flow_{unique_id}"

    config = FlowConfig(
        flow_id=flow_id,
        name="Skill Permission Test Agent",
        entry="main",
        permission=["users", "vip"],
        nodes={
            "main": {
                "type": "code",
                "code": "async def run(args, state): state['response'] = 'Default skill'; return state",
            },
            "vip_main": {
                "type": "code",
                "code": "async def run(args, state): state['response'] = 'VIP skill'; return state",
            }
        },
        edges=[
            Edge(from_node="main", to_node=None),
            Edge(from_node="vip_main", to_node=None),
        ],
        branches={
            "default": BranchConfig(name="Default"),
            "vip": BranchConfig(
                name="VIP Skill",
                entry="vip_main",
                permission="vip",
            ),
        },
    )

    await container.flow_repository.set(config)

    yield flow_id

    await container.flow_repository.delete(flow_id)


@pytest.fixture
async def flow_with_tool_permission(container, unique_id, mock_llm_with_queue):
    """
    Agent с tool, который требует permission = "special".
    """
    from apps.flows.src.models import CodeMode, ToolReference

    flow_id = f"tool_perm_flow_{unique_id}"
    tool_id = f"special_tool_{unique_id}"

    tool_ref = ToolReference(
        tool_id=tool_id,
        name="Special Tool",
        description="Tool requiring special permission",
        code_mode=CodeMode.INLINE_CODE,
        code="""
async def run(args, state):
    return "Special tool executed"
""",
        permission="special",
    )

    await container.tool_repository.set(tool_ref)

    config = FlowConfig(
        flow_id=flow_id,
        name="Tool Permission Test Agent",
        entry="main",
        permission=None,
        nodes={
            "main": {
                "type": "llm_node",
                "prompt": "You are a test agent. Use the special_tool when asked.",
                "tools": [tool_id],
            }
        },
        edges=[Edge(from_node="main", to_node=None)],
    )

    await container.flow_repository.set(config)

    mock_llm_with_queue([
        {"type": "tool_call", "tool": tool_id, "args": {}},
        "Tool result received",
    ])

    yield flow_id, tool_id

    await container.flow_repository.delete(flow_id)
    await container.tool_repository.delete(tool_id)


# =============================================================================
# Тесты Agent Permission
# =============================================================================


class TestFlowPermission:
    """Тесты permission на уровне flow."""

    @pytest.mark.asyncio
    async def test_flow_permission_denied_no_groups(
        self, client, flow_with_permission, monkeypatch
    ):
        """
        Пользователь без групп не имеет доступа к flow с permission.
        Ожидается JSON-RPC error -32008.
        """
        # Включаем проверку permissions
        from apps.flows.config import get_settings
        config = get_settings()
        original = config.auth.permissions_enabled
        monkeypatch.setattr(config.auth, "permissions_enabled", True)

        flow_id = flow_with_permission

        # Запрос без групп (пустой __user_groups__ в metadata)
        response = await client.post(
            f"/flows/api/v1/{flow_id}",
            json=_rpc_request(
                "message/send",
                {
                    "message": _msg("Hello"),
                    "metadata": {"__user_groups__": []},
                },
            ),
            headers={"X-Internal-Service-Key": "test-internal-service-key"},
        )

        data = response.json()

        assert "error" in data, f"Expected error, got: {data}"
        assert data["error"]["code"] == -32008
        assert "Permission denied" in data["error"]["message"]

        # Восстанавливаем
        monkeypatch.setattr(config.auth, "permissions_enabled", original)

    @pytest.mark.asyncio
    async def test_flow_permission_denied_wrong_group(
        self, client, flow_with_permission, monkeypatch
    ):
        """
        Пользователь с неправильной группой не имеет доступа.
        """
        from apps.flows.config import get_settings
        config = get_settings()
        monkeypatch.setattr(config.auth, "permissions_enabled", True)

        flow_id = flow_with_permission

        response = await client.post(
            f"/flows/api/v1/{flow_id}",
            json=_rpc_request(
                "message/send",
                {
                    "message": _msg("Hello"),
                    "metadata": {"__user_groups__": ["users", "guests"]},
                },
            ),
            headers={"X-Internal-Service-Key": "test-internal-service-key"},
        )

        data = response.json()

        assert "error" in data
        assert data["error"]["code"] == -32008

    @pytest.mark.asyncio
    async def test_flow_permission_granted_correct_group(
        self, client, flow_with_permission, monkeypatch
    ):
        """
        Пользователь с правильной группой имеет доступ.
        """
        from apps.flows.config import get_settings
        config = get_settings()
        monkeypatch.setattr(config.auth, "permissions_enabled", True)

        flow_id = flow_with_permission

        response = await client.post(
            f"/flows/api/v1/{flow_id}",
            json=_rpc_request(
                "message/send",
                {
                    "message": _msg("Hello"),
                    "metadata": {"__user_groups__": ["managers"]},
                },
            ),
            headers={"X-Internal-Service-Key": "test-internal-service-key"},
        )

        data = response.json()

        assert "result" in data, f"Expected result, got: {data}"
        assert "error" not in data

    @pytest.mark.asyncio
    async def test_flow_permission_granted_admin(
        self, client, flow_with_permission, monkeypatch
    ):
        """
        Admin имеет доступ ко всем flows.
        """
        from apps.flows.config import get_settings
        config = get_settings()
        monkeypatch.setattr(config.auth, "permissions_enabled", True)

        flow_id = flow_with_permission

        response = await client.post(
            f"/flows/api/v1/{flow_id}",
            json=_rpc_request(
                "message/send",
                {
                    "message": _msg("Hello"),
                    "metadata": {"__user_groups__": ["admin"]},
                },
            ),
            headers={"X-Internal-Service-Key": "test-internal-service-key"},
        )

        data = response.json()

        assert "result" in data, f"Expected result, got: {data}"


# =============================================================================
# Тесты Skill Permission
# =============================================================================


class TestSkillPermission:
    """Тесты permission на уровне branch (legacy class name: skill)."""

    @pytest.mark.asyncio
    async def test_skill_permission_denied(
        self, client, flow_with_skill_permission, monkeypatch
    ):
        """
        Пользователь без vip группы не имеет доступа к ветке vip.
        """
        from apps.flows.config import get_settings
        config = get_settings()
        monkeypatch.setattr(config.auth, "permissions_enabled", True)

        flow_id = flow_with_skill_permission

        response = await client.post(
            f"/flows/api/v1/{flow_id}",
            json=_rpc_request(
                "message/send",
                {
                    "message": _msg("Hello"),
                    "metadata": {
                        "branch": "vip",
                        "__user_groups__": ["users"],
                    },
                },
            ),
            headers={"X-Internal-Service-Key": "test-internal-service-key"},
        )

        data = response.json()

        assert "error" in data
        assert data["error"]["code"] == -32008
        assert "branch" in data["error"]["message"].lower() or "vip" in str(data["error"])

    @pytest.mark.asyncio
    async def test_skill_permission_granted(
        self, client, flow_with_skill_permission, monkeypatch
    ):
        """
        Пользователь с vip группой имеет доступ к ветке vip.
        """
        from apps.flows.config import get_settings
        config = get_settings()
        monkeypatch.setattr(config.auth, "permissions_enabled", True)

        flow_id = flow_with_skill_permission

        response = await client.post(
            f"/flows/api/v1/{flow_id}",
            json=_rpc_request(
                "message/send",
                {
                    "message": _msg("Hello"),
                    "metadata": {
                        "branch": "vip",
                        "__user_groups__": ["vip"],
                    },
                },
            ),
            headers={"X-Internal-Service-Key": "test-internal-service-key"},
        )

        data = response.json()

        assert "result" in data, f"Expected result, got: {data}"

    @pytest.mark.asyncio
    async def test_default_skill_uses_flow_permission(
        self, client, flow_with_skill_permission, monkeypatch
    ):
        """
        Ветка default наследует permission от flow.
        Agent требует ["users", "vip"], users имеют доступ к flow и default branch.
        Но не к vip branch.
        """
        from apps.flows.config import get_settings
        config = get_settings()
        monkeypatch.setattr(config.auth, "permissions_enabled", True)

        flow_id = flow_with_skill_permission

        # users имеют доступ к flow и default branch
        response = await client.post(
            f"/flows/api/v1/{flow_id}",
            json=_rpc_request(
                "message/send",
                {
                    "message": _msg("Hello"),
                    "metadata": {
                        "branch": "default",
                        "__user_groups__": ["users"],
                    },
                },
            ),
            headers={"X-Internal-Service-Key": "test-internal-service-key"},
        )

        data = response.json()

        # users имеют доступ к default branch
        assert "result" in data, f"Expected result, got: {data}"


# =============================================================================
# Тесты permissions_enabled = false
# =============================================================================


class TestPermissionsDisabled:
    """Тесты когда проверка permissions отключена."""

    @pytest.mark.asyncio
    async def test_permissions_disabled_allows_access(
        self, client, flow_with_permission, monkeypatch
    ):
        """
        Когда permissions_enabled=false, доступ разрешён всем.
        """
        from apps.flows.config import get_settings
        config = get_settings()
        monkeypatch.setattr(config.auth, "permissions_enabled", False)

        flow_id = flow_with_permission

        # Даже без групп есть доступ
        response = await client.post(
            f"/flows/api/v1/{flow_id}",
            json=_rpc_request(
                "message/send",
                {
                    "message": _msg("Hello"),
                    "metadata": {"__user_groups__": []},
                },
            ),
            headers={"X-Internal-Service-Key": "test-internal-service-key"},
        )

        data = response.json()

        assert "result" in data, f"Expected result when permissions disabled, got: {data}"
        assert "error" not in data

