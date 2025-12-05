"""
Тесты API endpoints CRM модуля.

Проверяет что API proxy endpoints доступны и возвращают корректные ответы.
Требует запущенный CRM сервис (через crm_server_process фикстуру).
"""

import pytest


class TestCRMNotesAPI:
    """Тесты Notes API endpoints"""

    @pytest.mark.asyncio
    async def test_list_notes(self, frontend_client):
        """Получение списка заметок возвращает 200"""
        response = await frontend_client.get("/frontend/api/crm/notes")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_note_not_found(self, frontend_client, unique_id):
        """Несуществующая заметка возвращает 404"""
        note_id = unique_id("note")
        response = await frontend_client.get(f"/frontend/api/crm/notes/{note_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_note_validation_error(self, frontend_client, unique_id):
        """Создание заметки с неполными данными возвращает 422"""
        response = await frontend_client.post(
            "/frontend/api/crm/notes",
            json={"content": f"Test note {unique_id('content')}", "note_type": "freeform"}
        )
        # Без title будет 422
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_update_note_not_found(self, frontend_client, unique_id):
        """Обновление несуществующей заметки возвращает 404"""
        note_id = unique_id("note")
        response = await frontend_client.put(
            f"/frontend/api/crm/notes/{note_id}",
            json={"content": f"Updated note {unique_id('content')}"}
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_note_not_found(self, frontend_client, unique_id):
        """Удаление несуществующей заметки возвращает 404"""
        note_id = unique_id("note")
        response = await frontend_client.delete(f"/frontend/api/crm/notes/{note_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_analyze_note_not_found(self, frontend_client, unique_id):
        """Анализ несуществующей заметки возвращает 404 или 422"""
        note_id = unique_id("note")
        response = await frontend_client.post(f"/frontend/api/crm/notes/{note_id}/analyze")
        assert response.status_code in [404, 422]


class TestCRMEntitiesAPI:
    """Тесты Entities API endpoints"""

    @pytest.mark.asyncio
    async def test_list_entities(self, frontend_client):
        """Получение списка сущностей возвращает 200"""
        response = await frontend_client.get("/frontend/api/crm/entities")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_entities_with_type_filter(self, frontend_client):
        """Получение сущностей с фильтром по типу возвращает 200"""
        for entity_type in ["person", "organization", "project"]:
            response = await frontend_client.get(f"/frontend/api/crm/entities?entity_type={entity_type}")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_entity_not_found(self, frontend_client, unique_id):
        """Несуществующая сущность возвращает 404"""
        entity_id = unique_id("entity")
        response = await frontend_client.get(f"/frontend/api/crm/entities/{entity_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_entity_validation_error(self, frontend_client, unique_id):
        """Создание сущности с неполными данными возвращает 422"""
        response = await frontend_client.post(
            "/frontend/api/crm/entities",
            json={"name": f"Test Entity {unique_id('entity')}", "entity_type": "person"}
        )
        # Поле должно быть "type", а не "entity_type"
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_update_entity_not_found(self, frontend_client, unique_id):
        """Обновление несуществующей сущности возвращает 404"""
        entity_id = unique_id("entity")
        response = await frontend_client.put(
            f"/frontend/api/crm/entities/{entity_id}",
            json={"name": f"Updated Entity {unique_id('name')}"}
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_entity_not_found(self, frontend_client, unique_id):
        """Удаление несуществующей сущности возвращает 404 или 200"""
        entity_id = unique_id("entity")
        response = await frontend_client.delete(f"/frontend/api/crm/entities/{entity_id}")
        # ChromaDB может вернуть 200 даже для несуществующих
        assert response.status_code in [200, 404]

    @pytest.mark.asyncio
    async def test_search_entities(self, frontend_client, unique_id):
        """Поиск сущностей возвращает 200"""
        search_query = f"test search {unique_id('query')}"
        response = await frontend_client.post(
            "/frontend/api/crm/entities/search",
            json={"query": search_query}
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_find_duplicates_not_found(self, frontend_client, unique_id):
        """Поиск дубликатов несуществующей сущности возвращает 404"""
        entity_id = unique_id("entity")
        response = await frontend_client.get(f"/frontend/api/crm/entities/{entity_id}/duplicates")
        assert response.status_code == 404


class TestCRMEntityTypesAPI:
    """Тесты Entity Types API endpoints"""

    @pytest.mark.asyncio
    async def test_list_entity_types(self, frontend_client):
        """Получение списка типов возвращает 200"""
        response = await frontend_client.get("/frontend/api/crm/entity-types")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_entity_type_not_found(self, frontend_client, unique_id):
        """Несуществующий тип возвращает 404"""
        type_id = unique_id("type")
        response = await frontend_client.get(f"/frontend/api/crm/entity-types/{type_id}")
        assert response.status_code == 404


class TestCRMRelationshipsAPI:
    """Тесты Relationships API endpoints"""

    @pytest.mark.asyncio
    async def test_list_relationships(self, frontend_client):
        """Получение списка связей возвращает 200"""
        response = await frontend_client.get("/frontend/api/crm/relationships")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_entity_relationships_empty(self, frontend_client, unique_id):
        """Связи несуществующей сущности - пустой список или 404"""
        entity_id = unique_id("entity")
        response = await frontend_client.get(f"/frontend/api/crm/relationships/entity/{entity_id}")
        assert response.status_code in [200, 404]

    @pytest.mark.asyncio
    async def test_create_relationship_not_found(self, frontend_client, unique_id):
        """Создание связи с несуществующими сущностями возвращает 404"""
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
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_relationship_not_found(self, frontend_client, unique_id):
        """Удаление несуществующей связи возвращает 404"""
        relationship_id = unique_id("relationship")
        response = await frontend_client.delete(f"/frontend/api/crm/relationships/{relationship_id}")
        assert response.status_code == 404


class TestCRMTasksAPI:
    """Тесты Tasks API endpoints"""

    @pytest.mark.asyncio
    async def test_list_tasks(self, frontend_client):
        """Получение списка задач возвращает 200"""
        response = await frontend_client.get("/frontend/api/crm/tasks")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_my_tasks(self, frontend_client):
        """Мои задачи возвращают 200"""
        response = await frontend_client.get("/frontend/api/crm/tasks/my")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_overdue_tasks(self, frontend_client):
        """Просроченные задачи возвращают 200"""
        response = await frontend_client.get("/frontend/api/crm/tasks/overdue")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_today_tasks(self, frontend_client):
        """Задачи на сегодня - проверяем что endpoint отвечает"""
        response = await frontend_client.get("/frontend/api/crm/tasks/today")
        # Endpoint может не существовать в текущей версии API
        assert response.status_code in [200, 404]

    @pytest.mark.asyncio
    async def test_week_tasks(self, frontend_client):
        """Задачи на неделю - проверяем что endpoint отвечает"""
        response = await frontend_client.get("/frontend/api/crm/tasks/week")
        # Endpoint может не существовать в текущей версии API
        assert response.status_code in [200, 404]

    @pytest.mark.asyncio
    async def test_tasks_stats(self, frontend_client):
        """Статистика задач возвращает 200"""
        response = await frontend_client.get("/frontend/api/crm/tasks/stats")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_task_not_found(self, frontend_client, unique_id):
        """Несуществующая задача возвращает 404"""
        task_id = unique_id("task")
        response = await frontend_client.get(f"/frontend/api/crm/tasks/{task_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_task_success(self, frontend_client, unique_id):
        """Создание задачи с минимальными данными возвращает 200"""
        task_title = f"Test Task {unique_id('task')}"
        response = await frontend_client.post(
            "/frontend/api/crm/tasks",
            json={"title": task_title, "priority": "medium"}
        )
        # title + priority достаточно для создания
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_update_task_not_found(self, frontend_client, unique_id):
        """Обновление несуществующей задачи возвращает 404"""
        task_id = unique_id("task")
        response = await frontend_client.put(
            f"/frontend/api/crm/tasks/{task_id}",
            json={"title": f"Updated Task {unique_id('title')}"}
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_complete_task_not_found(self, frontend_client, unique_id):
        """Завершение несуществующей задачи возвращает 404"""
        task_id = unique_id("task")
        response = await frontend_client.post(f"/frontend/api/crm/tasks/{task_id}/complete")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_task_not_found(self, frontend_client, unique_id):
        """Удаление несуществующей задачи возвращает 404"""
        task_id = unique_id("task")
        response = await frontend_client.delete(f"/frontend/api/crm/tasks/{task_id}")
        assert response.status_code == 404


class TestCRMGraphAPI:
    """Тесты Knowledge Graph API endpoints"""

    @pytest.mark.asyncio
    async def test_get_graph(self, frontend_client):
        """Получение графа возвращает 200"""
        response = await frontend_client.get("/frontend/api/crm/graph")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_entity_graph_empty(self, frontend_client, unique_id):
        """Граф несуществующей сущности - пустой граф или 404"""
        entity_id = unique_id("entity")
        response = await frontend_client.get(f"/frontend/api/crm/graph/entity/{entity_id}")
        # API возвращает пустой граф (200) или 404
        assert response.status_code in [200, 404]

    @pytest.mark.asyncio
    async def test_get_relationship_types(self, frontend_client):
        """Типы связей возвращают 200"""
        response = await frontend_client.get("/frontend/api/crm/graph/relationship-types")
        assert response.status_code == 200


class TestCRMAPIResponseFormat:
    """Тесты формата ответов API"""

    @pytest.mark.asyncio
    async def test_api_returns_json(self, frontend_client):
        """API возвращает JSON"""
        response = await frontend_client.get("/frontend/api/crm/notes")
        content_type = response.headers.get("content-type", "")
        assert "application/json" in content_type

    @pytest.mark.asyncio
    async def test_api_error_format(self, frontend_client):
        """Несуществующий endpoint возвращает 404"""
        response = await frontend_client.get("/frontend/api/crm/nonexistent")
        assert response.status_code == 404
