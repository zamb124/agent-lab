"""
Тесты API endpoints CRM модуля.

Проверяет что API proxy endpoints доступны и возвращают корректные ответы.
Поскольку это proxy к CRM бэкенду, тесты проверяют наличие endpoints.

Для полных интеграционных тестов нужен запущенный CRM сервис.
"""

import pytest


class TestCRMNotesAPI:
    """Тесты Notes API endpoints"""

    @pytest.mark.asyncio
    async def test_list_notes_endpoint_exists(self, frontend_client):
        """Endpoint списка заметок существует"""
        response = await frontend_client.get("/frontend/api/crm/notes")
        
        # Может вернуть ошибку подключения к бэкенду, но не 404
        assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_get_note_endpoint_exists(self, frontend_client, unique_id):
        """Endpoint получения заметки существует"""
        note_id = unique_id("note")
        response = await frontend_client.get(f"/frontend/api/crm/notes/{note_id}")
        
        assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_create_note_endpoint_exists(self, frontend_client, unique_id):
        """Endpoint создания заметки существует"""
        note_content = f"Test note {unique_id('content')}"
        response = await frontend_client.post(
            "/frontend/api/crm/notes",
            json={"content": note_content, "note_type": "freeform"}
        )
        
        assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_update_note_endpoint_exists(self, frontend_client, unique_id):
        """Endpoint обновления заметки существует"""
        note_id = unique_id("note")
        response = await frontend_client.put(
            f"/frontend/api/crm/notes/{note_id}",
            json={"content": f"Updated note {unique_id('content')}"}
        )
        
        assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_delete_note_endpoint_exists(self, frontend_client, unique_id):
        """Endpoint удаления заметки существует"""
        note_id = unique_id("note")
        response = await frontend_client.delete(f"/frontend/api/crm/notes/{note_id}")
        
        assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_analyze_note_endpoint_exists(self, frontend_client, unique_id):
        """Endpoint AI анализа заметки существует"""
        note_id = unique_id("note")
        response = await frontend_client.post(f"/frontend/api/crm/notes/{note_id}/analyze")
        
        assert response.status_code != 404


class TestCRMEntitiesAPI:
    """Тесты Entities API endpoints"""

    @pytest.mark.asyncio
    async def test_list_entities_endpoint_exists(self, frontend_client):
        """Endpoint списка сущностей существует"""
        response = await frontend_client.get("/frontend/api/crm/entities")
        
        assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_list_entities_with_type_filter(self, frontend_client):
        """Endpoint списка сущностей с фильтром по типу"""
        for entity_type in ["person", "company", "project"]:
            response = await frontend_client.get(f"/frontend/api/crm/entities?entity_type={entity_type}")
            
            assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_get_entity_endpoint_exists(self, frontend_client, unique_id):
        """Endpoint получения сущности существует"""
        entity_id = unique_id("entity")
        response = await frontend_client.get(f"/frontend/api/crm/entities/{entity_id}")
        
        assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_create_entity_endpoint_exists(self, frontend_client, unique_id):
        """Endpoint создания сущности существует"""
        entity_name = f"Test Entity {unique_id('entity')}"
        response = await frontend_client.post(
            "/frontend/api/crm/entities",
            json={"name": entity_name, "entity_type": "person"}
        )
        
        assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_update_entity_endpoint_exists(self, frontend_client, unique_id):
        """Endpoint обновления сущности существует"""
        entity_id = unique_id("entity")
        response = await frontend_client.put(
            f"/frontend/api/crm/entities/{entity_id}",
            json={"name": f"Updated Entity {unique_id('name')}"}
        )
        
        assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_delete_entity_endpoint_exists(self, frontend_client, unique_id):
        """Endpoint удаления сущности существует"""
        entity_id = unique_id("entity")
        response = await frontend_client.delete(f"/frontend/api/crm/entities/{entity_id}")
        
        assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_search_entities_endpoint_exists(self, frontend_client, unique_id):
        """Endpoint семантического поиска существует"""
        search_query = f"test search {unique_id('query')}"
        response = await frontend_client.post(
            "/frontend/api/crm/entities/search",
            json={"query": search_query}
        )
        
        assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_find_duplicates_endpoint_exists(self, frontend_client, unique_id):
        """Endpoint поиска дубликатов существует"""
        entity_id = unique_id("entity")
        response = await frontend_client.get(f"/frontend/api/crm/entities/{entity_id}/duplicates")
        
        assert response.status_code != 404


class TestCRMEntityTypesAPI:
    """Тесты Entity Types API endpoints"""

    @pytest.mark.asyncio
    async def test_list_entity_types_endpoint_exists(self, frontend_client):
        """Endpoint списка типов сущностей существует"""
        response = await frontend_client.get("/frontend/api/crm/entity-types")
        
        assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_get_entity_type_endpoint_exists(self, frontend_client, unique_id):
        """Endpoint получения типа сущности существует"""
        type_id = unique_id("type")
        response = await frontend_client.get(f"/frontend/api/crm/entity-types/{type_id}")
        
        assert response.status_code != 404


class TestCRMRelationshipsAPI:
    """Тесты Relationships API endpoints"""

    @pytest.mark.asyncio
    async def test_list_relationships_endpoint_exists(self, frontend_client):
        """Endpoint списка связей существует"""
        response = await frontend_client.get("/frontend/api/crm/relationships")
        
        assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_get_entity_relationships_endpoint_exists(self, frontend_client, unique_id):
        """Endpoint связей сущности существует"""
        entity_id = unique_id("entity")
        response = await frontend_client.get(f"/frontend/api/crm/relationships/entity/{entity_id}")
        
        assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_create_relationship_endpoint_exists(self, frontend_client, unique_id):
        """Endpoint создания связи существует"""
        source_id = unique_id("entity")
        target_id = unique_id("entity")
        response = await frontend_client.post(
            "/frontend/api/crm/relationships",
            json={
                "source_entity_id": source_id,
                "target_entity_id": target_id,
                "relationship_type": "works_for"
            }
        )
        
        assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_delete_relationship_endpoint_exists(self, frontend_client, unique_id):
        """Endpoint удаления связи существует"""
        relationship_id = unique_id("relationship")
        response = await frontend_client.delete(f"/frontend/api/crm/relationships/{relationship_id}")
        
        assert response.status_code != 404


class TestCRMTasksAPI:
    """Тесты Tasks API endpoints"""

    @pytest.mark.asyncio
    async def test_list_tasks_endpoint_exists(self, frontend_client):
        """Endpoint списка задач существует"""
        response = await frontend_client.get("/frontend/api/crm/tasks")
        
        assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_my_tasks_endpoint_exists(self, frontend_client):
        """Endpoint моих задач существует"""
        response = await frontend_client.get("/frontend/api/crm/tasks/my")
        
        assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_overdue_tasks_endpoint_exists(self, frontend_client):
        """Endpoint просроченных задач существует"""
        response = await frontend_client.get("/frontend/api/crm/tasks/overdue")
        
        assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_today_tasks_endpoint_exists(self, frontend_client):
        """Endpoint задач на сегодня существует"""
        response = await frontend_client.get("/frontend/api/crm/tasks/today")
        
        assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_week_tasks_endpoint_exists(self, frontend_client):
        """Endpoint задач на неделю существует"""
        response = await frontend_client.get("/frontend/api/crm/tasks/week")
        
        assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_tasks_stats_endpoint_exists(self, frontend_client):
        """Endpoint статистики задач существует"""
        response = await frontend_client.get("/frontend/api/crm/tasks/stats")
        
        assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_get_task_endpoint_exists(self, frontend_client, unique_id):
        """Endpoint получения задачи существует"""
        task_id = unique_id("task")
        response = await frontend_client.get(f"/frontend/api/crm/tasks/{task_id}")
        
        assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_create_task_endpoint_exists(self, frontend_client, unique_id):
        """Endpoint создания задачи существует"""
        task_title = f"Test Task {unique_id('task')}"
        response = await frontend_client.post(
            "/frontend/api/crm/tasks",
            json={"title": task_title, "priority": "medium"}
        )
        
        assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_update_task_endpoint_exists(self, frontend_client, unique_id):
        """Endpoint обновления задачи существует"""
        task_id = unique_id("task")
        response = await frontend_client.put(
            f"/frontend/api/crm/tasks/{task_id}",
            json={"title": f"Updated Task {unique_id('title')}"}
        )
        
        assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_complete_task_endpoint_exists(self, frontend_client, unique_id):
        """Endpoint завершения задачи существует"""
        task_id = unique_id("task")
        response = await frontend_client.post(f"/frontend/api/crm/tasks/{task_id}/complete")
        
        assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_delete_task_endpoint_exists(self, frontend_client, unique_id):
        """Endpoint удаления задачи существует"""
        task_id = unique_id("task")
        response = await frontend_client.delete(f"/frontend/api/crm/tasks/{task_id}")
        
        assert response.status_code != 404


class TestCRMGraphAPI:
    """Тесты Knowledge Graph API endpoints"""

    @pytest.mark.asyncio
    async def test_get_graph_endpoint_exists(self, frontend_client):
        """Endpoint получения графа существует"""
        response = await frontend_client.get("/frontend/api/crm/graph")
        
        assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_get_entity_graph_endpoint_exists(self, frontend_client, unique_id):
        """Endpoint графа сущности существует"""
        entity_id = unique_id("entity")
        response = await frontend_client.get(f"/frontend/api/crm/graph/entity/{entity_id}")
        
        assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_get_relationship_types_endpoint_exists(self, frontend_client):
        """Endpoint типов связей существует"""
        response = await frontend_client.get("/frontend/api/crm/graph/relationship-types")
        
        assert response.status_code != 404


class TestCRMAPIResponseFormat:
    """Тесты формата ответов API"""

    @pytest.mark.asyncio
    async def test_api_returns_json(self, frontend_client):
        """API возвращает JSON"""
        response = await frontend_client.get("/frontend/api/crm/notes")
        
        content_type = response.headers.get("content-type", "")
        # Если бэкенд недоступен - все равно ответ будет JSON с ошибкой
        assert "application/json" in content_type

    @pytest.mark.asyncio
    async def test_api_error_format(self, frontend_client):
        """Ошибки API возвращаются в правильном формате"""
        # Несуществующий endpoint внутри CRM API
        response = await frontend_client.get("/frontend/api/crm/nonexistent")
        
        # 404 от FastAPI
        assert response.status_code == 404

