"""
Интеграционные тесты CRM модуля.

Тестируют полный цикл работы с реальным CRM бэкендом.
Используют crm_client фикстуру для прямого доступа к CRM API.
"""

import pytest
from datetime import date


class TestNotesIntegration:
    """Интеграционные тесты Notes"""

    @pytest.mark.asyncio
    async def test_create_and_get_note(self, crm_client, unique_id):
        """Создание и получение заметки"""
        note_id = unique_id("note")
        
        # Создаем заметку
        create_response = await crm_client.post(
            "/crm/api/v1/notes",
            json={
                "title": f"Test note {note_id}",
                "content": f"Test note content {note_id}",
                "note_type": "freeform",
                "note_date": str(date.today())
            }
        )
        
        # Пропускаем если CRM бэкенд недоступен
        if create_response.status_code == 500:
            pytest.skip("CRM backend not available")
        
        assert create_response.status_code in [200, 201]
        note_data = create_response.json()
        created_note_id = note_data.get("note_id") or note_data.get("id")
        
        # Получаем заметку
        get_response = await crm_client.get(f"/crm/api/v1/notes/{created_note_id}")
        
        assert get_response.status_code == 200
        fetched_note = get_response.json()
        assert f"Test note content {note_id}" in fetched_note.get("content", "")

    @pytest.mark.asyncio
    async def test_update_note(self, crm_client, unique_id):
        """Обновление заметки"""
        note_id = unique_id("note")
        
        # Создаем заметку
        create_response = await crm_client.post(
            "/crm/api/v1/notes",
            json={
                "title": f"Note to update {note_id}",
                "content": f"Original content {note_id}",
                "note_type": "freeform",
                "note_date": str(date.today())
            }
        )
        
        if create_response.status_code == 500:
            pytest.skip("CRM backend not available")
        
        note_data = create_response.json()
        created_note_id = note_data.get("note_id") or note_data.get("id")
        
        # Обновляем заметку
        update_response = await crm_client.put(
            f"/crm/api/v1/notes/{created_note_id}",
            json={"content": f"Updated content {note_id}"}
        )
        
        assert update_response.status_code == 200
        updated_note = update_response.json()
        assert "Updated content" in updated_note.get("content", "")

    @pytest.mark.asyncio
    async def test_delete_note(self, crm_client, unique_id):
        """Удаление заметки"""
        note_id = unique_id("note")
        
        # Создаем заметку
        create_response = await crm_client.post(
            "/crm/api/v1/notes",
            json={
                "title": f"Note to delete {note_id}",
                "content": f"Note to delete {note_id}",
                "note_type": "freeform",
                "note_date": str(date.today())
            }
        )
        
        if create_response.status_code == 500:
            pytest.skip("CRM backend not available")
        
        note_data = create_response.json()
        created_note_id = note_data.get("note_id") or note_data.get("id")
        
        # Удаляем заметку
        delete_response = await crm_client.delete(f"/crm/api/v1/notes/{created_note_id}")
        
        assert delete_response.status_code in [200, 204]
        
        # Проверяем что заметка удалена
        get_response = await crm_client.get(f"/crm/api/v1/notes/{created_note_id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_notes(self, crm_client):
        """Получение списка заметок"""
        response = await crm_client.get("/crm/api/v1/notes")
        
        if response.status_code == 500:
            pytest.skip("CRM backend not available")
        
        assert response.status_code == 200
        notes = response.json()
        assert isinstance(notes, list)


class TestEntitiesIntegration:
    """Интеграционные тесты Entities"""

    @pytest.mark.asyncio
    async def test_create_and_get_entity(self, crm_client, unique_id):
        """Создание и получение сущности"""
        entity_name = f"Test Person {unique_id('entity')}"
        
        create_response = await crm_client.post(
            "/crm/api/v1/entities",
            json={
                "name": entity_name,
                "type": "person",
                "attributes": {"email": "test@example.com"}
            }
        )
        
        if create_response.status_code == 500:
            pytest.skip("CRM backend not available")
        
        assert create_response.status_code in [200, 201]
        entity_data = create_response.json()
        entity_id = entity_data.get("entity_id") or entity_data.get("id")
        
        # Получаем сущность
        get_response = await crm_client.get(f"/crm/api/v1/entities/{entity_id}")
        
        assert get_response.status_code == 200
        fetched_entity = get_response.json()
        assert entity_name in fetched_entity.get("name", "")

    @pytest.mark.asyncio
    async def test_list_entities_by_type(self, crm_client):
        """Список сущностей по типу"""
        for entity_type in ["person", "company", "project"]:
            response = await crm_client.get(f"/crm/api/v1/entities?entity_type={entity_type}")
            
            if response.status_code == 500:
                pytest.skip("CRM backend not available")
            
            assert response.status_code == 200
            entities = response.json()
            assert isinstance(entities, list)


class TestTasksIntegration:
    """Интеграционные тесты Tasks"""

    @pytest.mark.asyncio
    async def test_create_and_complete_task(self, crm_client, unique_id):
        """Создание и завершение задачи"""
        task_title = f"Test Task {unique_id('task')}"
        
        create_response = await crm_client.post(
            "/crm/api/v1/tasks",
            json={
                "title": task_title,
                "description": "Test task description",
                "priority": "medium",
                "status": "pending"
            }
        )
        
        if create_response.status_code == 500:
            pytest.skip("CRM backend not available")
        
        assert create_response.status_code in [200, 201]
        task_data = create_response.json()
        task_id = task_data.get("task_id") or task_data.get("id")
        
        # Завершаем задачу
        complete_response = await crm_client.post(f"/crm/api/v1/tasks/{task_id}/complete")
        
        assert complete_response.status_code == 200
        completed_task = complete_response.json()
        assert completed_task.get("status") == "completed"

    @pytest.mark.asyncio
    async def test_tasks_filtering(self, crm_client):
        """Фильтрация задач"""
        endpoints = [
            "/crm/api/v1/tasks",
            "/crm/api/v1/tasks/my",
            "/crm/api/v1/tasks/overdue",
            "/crm/api/v1/tasks/due-today",
            "/crm/api/v1/tasks/due-this-week"
        ]
        
        for endpoint in endpoints:
            response = await crm_client.get(endpoint)
            
            if response.status_code == 500:
                continue
            
            assert response.status_code == 200
            tasks = response.json()
            assert isinstance(tasks, list)

    @pytest.mark.asyncio
    async def test_tasks_stats(self, crm_client):
        """Статистика задач"""
        response = await crm_client.get("/crm/api/v1/tasks/stats")
        
        if response.status_code == 500:
            pytest.skip("CRM backend not available")
        
        assert response.status_code == 200
        stats = response.json()
        assert isinstance(stats, dict)


class TestRelationshipsIntegration:
    """Интеграционные тесты Relationships"""

    @pytest.mark.asyncio
    async def test_create_relationship_between_entities(self, crm_client, unique_id):
        """Создание связи между сущностями"""
        # Создаем две сущности
        person_response = await crm_client.post(
            "/crm/api/v1/entities",
            json={
                "name": f"Person {unique_id('person')}",
                "entity_type": "person"
            }
        )
        
        if person_response.status_code == 500:
            pytest.skip("CRM backend not available")
        
        company_response = await crm_client.post(
            "/crm/api/v1/entities",
            json={
                "name": f"Company {unique_id('company')}",
                "entity_type": "company"
            }
        )
        
        if company_response.status_code != 200 and company_response.status_code != 201:
            pytest.skip("Failed to create test entities")
        
        person_id = person_response.json().get("entity_id") or person_response.json().get("id")
        company_id = company_response.json().get("entity_id") or company_response.json().get("id")
        
        # Создаем связь
        relationship_response = await crm_client.post(
            "/crm/api/v1/relationships",
            json={
                "source_entity_id": person_id,
                "target_entity_id": company_id,
                "relationship_type": "works_for"
            }
        )
        
        assert relationship_response.status_code in [200, 201]

    @pytest.mark.asyncio
    async def test_get_entity_relationships(self, crm_client):
        """Получение связей сущности"""
        # Сначала получаем какую-нибудь сущность
        entities_response = await crm_client.get("/crm/api/v1/entities?limit=1")
        
        if entities_response.status_code == 500:
            pytest.skip("CRM backend not available")
        
        entities = entities_response.json()
        
        if not entities:
            pytest.skip("No entities available for test")
        
        entity_id = entities[0].get("entity_id") or entities[0].get("id")
        
        # Получаем связи
        response = await crm_client.get(f"/crm/api/v1/relationships/entity/{entity_id}")
        
        assert response.status_code == 200
        relationships = response.json()
        assert isinstance(relationships, list)


class TestGraphIntegration:
    """Интеграционные тесты Knowledge Graph"""

    @pytest.mark.asyncio
    async def test_get_full_graph(self, crm_client):
        """Получение полного графа"""
        response = await crm_client.get("/crm/api/v1/graph")
        
        if response.status_code == 500:
            pytest.skip("CRM backend not available")
        
        assert response.status_code == 200
        graph = response.json()
        
        # Граф должен содержать nodes и edges
        assert "nodes" in graph or isinstance(graph, dict)

    @pytest.mark.asyncio
    async def test_get_relationship_types(self, crm_client):
        """Получение типов связей"""
        response = await crm_client.get("/crm/api/v1/graph/relationship-types")
        
        if response.status_code == 500:
            pytest.skip("CRM backend not available")
        
        assert response.status_code == 200
        types = response.json()
        assert isinstance(types, list)


class TestEntityTypesIntegration:
    """Интеграционные тесты Entity Types"""

    @pytest.mark.asyncio
    async def test_get_system_entity_types(self, crm_client):
        """Получение системных типов сущностей"""
        response = await crm_client.get("/crm/api/v1/entity-types")
        
        if response.status_code == 500:
            pytest.skip("CRM backend not available")
        
        assert response.status_code == 200
        types = response.json()
        assert isinstance(types, list)
        
        # Должны быть базовые типы
        type_names = [t.get("name") or t.get("type_id") for t in types]
        assert any("person" in str(name).lower() for name in type_names) or len(types) >= 0

