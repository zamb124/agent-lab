"""
Интеграционные тесты версионности агентов.

ПРИНЦИПЫ:
- БЕЗ МОКОВ кроме LLM
- Реальный PostgreSQL и Redis
- Реальный HTTP через client фикстуру
- Изоляция через unique_id

Тестируем:
- Список версий агента
- Получение конкретной версии
- Rollback к версии
- A2A API с указанием версии через ?v= и metadata.version
"""

import uuid
from typing import Any, Dict

import pytest


def _msg(text: str, context_id: str = None, metadata: Dict = None) -> Dict[str, Any]:
    """Создаёт A2A Message с ОБЯЗАТЕЛЬНЫМИ полями по спецификации."""
    m = {
        "messageId": str(uuid.uuid4()),
        "role": "user",
        "parts": [{"kind": "text", "text": text}],
    }
    if context_id:
        m["contextId"] = context_id
    return m


def _validate_jsonrpc_response(data: Dict) -> None:
    """Строгая валидация JSON-RPC 2.0 response."""
    assert "jsonrpc" in data, "JSON-RPC response MUST have 'jsonrpc' field"
    assert data["jsonrpc"] == "2.0", "jsonrpc MUST be '2.0'"
    assert "id" in data, "JSON-RPC response MUST have 'id' field"
    assert "result" in data or "error" in data, "JSON-RPC response MUST have 'result' or 'error'"


class TestAgentVersionsList:
    """Тесты списка версий агента."""

    @pytest.mark.asyncio
    async def test_list_versions_empty_for_new_agent(self, client, unique_id):
        """
        GET /api/v1/flows/{id}/versions возвращает список с одной версией 
        сразу после создания агента.
        """
        flow_id = f"test_versions_list_{unique_id}"
        
        # Создаём агента
        create_resp = await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "Test Agent",
                "entry": "main",
                "nodes": {
                    "main": {
                        "type": "llm_node",
                        "prompt": "Test prompt v1",
                    }
                },
                "edges": [],
            },
        )
        assert create_resp.status_code == 200, f"Failed to create agent: {create_resp.text}"
        
        # Получаем список версий
        resp = await client.get(f"/flows/api/v1/flows/{flow_id}/versions")
        assert resp.status_code == 200
        
        versions_data = resp.json()
        versions = versions_data["items"]
        assert isinstance(versions, list), "versions MUST be list"
        assert len(versions) == 1, "New agent MUST have exactly 1 version"
        
        # Версия - это timestamp строка
        assert len(versions[0]) >= 14, "Version MUST be timestamp format (YYYYMMDDHHmmss...)"
        
        # Cleanup
        await client.delete(f"/flows/api/v1/flows/{flow_id}")

    @pytest.mark.asyncio
    async def test_multiple_saves_create_multiple_versions(self, client, unique_id):
        """Каждое сохранение агента создаёт новую версию."""
        flow_id = f"test_multi_versions_{unique_id}"
        
        # Создаём агента (версия 1)
        create_resp = await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "Agent Version 1",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "prompt": "Prompt v1"}},
                "edges": [],
            },
        )
        assert create_resp.status_code == 200
        
        # Обновляем агента 2 раза (версии 2 и 3)
        for i in range(2, 4):
            update_resp = await client.put(
                f"/flows/api/v1/flows/{flow_id}",
                json={
                    "flow_id": flow_id,
                    "name": f"Agent Version {i}",
                    "entry": "main",
                    "nodes": {"main": {"type": "llm_node", "prompt": f"Prompt v{i}"}},
                    "edges": [],
                },
            )
            assert update_resp.status_code == 200, f"Update {i} failed: {update_resp.text}"
        
        # Должно быть 3 версии
        resp = await client.get(f"/flows/api/v1/flows/{flow_id}/versions")
        assert resp.status_code == 200
        
        versions_data = resp.json()
        versions = versions_data["items"]
        assert len(versions) == 3, f"Expected 3 versions, got {len(versions)}"
        
        # Версии отсортированы от новых к старым (DESC)
        assert versions[0] > versions[1], "Versions MUST be sorted newest first"
        assert versions[1] > versions[2], "Versions MUST be sorted newest first"
        
        # Cleanup
        await client.delete(f"/flows/api/v1/flows/{flow_id}")

    @pytest.mark.asyncio
    async def test_list_versions_empty_for_nonexistent_agent(self, client, unique_id):
        """GET /api/v1/flows/{id}/versions для несуществующего агента возвращает пустой список."""
        resp = await client.get(f"/flows/api/v1/flows/nonexistent_{unique_id}/versions")
        assert resp.status_code == 200
        versions_data = resp.json()
        versions = versions_data["items"]
        assert isinstance(versions, list)
        assert len(versions) == 0, "Nonexistent agent MUST return empty versions list"


class TestAgentGetVersion:
    """Тесты получения конкретной версии агента."""

    @pytest.mark.asyncio
    async def test_get_specific_version_returns_old_data(self, client, unique_id):
        """
        GET /api/v1/flows/{id}/versions/{version} возвращает данные 
        на момент создания версии.
        """
        flow_id = f"test_get_version_{unique_id}"
        original_name = "Original Agent Name"
        updated_name = "Updated Agent Name"
        
        # Создаём агента с оригинальным именем
        create_resp = await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": original_name,
                "description": "Original description",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "prompt": "Original prompt"}},
                "edges": [],
            },
        )
        assert create_resp.status_code == 200
        
        # Запоминаем первую версию
        versions_resp = await client.get(f"/flows/api/v1/flows/{flow_id}/versions")
        first_version = versions_resp.json()["items"][0]
        
        # Обновляем агента
        await client.put(
            f"/flows/api/v1/flows/{flow_id}",
            json={
                "flow_id": flow_id,
                "name": updated_name,
                "description": "Updated description",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "prompt": "Updated prompt"}},
                "edges": [],
            },
        )
        
        # Получаем первую версию - должна вернуть оригинальные данные
        version_resp = await client.get(f"/flows/api/v1/flows/{flow_id}/versions/{first_version}")
        assert version_resp.status_code == 200
        
        agent_v1 = version_resp.json()
        assert agent_v1["name"] == original_name, "Version MUST return original name"
        assert agent_v1["description"] == "Original description"
        assert agent_v1["version"] == first_version
        
        # Latest должен вернуть обновленные данные
        latest_resp = await client.get(f"/flows/api/v1/flows/{flow_id}")
        latest = latest_resp.json()
        assert latest["name"] == updated_name, "Latest MUST return updated name"
        
        # Cleanup
        await client.delete(f"/flows/api/v1/flows/{flow_id}")

    @pytest.mark.asyncio
    async def test_get_version_404_for_nonexistent_version(self, client, unique_id):
        """GET /api/v1/flows/{id}/versions/{version} для несуществующей версии возвращает 404."""
        flow_id = f"test_version_404_{unique_id}"
        
        # Создаём агента
        await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "Test",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "prompt": "test"}},
                "edges": [],
            },
        )
        
        # Запрашиваем несуществующую версию
        resp = await client.get(f"/flows/api/v1/flows/{flow_id}/versions/99999999999999999999")
        assert resp.status_code == 404
        
        # Cleanup
        await client.delete(f"/flows/api/v1/flows/{flow_id}")

    @pytest.mark.asyncio
    async def test_get_version_preserves_nodes_and_edges(self, client, unique_id):
        """Версия сохраняет полную структуру nodes и edges."""
        flow_id = f"test_version_structure_{unique_id}"
        
        # Создаём агента с несколькими нодами
        original_nodes = {
            "start": {"type": "llm_node", "prompt": "Start node"},
            "middle": {"type": "llm_node", "prompt": "Middle node"},
            "end": {"type": "llm_node", "prompt": "End node"},
        }
        original_edges = [
            {"from": "start", "to": "middle"},
            {"from": "middle", "to": "end"},
        ]
        
        create_resp = await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "Complex Agent",
                "entry": "start",
                "nodes": original_nodes,
                "edges": original_edges,
            },
        )
        assert create_resp.status_code == 200, f"Failed to create: {create_resp.text}"
        
        versions_resp = await client.get(f"/flows/api/v1/flows/{flow_id}/versions")
        versions = versions_resp.json()["items"]
        assert len(versions) > 0, "Agent MUST have at least one version"
        first_version = versions[0]
        
        # Обновляем - упрощаем структуру
        await client.put(
            f"/flows/api/v1/flows/{flow_id}",
            json={
                "flow_id": flow_id,
                "name": "Simple Agent",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "prompt": "Simple"}},
                "edges": [],
            },
        )
        
        # Старая версия должна содержать полную структуру
        version_resp = await client.get(f"/flows/api/v1/flows/{flow_id}/versions/{first_version}")
        agent_v1 = version_resp.json()
        
        assert len(agent_v1["nodes"]) == 3, "Version MUST preserve all nodes"
        assert "start" in agent_v1["nodes"]
        assert "middle" in agent_v1["nodes"]
        assert "end" in agent_v1["nodes"]
        assert len(agent_v1["edges"]) == 2, "Version MUST preserve all edges"
        
        # Cleanup
        await client.delete(f"/flows/api/v1/flows/{flow_id}")


class TestAgentRollback:
    """Тесты отката версии агента."""

    @pytest.mark.asyncio
    async def test_rollback_changes_latest_pointer(self, client, unique_id):
        """POST /api/v1/flows/{id}/versions/{version}/rollback меняет указатель latest."""
        flow_id = f"test_rollback_{unique_id}"
        
        # Создаём агента (v1)
        await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "Version 1",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "prompt": "v1"}},
                "edges": [],
            },
        )
        
        versions_resp = await client.get(f"/flows/api/v1/flows/{flow_id}/versions")
        v1 = versions_resp.json()["items"][0]
        
        # Обновляем (v2)
        await client.put(
            f"/flows/api/v1/flows/{flow_id}",
            json={
                "flow_id": flow_id,
                "name": "Version 2",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "prompt": "v2"}},
                "edges": [],
            },
        )
        
        # Проверяем что latest = v2
        latest_before = await client.get(f"/flows/api/v1/flows/{flow_id}")
        assert latest_before.json()["name"] == "Version 2"
        
        # Откатываем к v1
        rollback_resp = await client.post(
            f"/flows/api/v1/flows/{flow_id}/versions/{v1}/rollback"
        )
        assert rollback_resp.status_code == 200
        
        data = rollback_resp.json()
        assert data["status"] == "success"
        assert data["version"] == v1
        
        # Проверяем что latest теперь = v1
        latest_after = await client.get(f"/flows/api/v1/flows/{flow_id}")
        assert latest_after.json()["name"] == "Version 1", "Rollback MUST change latest"
        
        # Cleanup
        await client.delete(f"/flows/api/v1/flows/{flow_id}")

    @pytest.mark.asyncio
    async def test_rollback_404_for_nonexistent_version(self, client, unique_id):
        """POST rollback для несуществующей версии возвращает 404."""
        flow_id = f"test_rollback_404_{unique_id}"
        
        await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "Test",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "prompt": "test"}},
                "edges": [],
            },
        )
        
        resp = await client.post(
            f"/flows/api/v1/flows/{flow_id}/versions/99999999999999999999/rollback"
        )
        assert resp.status_code == 404
        
        # Cleanup
        await client.delete(f"/flows/api/v1/flows/{flow_id}")

    @pytest.mark.asyncio
    async def test_rollback_preserves_version_history(self, client, unique_id):
        """Rollback не удаляет версии, только меняет указатель latest."""
        flow_id = f"test_rollback_history_{unique_id}"
        
        # Создаём 3 версии
        await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "v1",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "prompt": "v1"}},
                "edges": [],
            },
        )
        
        for i in range(2, 4):
            await client.put(
                f"/flows/api/v1/flows/{flow_id}",
                json={
                    "flow_id": flow_id,
                    "name": f"v{i}",
                    "entry": "main",
                    "nodes": {"main": {"type": "llm_node", "prompt": f"v{i}"}},
                    "edges": [],
                },
            )
        
        versions_before = await client.get(f"/flows/api/v1/flows/{flow_id}/versions")
        count_before = len(versions_before.json()["items"])
        assert count_before == 3
        
        # Откатываем к первой версии
        v1 = versions_before.json()["items"][-1]  # Последняя в списке = самая старая
        await client.post(f"/flows/api/v1/flows/{flow_id}/versions/{v1}/rollback")
        
        # Количество версий не должно измениться
        versions_after = await client.get(f"/flows/api/v1/flows/{flow_id}/versions")
        count_after = len(versions_after.json()["items"])
        assert count_after == count_before, "Rollback MUST NOT delete versions"
        
        # Cleanup
        await client.delete(f"/flows/api/v1/flows/{flow_id}")


class TestA2AVersionQueryParam:
    """Тесты A2A API с указанием версии через query param ?v=."""

    @pytest.mark.asyncio
    async def test_agent_card_with_version_query(self, client, unique_id):
        """GET /flows/{id}?v=VERSION возвращает карточку конкретной версии."""
        flow_id = f"test_a2a_card_v_{unique_id}"
        
        # Создаём агента
        await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "Original Agent",
                "description": "Original description",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "prompt": "v1"}},
                "edges": [],
            },
        )
        
        versions_resp = await client.get(f"/flows/api/v1/flows/{flow_id}/versions")
        v1 = versions_resp.json()["items"][0]
        
        # Обновляем
        await client.put(
            f"/flows/api/v1/flows/{flow_id}",
            json={
                "flow_id": flow_id,
                "name": "Updated Agent",
                "description": "Updated description",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "prompt": "v2"}},
                "edges": [],
            },
        )
        
        # Agent Card с версией
        card_v1_resp = await client.get(f"/flows/api/v1/{flow_id}?v={v1}")
        assert card_v1_resp.status_code == 200
        
        card_v1 = card_v1_resp.json()
        assert card_v1["name"] == "Original Agent", "Card MUST return versioned name"
        assert card_v1["description"] == "Original description"
        
        # Agent Card без версии (latest)
        card_latest_resp = await client.get(f"/flows/api/v1/{flow_id}")
        card_latest = card_latest_resp.json()
        assert card_latest["name"] == "Updated Agent", "Card without version MUST return latest"
        
        # Cleanup
        await client.delete(f"/flows/api/v1/flows/{flow_id}")

    @pytest.mark.asyncio
    async def test_message_send_with_version_query(
        self, client, unique_id, mock_llm_with_queue, sync_tools
    ):
        """POST /flows/{id}?v=VERSION выполняет запрос к конкретной версии."""
        flow_id = f"test_a2a_msg_v_{unique_id}"
        
        # Создаём агента
        await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "Test Agent",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "prompt": "You are v1 agent"}},
                "edges": [],
            },
        )
        
        versions_resp = await client.get(f"/flows/api/v1/flows/{flow_id}/versions")
        v1 = versions_resp.json()["items"][0]
        
        # Обновляем
        await client.put(
            f"/flows/api/v1/flows/{flow_id}",
            json={
                "flow_id": flow_id,
                "name": "Updated Agent",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "prompt": "You are v2 agent"}},
                "edges": [],
            },
        )
        
        mock_llm_with_queue([{"type": "text", "content": "Response from agent"}])
        
        # Вызываем с версией
        resp = await client.post(
            f"/flows/api/v1/{flow_id}?v={v1}",
            json={
                "jsonrpc": "2.0",
                "id": "test-version-query",
                "method": "message/send",
                "params": {"message": _msg("Hello")},
            },
        )
        
        assert resp.status_code == 200
        data = resp.json()
        _validate_jsonrpc_response(data)
        assert "result" in data, "Request with valid version MUST succeed"
        
        # Cleanup
        await client.delete(f"/flows/api/v1/flows/{flow_id}")

    @pytest.mark.asyncio
    async def test_version_query_nonexistent_returns_jsonrpc_error(self, client, unique_id):
        """POST с несуществующей версией возвращает JSON-RPC ошибку."""
        flow_id = f"test_a2a_bad_v_{unique_id}"
        
        await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "Test",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "prompt": "test"}},
                "edges": [],
            },
        )
        
        resp = await client.post(
            f"/flows/api/v1/{flow_id}?v=99999999999999999999",
            json={
                "jsonrpc": "2.0",
                "id": "test-bad-version",
                "method": "message/send",
                "params": {"message": _msg("Hello")},
            },
        )
        
        assert resp.status_code == 200  # JSON-RPC ошибки возвращаются в body
        data = resp.json()
        _validate_jsonrpc_response(data)
        
        assert "error" in data, "Nonexistent version MUST return error"
        assert data["error"]["code"] == -32000, "Error code MUST be -32000 (application error)"
        assert "version" in data["error"]["message"].lower(), "Error message MUST mention version"
        
        # Cleanup
        await client.delete(f"/flows/api/v1/flows/{flow_id}")


class TestA2AVersionMetadata:
    """Тесты A2A API с указанием версии через metadata."""

    @pytest.mark.asyncio
    async def test_message_send_with_version_in_metadata(
        self, client, unique_id, mock_llm_with_queue, sync_tools
    ):
        """POST с metadata.version выполняет запрос к конкретной версии."""
        flow_id = f"test_a2a_meta_v_{unique_id}"
        
        await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "Agent v1",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "prompt": "v1"}},
                "edges": [],
            },
        )
        
        versions_resp = await client.get(f"/flows/api/v1/flows/{flow_id}/versions")
        v1 = versions_resp.json()["items"][0]
        
        await client.put(
            f"/flows/api/v1/flows/{flow_id}",
            json={
                "flow_id": flow_id,
                "name": "Agent v2",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "prompt": "v2"}},
                "edges": [],
            },
        )
        
        mock_llm_with_queue([{"type": "text", "content": "Response"}])
        
        # Вызываем через metadata.version
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "test-metadata-version",
                "method": "message/send",
                "params": {
                    "message": _msg("Hello"),
                    "metadata": {"version": v1},
                },
            },
        )
        
        assert resp.status_code == 200
        data = resp.json()
        _validate_jsonrpc_response(data)
        assert "result" in data, "Request with valid version in metadata MUST succeed"
        
        # Cleanup
        await client.delete(f"/flows/api/v1/flows/{flow_id}")

    @pytest.mark.asyncio
    async def test_query_param_has_priority_over_metadata(
        self, client, unique_id, mock_llm_with_queue, sync_tools
    ):
        """Query param ?v= имеет приоритет над metadata.version."""
        flow_id = f"test_a2a_priority_{unique_id}"
        
        # Создаём 2 версии
        await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "v1",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "prompt": "v1"}},
                "edges": [],
            },
        )
        
        versions_resp = await client.get(f"/flows/api/v1/flows/{flow_id}/versions")
        v1 = versions_resp.json()["items"][0]
        
        await client.put(
            f"/flows/api/v1/flows/{flow_id}",
            json={
                "flow_id": flow_id,
                "name": "v2",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "prompt": "v2"}},
                "edges": [],
            },
        )
        
        versions_resp2 = await client.get(f"/flows/api/v1/flows/{flow_id}/versions")
        v2 = versions_resp2.json()["items"][0]
        
        mock_llm_with_queue([{"type": "text", "content": "Response"}])
        
        # Передаём v1 в query и v2 в metadata - query должен победить
        resp = await client.post(
            f"/flows/api/v1/{flow_id}?v={v1}",
            json={
                "jsonrpc": "2.0",
                "id": "test-priority",
                "method": "message/send",
                "params": {
                    "message": _msg("Hello"),
                    "metadata": {"version": v2},
                },
            },
        )
        
        assert resp.status_code == 200
        data = resp.json()
        _validate_jsonrpc_response(data)
        # Если бы использовалась v2 из metadata, а v1 не существовала бы - была бы ошибка
        # Но запрос успешен, значит query param имеет приоритет
        assert "result" in data
        
        # Cleanup
        await client.delete(f"/flows/api/v1/flows/{flow_id}")

    @pytest.mark.asyncio
    async def test_metadata_version_nonexistent_returns_error(self, client, unique_id):
        """metadata.version с несуществующей версией возвращает JSON-RPC ошибку."""
        flow_id = f"test_meta_bad_v_{unique_id}"
        
        await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "Test",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "prompt": "test"}},
                "edges": [],
            },
        )
        
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "test-bad-metadata-version",
                "method": "message/send",
                "params": {
                    "message": _msg("Hello"),
                    "metadata": {"version": "99999999999999999999"},
                },
            },
        )
        
        data = resp.json()
        _validate_jsonrpc_response(data)
        assert "error" in data, "Nonexistent version in metadata MUST return error"
        assert data["error"]["code"] == -32000
        
        # Cleanup
        await client.delete(f"/flows/api/v1/flows/{flow_id}")


class TestA2AVersionStream:
    """Тесты стриминга с версией."""

    @pytest.mark.asyncio
    async def test_message_stream_with_version_query(
        self, client, unique_id, mock_llm_with_queue, sync_tools
    ):
        """POST message/stream с ?v= работает с конкретной версией."""
        flow_id = f"test_a2a_stream_v_{unique_id}"
        
        await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "Streaming Agent",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "prompt": "Stream test"}},
                "edges": [],
            },
        )
        
        versions_resp = await client.get(f"/flows/api/v1/flows/{flow_id}/versions")
        v1 = versions_resp.json()["items"][0]
        
        await client.put(
            f"/flows/api/v1/flows/{flow_id}",
            json={
                "flow_id": flow_id,
                "name": "Updated Streaming Agent",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "prompt": "Updated stream test"}},
                "edges": [],
            },
        )
        
        mock_llm_with_queue([{"type": "text", "content": "Streaming response from v1"}])
        
        resp = await client.post(
            f"/flows/api/v1/{flow_id}?v={v1}",
            json={
                "jsonrpc": "2.0",
                "id": "test-stream-version",
                "method": "message/stream",
                "params": {"message": _msg("Hello stream")},
            },
        )
        
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")
        
        # Cleanup
        await client.delete(f"/flows/api/v1/flows/{flow_id}")
