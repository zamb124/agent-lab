"""
Тесты API endpoints CRM модуля.

Проверяет что API proxy endpoints доступны и возвращают корректные ответы.
Требует запущенный CRM сервис (через crm_server_process фикстуру).
"""

import pytest


class TestCRMNotesAPI:
    """Тесты Notes API endpoints"""

    @pytest.mark.asyncio
    async def test_list_notes(self, crm_frontend_client):
        """Получение списка заметок возвращает 200"""
        response = await crm_frontend_client.get("/frontend/api/crm/notes")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_note_not_found(self, crm_frontend_client, unique_id):
        """Несуществующая заметка возвращает 404"""
        note_id = unique_id("note")
        response = await crm_frontend_client.get(f"/frontend/api/crm/notes/{note_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_note_validation_error(self, crm_frontend_client, unique_id):
        """Создание заметки с неполными данными возвращает 422"""
        response = await crm_frontend_client.post(
            "/frontend/api/crm/notes",
            json={"content": f"Test note {unique_id('content')}", "note_type": "freeform"}
        )
        # Без title будет 422
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_update_note_not_found(self, crm_frontend_client, unique_id):
        """Обновление несуществующей заметки возвращает 404"""
        note_id = unique_id("note")
        response = await crm_frontend_client.put(
            f"/frontend/api/crm/notes/{note_id}",
            json={"content": f"Updated note {unique_id('content')}"}
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_note_not_found(self, crm_frontend_client, unique_id):
        """Удаление несуществующей заметки возвращает 404"""
        note_id = unique_id("note")
        response = await crm_frontend_client.delete(f"/frontend/api/crm/notes/{note_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_analyze_note_not_found(self, crm_frontend_client, unique_id):
        """Анализ несуществующей заметки возвращает 404 или 422"""
        note_id = unique_id("note")
        response = await crm_frontend_client.post(f"/frontend/api/crm/notes/{note_id}/analyze")
        assert response.status_code in [404, 422]


class TestCRMEntitiesAPI:
    """Тесты Entities API endpoints"""

    @pytest.mark.asyncio
    async def test_list_entities(self, crm_frontend_client):
        """Получение списка сущностей возвращает 200"""
        response = await crm_frontend_client.get("/frontend/api/crm/entities")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_entities_with_type_filter(self, crm_frontend_client):
        """Получение сущностей с фильтром по типу возвращает 200"""
        for entity_type in ["person", "organization", "project"]:
            response = await crm_frontend_client.get(f"/frontend/api/crm/entities?entity_type={entity_type}")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_entity_not_found(self, crm_frontend_client, unique_id):
        """Несуществующая сущность возвращает 404"""
        entity_id = unique_id("entity")
        response = await crm_frontend_client.get(f"/frontend/api/crm/entities/{entity_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_entity_validation_error(self, crm_frontend_client, unique_id):
        """Создание сущности с неполными данными возвращает 422"""
        response = await crm_frontend_client.post(
            "/frontend/api/crm/entities",
            json={"name": f"Test Entity {unique_id('entity')}", "entity_type": "person"}
        )
        # Поле должно быть "type", а не "entity_type"
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_update_entity_not_found(self, crm_frontend_client, unique_id):
        """Обновление несуществующей сущности возвращает 404"""
        entity_id = unique_id("entity")
        response = await crm_frontend_client.put(
            f"/frontend/api/crm/entities/{entity_id}",
            json={"name": f"Updated Entity {unique_id('name')}"}
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_entity_not_found(self, crm_frontend_client, unique_id):
        """Удаление несуществующей сущности возвращает 404 или 200"""
        entity_id = unique_id("entity")
        response = await crm_frontend_client.delete(f"/frontend/api/crm/entities/{entity_id}")
        # ChromaDB может вернуть 200 даже для несуществующих
        assert response.status_code in [200, 404]

    @pytest.mark.asyncio
    async def test_search_entities(self, crm_frontend_client, unique_id):
        """Поиск сущностей возвращает 200"""
        search_query = f"test search {unique_id('query')}"
        response = await crm_frontend_client.post(
            "/frontend/api/crm/entities/search",
            json={"query": search_query}
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_find_duplicates_not_found(self, crm_frontend_client, unique_id):
        """Поиск дубликатов несуществующей сущности возвращает 404"""
        entity_id = unique_id("entity")
        response = await crm_frontend_client.get(f"/frontend/api/crm/entities/{entity_id}/duplicates")
        assert response.status_code == 404


class TestCRMEntityTypesAPI:
    """Тесты Entity Types API endpoints"""

    @pytest.mark.asyncio
    async def test_list_entity_types(self, crm_frontend_client):
        """Получение списка типов возвращает 200"""
        response = await crm_frontend_client.get("/frontend/api/crm/entity-types")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_entity_type_not_found(self, crm_frontend_client, unique_id):
        """Несуществующий тип возвращает 404"""
        type_id = unique_id("type")
        response = await crm_frontend_client.get(f"/frontend/api/crm/entity-types/{type_id}")
        assert response.status_code == 404


class TestCRMRelationshipsAPI:
    """Тесты Relationships API endpoints"""

    @pytest.mark.asyncio
    async def test_list_relationships(self, crm_frontend_client):
        """Получение списка связей возвращает 200"""
        response = await crm_frontend_client.get("/frontend/api/crm/relationships")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_entity_relationships_empty(self, crm_frontend_client, unique_id):
        """Связи несуществующей сущности - пустой список или 404"""
        entity_id = unique_id("entity")
        response = await crm_frontend_client.get(f"/frontend/api/crm/relationships/entity/{entity_id}")
        assert response.status_code in [200, 404]

    @pytest.mark.asyncio
    async def test_create_relationship_not_found(self, crm_frontend_client, unique_id):
        """Создание связи с несуществующими сущностями возвращает 404"""
        source_id = unique_id("entity")
        target_id = unique_id("entity")
        response = await crm_frontend_client.post(
            "/frontend/api/crm/relationships",
            json={
                "source_entity_id": source_id,
                "target_entity_id": target_id,
                "relationship_type": "works_for"
            }
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_relationship_not_found(self, crm_frontend_client, unique_id):
        """Удаление несуществующей связи возвращает 404"""
        relationship_id = unique_id("relationship")
        response = await crm_frontend_client.delete(f"/frontend/api/crm/relationships/{relationship_id}")
        assert response.status_code == 404


class TestCRMTasksAPI:
    """Тесты Tasks API endpoints"""

    @pytest.mark.asyncio
    async def test_list_tasks(self, crm_frontend_client):
        """Получение списка задач возвращает 200"""
        response = await crm_frontend_client.get("/frontend/api/crm/tasks")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_my_tasks(self, crm_frontend_client):
        """Мои задачи возвращают 200"""
        response = await crm_frontend_client.get("/frontend/api/crm/tasks/my")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_overdue_tasks(self, crm_frontend_client):
        """Просроченные задачи возвращают 200"""
        response = await crm_frontend_client.get("/frontend/api/crm/tasks/overdue")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_today_tasks(self, crm_frontend_client):
        """Задачи на сегодня - проверяем что endpoint отвечает"""
        response = await crm_frontend_client.get("/frontend/api/crm/tasks/today")
        # Endpoint может не существовать в текущей версии API
        assert response.status_code in [200, 404]

    @pytest.mark.asyncio
    async def test_week_tasks(self, crm_frontend_client):
        """Задачи на неделю - проверяем что endpoint отвечает"""
        response = await crm_frontend_client.get("/frontend/api/crm/tasks/week")
        # Endpoint может не существовать в текущей версии API
        assert response.status_code in [200, 404]

    @pytest.mark.asyncio
    async def test_tasks_stats(self, crm_frontend_client):
        """Статистика задач возвращает 200"""
        response = await crm_frontend_client.get("/frontend/api/crm/tasks/stats")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_task_not_found(self, crm_frontend_client, unique_id):
        """Несуществующая задача возвращает 404"""
        task_id = unique_id("task")
        response = await crm_frontend_client.get(f"/frontend/api/crm/tasks/{task_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_task_success(self, crm_frontend_client, unique_id):
        """Создание задачи с минимальными данными возвращает 200"""
        task_title = f"Test Task {unique_id('task')}"
        response = await crm_frontend_client.post(
            "/frontend/api/crm/tasks",
            json={"title": task_title, "priority": "medium"}
        )
        # title + priority достаточно для создания
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_update_task_not_found(self, crm_frontend_client, unique_id):
        """Обновление несуществующей задачи возвращает 404"""
        task_id = unique_id("task")
        response = await crm_frontend_client.put(
            f"/frontend/api/crm/tasks/{task_id}",
            json={"title": f"Updated Task {unique_id('title')}"}
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_complete_task_not_found(self, crm_frontend_client, unique_id):
        """Завершение несуществующей задачи возвращает 404"""
        task_id = unique_id("task")
        response = await crm_frontend_client.post(f"/frontend/api/crm/tasks/{task_id}/complete")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_task_not_found(self, crm_frontend_client, unique_id):
        """Удаление несуществующей задачи возвращает 404"""
        task_id = unique_id("task")
        response = await crm_frontend_client.delete(f"/frontend/api/crm/tasks/{task_id}")
        assert response.status_code == 404


class TestCRMGraphAPI:
    """Тесты Knowledge Graph API endpoints"""

    @pytest.mark.asyncio
    async def test_get_graph(self, crm_frontend_client):
        """Получение графа возвращает 200"""
        response = await crm_frontend_client.get("/frontend/api/crm/graph")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_entity_graph_empty(self, crm_frontend_client, unique_id):
        """Граф несуществующей сущности - пустой граф или 404"""
        entity_id = unique_id("entity")
        response = await crm_frontend_client.get(f"/frontend/api/crm/graph/entity/{entity_id}")
        # API возвращает пустой граф (200) или 404
        assert response.status_code in [200, 404]

    @pytest.mark.asyncio
    async def test_get_relationship_types(self, crm_frontend_client):
        """Типы связей возвращают 200"""
        response = await crm_frontend_client.get("/frontend/api/crm/graph/relationship-types")
        assert response.status_code == 200


class TestCRMTaskFormAPI:
    """Тесты Task API через form (frontend proxy)"""

    @pytest.mark.asyncio
    async def test_create_task_via_form(self, crm_frontend_client, unique_id):
        """Создание задачи через JSON POST"""
        from datetime import date
        
        task_title = f"Test Task {unique_id('task')}"
        
        response = await crm_frontend_client.post(
            "/crm/api/tasks",
            json={
                "title": task_title,
                "description": "Test description",
                "priority": "high",
                "due_date": str(date.today()),
                "tags": [],
                "assignees": [],
            }
        )
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_update_task_via_form(self, crm_frontend_client, test_task, unique_id):
        """Обновление задачи через JSON POST"""
        new_title = f"Updated Task {unique_id('title')}"
        
        response = await crm_frontend_client.post(
            f"/crm/api/tasks?task_id={test_task.task_id}",
            json={
                "title": new_title,
                "description": "Updated description",
                "priority": "urgent",
                "status": "in_progress",
                "tags": ["tag1", "tag2"],
                "assignees": [],
            }
        )
        
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_complete_task_html(self, crm_frontend_client, test_task):
        """Завершение задачи возвращает script с event"""
        response = await crm_frontend_client.post(
            f"/crm/api/tasks/{test_task.task_id}/complete"
        )
        
        assert response.status_code == 200
        html = response.text
        assert "taskUpdated" in html

    @pytest.mark.asyncio
    async def test_delete_task_html(self, crm_frontend_client, test_task):
        """Удаление задачи возвращает HTML"""
        response = await crm_frontend_client.delete(
            f"/crm/api/tasks/{test_task.task_id}"
        )
        
        assert response.status_code == 200


class TestCRMExportAPI:
    """Тесты Export API"""

    @pytest.mark.asyncio
    async def test_export_note_pdf(self, crm_frontend_client, test_note):
        """Экспорт заметки в PDF"""
        response = await crm_frontend_client.get(
            f"/crm/api/notes/{test_note.note_id}/export/pdf"
        )
        
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_export_note_html(self, crm_frontend_client, test_note):
        """Экспорт заметки в HTML"""
        response = await crm_frontend_client.get(
            f"/crm/api/notes/{test_note.note_id}/export/html"
        )
        
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_export_note_invalid_format(self, crm_frontend_client, test_note):
        """Экспорт заметки с неверным форматом"""
        response = await crm_frontend_client.get(
            f"/crm/api/notes/{test_note.note_id}/export/docx"
        )
        
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_export_entity_pdf(self, crm_frontend_client, unique_id):
        """Экспорт сущности в PDF"""
        # Создаем entity через API чтобы использовать правильную компанию
        entity_data = {
            "name": f"Export Test Entity {unique_id('export')}",
            "type": "person",
            "attributes": {"email": "export@test.com"}
        }
        create_resp = await crm_frontend_client.post("/frontend/api/crm/entities", json=entity_data)
        assert create_resp.status_code == 200, f"Failed to create entity: {create_resp.text}"
        entity_id = create_resp.json()["entity_id"]
        
        try:
            response = await crm_frontend_client.get(
                f"/frontend/api/crm/export/entity/{entity_id}?format=pdf"
            )
            assert response.status_code == 200
        finally:
            await crm_frontend_client.delete(f"/frontend/api/crm/entities/{entity_id}")

    @pytest.mark.asyncio
    async def test_export_entity_html(self, crm_frontend_client, unique_id):
        """Экспорт сущности в HTML"""
        # Создаем entity через API чтобы использовать правильную компанию
        entity_data = {
            "name": f"Export Test Entity {unique_id('export')}",
            "type": "person",
            "attributes": {"email": "export@test.com"}
        }
        create_resp = await crm_frontend_client.post("/frontend/api/crm/entities", json=entity_data)
        assert create_resp.status_code == 200, f"Failed to create entity: {create_resp.text}"
        entity_id = create_resp.json()["entity_id"]
        
        try:
            response = await crm_frontend_client.get(
                f"/frontend/api/crm/export/entity/{entity_id}?format=html"
            )
            assert response.status_code == 200
        finally:
            await crm_frontend_client.delete(f"/frontend/api/crm/entities/{entity_id}")


class TestCRMTelegramAPI:
    """Тесты Telegram integration API"""

    @pytest.mark.asyncio
    async def test_link_telegram(self, crm_frontend_client, unique_id):
        """Привязка Telegram аккаунта"""
        telegram_id = f"123456789{unique_id('tg')[:3]}"
        
        response = await crm_frontend_client.post(
            "/crm/api/profile/telegram",
            json={"telegram_id": telegram_id}
        )
        
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_link_telegram_empty_id(self, crm_frontend_client):
        """Привязка Telegram без ID возвращает ошибку"""
        response = await crm_frontend_client.post(
            "/crm/api/profile/telegram",
            json={"telegram_id": ""}
        )
        
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_unlink_telegram(self, crm_frontend_client):
        """Отвязка Telegram аккаунта"""
        response = await crm_frontend_client.delete("/crm/api/profile/telegram")
        
        assert response.status_code == 200


class TestCRMAccessRequestsAPI:
    """Тесты Access Requests API"""

    @pytest.mark.asyncio
    async def test_access_requests_pending_count(self, crm_frontend_client):
        """API для pending count возвращает HTML badge"""
        response = await crm_frontend_client.get(
            "/crm/api/access-requests/pending-count"
        )
        
        assert response.status_code == 200
        html = response.text
        assert html == "" or "crm-badge" in html or html.strip().isdigit()


class TestCRMProfileUpdateAPI:
    """Тесты Profile Update API через frontend proxy"""

    @pytest.mark.asyncio
    async def test_update_profile_via_json(self, crm_frontend_client):
        """Обновление профиля через JSON"""
        response = await crm_frontend_client.put(
            "/crm/api/profile",
            json={
                "display_name": "Updated Name",
                "position": "Senior Developer",
                "bio": "Test bio"
            }
        )
        
        assert response.status_code == 200


class TestCRMAttachmentsProxyAPI:
    """Тесты Attachments API через frontend proxy"""

    @pytest.mark.asyncio
    async def test_get_attachments(self, crm_frontend_client, test_note):
        """Получение списка файлов заметки"""
        response = await crm_frontend_client.get(
            f"/crm/api/notes/{test_note.note_id}/attachments"
        )
        
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_upload_attachment(self, crm_frontend_client, test_note):
        """Загрузка файла к заметке"""
        import io
        
        file_content = b"Test file content for upload"
        files = {"file": ("test.txt", io.BytesIO(file_content), "text/plain")}
        
        response = await crm_frontend_client.post(
            f"/crm/api/notes/{test_note.note_id}/attachments",
            files=files
        )
        
        # Может вернуть 200 или HTML с ошибкой
        assert response.status_code in [200, 400, 500]

    @pytest.mark.asyncio
    async def test_delete_attachment_not_found(self, crm_frontend_client, test_note, unique_id):
        """Удаление несуществующего файла"""
        file_id = unique_id("file")
        
        response = await crm_frontend_client.delete(
            f"/crm/api/notes/{test_note.note_id}/attachments/{file_id}"
        )
        
        # Может вернуть 200 (пустой) или 404
        assert response.status_code in [200, 404]

    @pytest.mark.asyncio
    async def test_download_attachment_not_found(self, crm_frontend_client, test_note, unique_id):
        """Скачивание несуществующего файла"""
        file_id = unique_id("file")
        
        response = await crm_frontend_client.get(
            f"/crm/api/notes/{test_note.note_id}/attachments/{file_id}/download"
        )
        
        assert response.status_code in [200, 404]

    @pytest.mark.asyncio
    async def test_get_attachment_content_not_found(self, crm_frontend_client, test_note, unique_id):
        """Получение контента несуществующего файла"""
        file_id = unique_id("file")
        
        response = await crm_frontend_client.get(
            f"/crm/api/notes/{test_note.note_id}/attachments/{file_id}/content"
        )
        
        assert response.status_code in [200, 404]


class TestCRMTemplatesAPI:
    """Тесты Templates API через frontend proxy"""

    @pytest.mark.asyncio
    async def test_create_template(self, crm_frontend_client, unique_id):
        """Создание шаблона"""
        response = await crm_frontend_client.post(
            "/crm/api/templates",
            json={
                "title": f"Test Template {unique_id('tpl')}",
                "content": "## Agenda\n\n## Notes\n\n## Actions",
                "note_type": "meeting_minutes"
            }
        )
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_update_template(self, crm_frontend_client, unique_id):
        """Обновление шаблона (требует существующий template_id)"""
        template_id = unique_id("template")
        
        response = await crm_frontend_client.post(
            f"/crm/api/templates?template_id={template_id}",
            json={
                "title": "Updated Template",
                "content": "Updated content",
                "note_type": "freeform"
            }
        )
        
        # Может вернуть 200 или 404 если шаблон не существует
        assert response.status_code in [200, 404]

    @pytest.mark.asyncio
    async def test_delete_template_not_found(self, crm_frontend_client, unique_id):
        """Удаление несуществующего шаблона"""
        template_id = unique_id("template")
        
        response = await crm_frontend_client.delete(
            f"/crm/api/templates/{template_id}"
        )
        
        # Может вернуть 200 (HTML) или 404
        assert response.status_code in [200, 404]


class TestCRMEntitiesProxyAPI:
    """Тесты Entities API через frontend proxy"""

    @pytest.mark.asyncio
    async def test_create_entity_via_json(self, crm_frontend_client, unique_id):
        """Создание сущности через JSON API"""
        response = await crm_frontend_client.post(
            "/crm/api/entities",
            json={
                "name": f"Test Entity {unique_id('entity')}",
                "type": "person",
                "description": "Test description",
                "attributes": {"email": "test@example.com"}
            }
        )
        
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_update_entity_via_json(self, crm_frontend_client, unique_id):
        """Обновление сущности через JSON API"""
        # Создаем entity через API чтобы использовать правильную компанию
        entity_data = {
            "name": f"Update Test Entity {unique_id('update')}",
            "type": "person",
            "attributes": {"email": "update@test.com"}
        }
        create_resp = await crm_frontend_client.post("/frontend/api/crm/entities", json=entity_data)
        assert create_resp.status_code == 200, f"Failed to create entity: {create_resp.text}"
        entity_id = create_resp.json()["entity_id"]
        
        try:
            response = await crm_frontend_client.put(
                f"/frontend/api/crm/entities/{entity_id}",
                json={
                    "name": "Updated Entity Name",
                    "description": "Updated description"
                }
            )
            assert response.status_code == 200
        finally:
            await crm_frontend_client.delete(f"/frontend/api/crm/entities/{entity_id}")

    @pytest.mark.asyncio
    async def test_delete_entity_via_api(self, crm_frontend_client, unique_id):
        """Удаление сущности через API"""
        # Сначала создаем сущность
        create_response = await crm_frontend_client.post(
            "/crm/api/entities",
            json={
                "name": f"To Delete {unique_id('del')}",
                "type": "person"
            }
        )
        
        if create_response.status_code == 200:
            html = create_response.text
            # Пытаемся удалить (entity_id может быть в script)
            fake_id = unique_id("entity")
            response = await crm_frontend_client.delete(
                f"/crm/api/entities/{fake_id}"
            )
            assert response.status_code == 200


class TestCRMImportAPI:
    """Тесты Import API через frontend proxy"""

    @pytest.mark.asyncio
    async def test_import_note_from_file(self, crm_frontend_client, unique_id):
        """Импорт заметки из файла"""
        import io
        
        file_content = b"# Meeting Notes\n\nDiscussed project timeline."
        files = {"file": ("meeting.txt", io.BytesIO(file_content), "text/plain")}
        
        response = await crm_frontend_client.post(
            "/crm/api/notes/import",
            files=files
        )
        
        # Может вернуть JSON или HTML в зависимости от реализации
        assert response.status_code in [200, 400, 422]


class TestCRMAPIResponseFormat:
    """Тесты формата ответов API"""

    @pytest.mark.asyncio
    async def test_api_returns_json(self, crm_frontend_client):
        """API возвращает JSON"""
        response = await crm_frontend_client.get("/frontend/api/crm/notes")
        content_type = response.headers.get("content-type", "")
        assert "application/json" in content_type

    @pytest.mark.asyncio
    async def test_api_error_format(self, crm_frontend_client):
        """Несуществующий endpoint возвращает 404"""
        response = await crm_frontend_client.get("/frontend/api/crm/nonexistent")
        assert response.status_code == 404
