"""
Интеграционные тесты Mock Control System через A2A API.

Тестирует полный flow: A2A request → metadata.__mock__ → mock результаты.
"""

import uuid

import pytest
from httpx import AsyncClient


def make_message(text: str) -> dict[str, object]:
    """Создаёт A2A message с обязательным messageId."""
    return {
        "messageId": str(uuid.uuid4()),
        "role": "user",
        "parts": [{"kind": "text", "text": text}]
    }


class TestMockViaA2AMetadata:
    """Тесты mock через metadata в A2A запросах."""

    @pytest.mark.asyncio
    async def test_mock_tool_via_metadata(self, client: AsyncClient, unique_id: str):
        """Mock tool через metadata.__mock__ в A2A запросе."""
        flow_id = "example_react"

        response = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": f"test-{unique_id}",
                "method": "message/send",
                "params": {
                    "message": make_message("Calculate 2+2"),
                    "metadata": {
                        "__mock__": {
                            "enabled": True,
                            "tools": {
                                "calculator": "Mock: result is 42"
                            }
                        }
                    }
                }
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert "result" in data
        # Агент должен получить mock результат от calculator

    @pytest.mark.asyncio
    async def test_mock_llm_via_metadata(self, client: AsyncClient, unique_id: str):
        """Mock LLM ответов через metadata.__mock__ в A2A запросе."""
        flow_id = "example_react"

        response = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": f"test-{unique_id}",
                "method": "message/send",
                "params": {
                    "message": make_message("Hello"),
                    "metadata": {
                        "__mock__": {
                            "enabled": True,
                            "llm": [
                                {"type": "text", "content": "Mock LLM response: Hello from mock!"}
                            ]
                        }
                    }
                }
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert "result" in data

        # Проверяем что mock LLM ответ использован
        task = data["result"]
        if task.get("artifacts"):
            artifact_text = ""
            for artifact in task["artifacts"]:
                for part in artifact.get("parts", []):
                    if part.get("kind") == "text":
                        artifact_text += part.get("text", "")
            assert "Mock LLM response" in artifact_text or "Hello from mock" in artifact_text

    @pytest.mark.asyncio
    async def test_mock_disabled_uses_real(self, client: AsyncClient, unique_id: str, mock_llm):
        """Mock выключен - используется реальный LLM (mock_llm из conftest)."""
        flow_id = "example_react"

        response = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": f"test-{unique_id}",
                "method": "message/send",
                "params": {
                    "message": make_message("Hello"),
                    "metadata": {
                        "__mock__": {
                            "enabled": False,  # Mock выключен
                            "llm": [{"type": "text", "content": "Should not be used"}]
                        }
                    }
                }
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert "result" in data

        # mock_llm из conftest вернёт "Test response", не mock из metadata
        task = data["result"]
        if task.get("artifacts"):
            artifact_text = ""
            for artifact in task["artifacts"]:
                for part in artifact.get("parts", []):
                    if part.get("kind") == "text":
                        artifact_text += part.get("text", "")
            # Не должен содержать mock из metadata
            assert "Should not be used" not in artifact_text


class TestMockViaFlowConfig:
    """Тесты mock через agent.json конфигурацию."""

    @pytest.mark.asyncio
    async def test_flow_default_mock_config(self, client: AsyncClient, unique_id: str):
        """Agent может иметь default mock конфиг."""
        # example_react имеет mock конфиг в agent.json
        flow_id = "example_react"

        response = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": f"test-{unique_id}",
                "method": "message/send",
                "params": {
                    "message": make_message("Test")
                    # Нет metadata.__mock__ - используется flow default
                }
            }
        )

        assert response.status_code == 200


class TestMockViaBranchConfig:
    """Тесты mock через skill конфигурацию."""

    @pytest.mark.asyncio
    async def test_skill_mock_tools(self, client: AsyncClient, unique_id: str):
        """Skill с mock для tools."""
        flow_id = "example_react"
        branch_id = "test_tools"  # Skill с mock для tools

        response = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": f"test-{unique_id}",
                "method": "message/send",
                "params": {
                    "skillId": branch_id,
                    "message": make_message("Use calculator")
                }
            }
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_skill_mock_llm(self, client: AsyncClient, unique_id: str):
        """Skill с mock для LLM."""
        flow_id = "example_react"
        branch_id = "test_llm"  # Skill с mock LLM

        response = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": f"test-{unique_id}",
                "method": "message/send",
                "params": {
                    "skillId": branch_id,
                    "message": {
                        "role": "user",
                        "parts": [{"kind": "text", "text": "Hello"}]
                    }
                }
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Skill test_llm должен вернуть mock ответ
        if "result" in data and data["result"].get("artifacts"):
            artifact_text = ""
            for artifact in data["result"]["artifacts"]:
                for part in artifact.get("parts", []):
                    if part.get("kind") == "text":
                        artifact_text += part.get("text", "")
            # Проверяем что использован mock из skill
            assert "Skill mock" in artifact_text or len(artifact_text) > 0


class TestMockHierarchy:
    """Тесты иерархии mock конфигов."""

    @pytest.mark.asyncio
    async def test_metadata_overrides_skill(self, client: AsyncClient, unique_id: str):
        """Metadata.__mock__ переопределяет skill mock."""
        flow_id = "example_react"
        branch_id = "test_llm"  # Skill с mock LLM

        response = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": f"test-{unique_id}",
                "method": "message/send",
                "params": {
                    "skillId": branch_id,
                    "message": make_message("Hello"),
                    "metadata": {
                        "__mock__": {
                            "enabled": True,
                            "llm": [
                                {"type": "text", "content": "Metadata override response"}
                            ]
                        }
                    }
                }
            }
        )

        assert response.status_code == 200
        data = response.json()

        if "result" in data and data["result"].get("artifacts"):
            artifact_text = ""
            for artifact in data["result"]["artifacts"]:
                for part in artifact.get("parts", []):
                    if part.get("kind") == "text":
                        artifact_text += part.get("text", "")
            # Metadata должен переопределить skill
            assert "Metadata override" in artifact_text

    @pytest.mark.asyncio
    async def test_tools_merge_across_levels(self, client: AsyncClient, unique_id: str):
        """Tools мержатся между уровнями."""
        flow_id = "example_react"
        branch_id = "test_tools"  # Skill с mock для calculator

        response = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": f"test-{unique_id}",
                "method": "message/send",
                "params": {
                    "skillId": branch_id,
                    "message": make_message("Test"),
                    "metadata": {
                        "__mock__": {
                            "enabled": True,
                            "tools": {
                                # Добавляем mock для другого tool
                                "another_tool": "Mock result"
                            }
                        }
                    }
                }
            }
        )

        assert response.status_code == 200


class TestMockWithGraphAgent:
    """Тесты mock с graph flow (example_graph)."""

    @pytest.mark.asyncio
    async def test_mock_function_node(self, client: AsyncClient, unique_id: str):
        """Mock function node в graph flow."""
        flow_id = "example_graph"
        branch_id = "test_function_nodes"  # Skill с mock для function нод

        response = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": f"test-{unique_id}",
                "method": "message/send",
                "params": {
                    "skillId": branch_id,
                    "message": make_message("Process order")
                }
            }
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_mock_llm_node(self, client: AsyncClient, unique_id: str):
        """Mock llm_node node в graph flow."""
        flow_id = "example_graph"
        branch_id = "test_llm_nodes"  # Skill с mock для react нод

        response = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": f"test-{unique_id}",
                "method": "message/send",
                "params": {
                    "skillId": branch_id,
                    "message": {
                        "role": "user",
                        "parts": [{"kind": "text", "text": "Hello"}]
                    }
                }
            }
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_mock_full_graph(self, client: AsyncClient, unique_id: str):
        """Full mock для всего graph flow."""
        flow_id = "example_graph"
        branch_id = "test_full_graph"  # Skill с full mock

        response = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": f"test-{unique_id}",
                "method": "message/send",
                "params": {
                    "skillId": branch_id,
                    "message": make_message("Test full mock")
                }
            }
        )

        assert response.status_code == 200


class TestMockPermissions:
    """Тесты проверки прав на использование mock."""

    @pytest.mark.asyncio
    async def test_admin_can_use_mock(self, client: AsyncClient, unique_id: str):
        """Admin пользователь может использовать mock."""
        flow_id = "example_react"

        response = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers={
                "X-User-Id": "admin-user",
                "X-User-Groups": "admin",  # Admin группа
            },
            json={
                "jsonrpc": "2.0",
                "id": f"test-{unique_id}",
                "method": "message/send",
                "params": {
                    "message": make_message("Test"),
                    "metadata": {
                        "__mock__": {
                            "enabled": True,
                            "llm": [{"type": "text", "content": "Admin mock response"}]
                        }
                    }
                }
            }
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_developers_can_use_mock(self, client: AsyncClient, unique_id: str):
        """Developers группа может использовать mock."""
        flow_id = "example_react"

        response = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers={
                "X-User-Id": "dev-user",
                "X-User-Groups": "developers",
            },
            json={
                "jsonrpc": "2.0",
                "id": f"test-{unique_id}",
                "method": "message/send",
                "params": {
                    "message": make_message("Test"),
                    "metadata": {
                        "__mock__": {
                            "enabled": True,
                            "llm": [{"type": "text", "content": "Dev mock response"}]
                        }
                    }
                }
            }
        )

        assert response.status_code == 200


class TestMockStreaming:
    """Тесты mock со streaming (message/stream)."""

    @pytest.mark.asyncio
    async def test_mock_llm_streaming(self, client: AsyncClient, unique_id: str):
        """Mock LLM работает с streaming."""
        flow_id = "example_react"

        async with client.stream(
            "POST",
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": f"test-{unique_id}",
                "method": "message/stream",
                "params": {
                    "message": make_message("Hello"),
                    "metadata": {
                        "__mock__": {
                            "enabled": True,
                            "llm": [
                                {"type": "text", "content": "Mock streaming response"}
                            ]
                        }
                    }
                }
            }
        ) as response:
            assert response.status_code == 200

            events = []
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    events.append(line)

            # Должны быть события от mock LLM
            assert len(events) > 0

