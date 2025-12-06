"""
Тесты HTMX partials CRM модуля.

Проверяет что все partial endpoints возвращают корректный HTML.
Все partials требуют CRM бэкенд (crm_server_process).
Используется crm_frontend_client с session_test_data для авторизации.
"""

import pytest


class TestDashboardPartials:
    """Тесты partials для Dashboard"""

    @pytest.mark.asyncio
    async def test_partial_dashboard(self, crm_frontend_client):
        """Partial для Dashboard"""
        response = await crm_frontend_client.get("/crm/partials/dashboard")
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_partial_dashboard_contains_stats(self, crm_frontend_client):
        """Dashboard partial содержит статистику"""
        response = await crm_frontend_client.get("/crm/partials/dashboard")
        html = response.text
        
        assert "crm-" in html

    @pytest.mark.asyncio
    async def test_partial_priority_tasks(self, crm_frontend_client):
        """Partial для приоритетных задач"""
        response = await crm_frontend_client.get("/crm/partials/priority-tasks")
        
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_partial_recent_notes(self, crm_frontend_client):
        """Partial для недавних заметок"""
        response = await crm_frontend_client.get("/crm/partials/recent-notes?limit=5")
        
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_partial_recent_entities(self, crm_frontend_client):
        """Partial для недавних сущностей"""
        response = await crm_frontend_client.get("/crm/partials/recent-entities?limit=5")
        
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_partial_daily_summary(self, crm_frontend_client):
        """Partial для daily summary"""
        response = await crm_frontend_client.get("/crm/partials/daily-summary")
        
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_partial_pending_access_requests(self, crm_frontend_client):
        """Partial для pending access requests"""
        response = await crm_frontend_client.get("/crm/partials/pending-access-requests")
        
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_dashboard_contains_widgets(self, crm_frontend_client):
        """Dashboard содержит виджеты"""
        response = await crm_frontend_client.get("/crm/partials/dashboard")
        html = response.text
        
        assert "widget" in html.lower() or "crm-card" in html


class TestNotesPartials:
    """Тесты partials для Notes"""

    @pytest.mark.asyncio
    async def test_partial_notes(self, crm_frontend_client):
        """Partial для списка заметок"""
        response = await crm_frontend_client.get("/crm/partials/notes")
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_partial_notes_database(self, crm_frontend_client):
        """Partial для базы заметок"""
        response = await crm_frontend_client.get("/crm/partials/notes/database")
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")


class TestEntitiesPartials:
    """Тесты partials для Entities"""

    @pytest.mark.asyncio
    async def test_partial_entities(self, crm_frontend_client):
        """Partial для списка сущностей"""
        response = await crm_frontend_client.get("/crm/partials/entities")
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_partial_entities_with_type(self, crm_frontend_client):
        """Partial для сущностей с фильтром по типу"""
        for entity_type in ["person", "company", "project"]:
            response = await crm_frontend_client.get(f"/crm/partials/entities?type={entity_type}")
            
            assert response.status_code == 200
            assert "text/html" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_partial_entity_modal_new(self, crm_frontend_client):
        """Partial для модалки создания новой сущности"""
        response = await crm_frontend_client.get("/crm/partials/entity-modal")
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_partial_entity_modal_with_entity(self, crm_frontend_client, test_entity):
        """Partial для модалки существующей сущности"""
        response = await crm_frontend_client.get(
            f"/crm/partials/entity-modal/{test_entity.entity_id}"
        )
        
        assert response.status_code == 200
        html = response.text
        assert "crm-entity-modal" in html

    @pytest.mark.asyncio
    async def test_partial_entity_notes(self, crm_frontend_client, test_entity):
        """Partial для заметок сущности"""
        response = await crm_frontend_client.get(
            f"/crm/partials/entity-notes/{test_entity.entity_id}"
        )
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_partial_entity_notes_empty(self, crm_frontend_client, unique_id):
        """Partial для заметок несуществующей сущности"""
        entity_id = unique_id("entity")
        response = await crm_frontend_client.get(f"/crm/partials/entity-notes/{entity_id}")
        
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_partial_entity_tasks(self, crm_frontend_client, test_entity):
        """Partial для задач сущности"""
        response = await crm_frontend_client.get(
            f"/crm/partials/entity-tasks/{test_entity.entity_id}"
        )
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_partial_entity_tasks_empty(self, crm_frontend_client, unique_id):
        """Partial для задач несуществующей сущности"""
        entity_id = unique_id("entity")
        response = await crm_frontend_client.get(f"/crm/partials/entity-tasks/{entity_id}")
        
        assert response.status_code == 200


class TestTasksPartials:
    """Тесты partials для Tasks"""

    @pytest.mark.asyncio
    async def test_partial_tasks(self, crm_frontend_client):
        """Partial для списка задач"""
        response = await crm_frontend_client.get("/crm/partials/tasks")
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_partial_tasks_sidebar(self, crm_frontend_client):
        """Partial для виджета задач в sidebar"""
        response = await crm_frontend_client.get("/crm/partials/tasks-sidebar")
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_partial_tasks_count(self, crm_frontend_client):
        """Partial для счетчика задач"""
        response = await crm_frontend_client.get("/crm/partials/tasks-count")
        
        assert response.status_code == 200
        text = response.text.strip()
        assert text.isdigit() or text == "0"

    @pytest.mark.asyncio
    async def test_partial_tasks_with_status_filter(self, crm_frontend_client):
        """Partial задач с фильтром по статусу"""
        for status in ["pending", "in_progress", "completed"]:
            response = await crm_frontend_client.get(
                f"/crm/partials/tasks?task-status-filter={status}"
            )
            
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_partial_tasks_with_priority_filter(self, crm_frontend_client):
        """Partial задач с фильтром по приоритету"""
        for priority in ["low", "medium", "high", "urgent"]:
            response = await crm_frontend_client.get(
                f"/crm/partials/tasks?task-priority-filter={priority}"
            )
            
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_partial_tasks_with_search(self, crm_frontend_client, unique_id):
        """Partial задач с поиском"""
        search_query = unique_id("search")
        response = await crm_frontend_client.get(
            f"/crm/partials/tasks?task-search={search_query}"
        )
        
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_partial_tasks_with_all_filters(self, crm_frontend_client):
        """Partial задач со всеми фильтрами"""
        response = await crm_frontend_client.get(
            "/crm/partials/tasks?task-status-filter=pending&task-priority-filter=high&task-search=test"
        )
        
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_partial_task_modal_new(self, crm_frontend_client):
        """Partial для модалки создания задачи"""
        response = await crm_frontend_client.get("/crm/partials/task-modal")
        
        assert response.status_code == 200
        html = response.text
        assert "modal" in html.lower()
        assert "title" in html.lower()
        assert "priority" in html.lower()

    @pytest.mark.asyncio
    async def test_partial_task_modal_with_task(self, crm_frontend_client, test_task):
        """Partial для модалки существующей задачи"""
        response = await crm_frontend_client.get(
            f"/crm/partials/task-modal?task_id={test_task.task_id}"
        )
        
        assert response.status_code == 200
        html = response.text
        assert test_task.title in html


class TestGraphPartials:
    """Тесты partials для Knowledge Graph"""

    @pytest.mark.asyncio
    async def test_partial_graph(self, crm_frontend_client):
        """Partial для графа"""
        response = await crm_frontend_client.get("/crm/partials/graph")
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")


class TestSettingsPartials:
    """Тесты partials для Settings"""

    @pytest.mark.asyncio
    async def test_partial_settings(self, crm_frontend_client):
        """Partial для настроек"""
        response = await crm_frontend_client.get("/crm/partials/settings")
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")


class TestModalPartials:
    """Тесты partials для модальных окон"""

    @pytest.mark.asyncio
    async def test_partial_note_modal(self, frontend_client):
        """Partial для модалки создания заметки"""
        response = await frontend_client.get("/crm/partials/note-modal")
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        
        html = response.text
        assert "modal" in html.lower()

    @pytest.mark.asyncio
    async def test_partial_note_modal_contains_visibility(self, frontend_client):
        """Модалка заметки содержит выбор visibility"""
        response = await frontend_client.get("/crm/partials/note-modal")
        
        html = response.text
        assert "visibility" in html.lower()
        assert "private" in html.lower()

    @pytest.mark.asyncio
    async def test_partial_note_modal_contains_shared_with(self, frontend_client):
        """Модалка заметки содержит shared_with"""
        response = await frontend_client.get("/crm/partials/note-modal")
        
        html = response.text
        assert "shared-with" in html or "shared_with" in html

    @pytest.mark.asyncio
    async def test_partial_note_modal_with_existing_note(self, crm_frontend_client, test_note):
        """Модалка существующей заметки содержит кнопки экспорта"""
        response = await crm_frontend_client.get(
            f"/crm/partials/note-modal?note_id={test_note.note_id}"
        )
        
        assert response.status_code == 200
        html = response.text
        assert "export" in html.lower() or "pdf" in html.lower()

    @pytest.mark.asyncio
    async def test_partial_entity_modal(self, crm_frontend_client):
        """Partial для модалки сущности"""
        response = await crm_frontend_client.get("/crm/partials/entity-modal")
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        
        html = response.text
        assert "modal" in html.lower()

    @pytest.mark.asyncio
    async def test_partial_ai_suggestions_modal(self, frontend_client):
        """Partial для модалки AI предложений"""
        response = await frontend_client.get("/crm/partials/ai-suggestions-modal")
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_partial_import_modal(self, crm_frontend_client):
        """Partial для модалки импорта"""
        response = await crm_frontend_client.get("/crm/partials/import-modal")
        
        assert response.status_code == 200
        html = response.text
        assert "modal" in html.lower()
        assert "import" in html.lower() or "upload" in html.lower()

    @pytest.mark.asyncio
    async def test_partial_request_access_modal(self, crm_frontend_client, test_note):
        """Модалка запроса доступа"""
        response = await crm_frontend_client.get(
            f"/crm/partials/request-access-modal?resource_type=note&resource_id={test_note.note_id}"
        )
        
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_partial_profile_modal(self, crm_frontend_client):
        """Модалка редактирования профиля"""
        response = await crm_frontend_client.get("/crm/partials/profile-modal")
        
        assert response.status_code == 200
        html = response.text
        assert "modal" in html.lower()


class TestSearchPartials:
    """Тесты partials для поиска"""

    @pytest.mark.asyncio
    async def test_partial_search_empty(self, frontend_client):
        """Partial поиска без запроса"""
        response = await frontend_client.get("/crm/partials/search")
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_partial_search_with_query(self, crm_frontend_client):
        """Partial поиска с запросом"""
        response = await crm_frontend_client.get("/crm/partials/search?q=test")
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")


class TestProfilePartials:
    """Тесты partials для Profile"""

    @pytest.mark.asyncio
    async def test_partial_profile(self, crm_frontend_client):
        """Partial для профиля"""
        response = await crm_frontend_client.get("/crm/partials/profile")
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_profile_contains_telegram_section(self, crm_frontend_client):
        """Профиль содержит секцию Telegram"""
        response = await crm_frontend_client.get("/crm/partials/profile")
        
        html = response.text
        assert "telegram" in html.lower()

    @pytest.mark.asyncio
    async def test_profile_contains_sidebar_settings(self, crm_frontend_client):
        """Профиль содержит настройки sidebar"""
        response = await crm_frontend_client.get("/crm/partials/profile")
        
        html = response.text
        assert "sidebar" in html.lower()

    @pytest.mark.asyncio
    async def test_profile_contains_widget_settings(self, crm_frontend_client):
        """Профиль содержит настройки виджетов"""
        response = await crm_frontend_client.get("/crm/partials/profile")
        
        html = response.text
        assert "widget" in html.lower()

    @pytest.mark.asyncio
    async def test_profile_contains_heatmap(self, crm_frontend_client):
        """Профиль содержит heatmap активности"""
        response = await crm_frontend_client.get("/crm/partials/profile")
        
        html = response.text
        assert "heatmap" in html.lower() or "activity" in html.lower()


class TestAccessRequestsPartials:
    """Тесты partials для Access Requests"""

    @pytest.mark.asyncio
    async def test_partial_access_requests_incoming(self, crm_frontend_client):
        """Partial для входящих запросов"""
        response = await crm_frontend_client.get(
            "/crm/partials/access-requests?tab=incoming"
        )
        
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_partial_access_requests_outgoing(self, crm_frontend_client):
        """Partial для исходящих запросов"""
        response = await crm_frontend_client.get(
            "/crm/partials/access-requests?tab=outgoing"
        )
        
        assert response.status_code == 200


class TestNotesViewPartials:
    """Тесты partials для просмотра заметок"""

    @pytest.mark.asyncio
    async def test_partial_note_view(self, crm_frontend_client, test_note):
        """Partial для просмотра одной заметки"""
        response = await crm_frontend_client.get(
            f"/crm/partials/notes/{test_note.note_id}"
        )
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_partial_note_suggestions(self, crm_frontend_client, test_note):
        """Partial для AI suggestions заметки"""
        response = await crm_frontend_client.get(
            f"/crm/partials/notes/{test_note.note_id}/suggestions"
        )
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_partial_note_linked_entities(self, crm_frontend_client, test_note):
        """Partial для связанных сущностей заметки"""
        response = await crm_frontend_client.get(
            f"/crm/partials/notes/{test_note.note_id}/linked-entities"
        )
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")


class TestNotesFormPartials:
    """Тесты partials для форм заметок"""

    @pytest.mark.asyncio
    async def test_create_note_via_partial(self, crm_frontend_client, unique_id):
        """Создание заметки через partial POST"""
        from datetime import date
        
        response = await crm_frontend_client.post(
            "/crm/partials/notes",
            json={
                "title": f"Test Note {unique_id('note')}",
                "content": "Test content",
                "note_type": "freeform",
                "note_date": str(date.today()),
            }
        )
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_analyze_note_partial(self, crm_frontend_client, test_note):
        """Partial для AI анализа заметки"""
        response = await crm_frontend_client.post(
            f"/crm/partials/notes/{test_note.note_id}/analyze"
        )
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_approve_suggestions_partial(self, crm_frontend_client, test_note):
        """Partial для одобрения AI suggestions"""
        response = await crm_frontend_client.post(
            f"/crm/partials/notes/{test_note.note_id}/approve-suggestions",
            json={"entities": [], "tasks": []}
        )
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_close_modal_and_refresh(self, crm_frontend_client):
        """Partial для закрытия модалки и обновления списка"""
        response = await crm_frontend_client.post(
            "/crm/partials/notes/close-modal"
        )
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_unlink_entity_from_note(self, crm_frontend_client, test_note, unique_id):
        """Partial для отвязки сущности от заметки"""
        entity_id = unique_id("entity")
        
        response = await crm_frontend_client.delete(
            f"/crm/partials/notes/{test_note.note_id}/unlink/{entity_id}"
        )
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")


class TestEntityActionsPartials:
    """Тесты partials для действий с сущностями"""

    @pytest.mark.asyncio
    async def test_partial_entity_detail(self, crm_frontend_client, test_entity):
        """Partial для детальной информации о сущности"""
        response = await crm_frontend_client.get(
            f"/crm/partials/entity/{test_entity.entity_id}"
        )
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_partial_entity_intelligence(self, crm_frontend_client, test_entity):
        """Partial для AI intelligence summary сущности"""
        response = await crm_frontend_client.get(
            f"/crm/partials/entity-intelligence/{test_entity.entity_id}"
        )
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_partial_entity_history(self, crm_frontend_client, test_entity):
        """Partial для истории взаимодействий сущности"""
        response = await crm_frontend_client.get(
            f"/crm/partials/entity-history/{test_entity.entity_id}"
        )
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_approve_entity_partial(self, crm_frontend_client, test_entity):
        """Partial для одобрения сущности"""
        response = await crm_frontend_client.post(
            f"/crm/partials/entities/{test_entity.entity_id}/approve"
        )
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_reject_entity_partial(self, crm_frontend_client, test_entity):
        """Partial для отклонения сущности"""
        response = await crm_frontend_client.post(
            f"/crm/partials/entities/{test_entity.entity_id}/reject"
        )
        
        assert response.status_code == 200


class TestTemplatesPartials:
    """Тесты partials для шаблонов"""

    @pytest.mark.asyncio
    async def test_partial_templates_list(self, crm_frontend_client):
        """Partial для списка шаблонов"""
        response = await crm_frontend_client.get("/crm/partials/templates-list")
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_partial_template_modal_new(self, crm_frontend_client):
        """Partial для модалки создания шаблона"""
        response = await crm_frontend_client.get("/crm/partials/template-modal")
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        
        html = response.text
        assert "modal" in html.lower()

    @pytest.mark.asyncio
    async def test_partial_template_modal_existing(self, crm_frontend_client, unique_id):
        """Partial для модалки существующего шаблона"""
        template_id = unique_id("template")
        response = await crm_frontend_client.get(
            f"/crm/partials/template-modal?template_id={template_id}"
        )
        
        assert response.status_code == 200


class TestOtherPartials:
    """Тесты других partials"""

    @pytest.mark.asyncio
    async def test_partial_ai_suggestions_without_modal(self, crm_frontend_client):
        """Partial для AI suggestions (без modal wrapper)"""
        response = await crm_frontend_client.get("/crm/partials/ai-suggestions")
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")


class TestHTMXHeaders:
    """Тесты HTMX-специфичных заголовков"""

    @pytest.mark.asyncio
    async def test_partials_accept_htmx_request(self, crm_frontend_client):
        """Partials принимают HTMX запросы"""
        response = await crm_frontend_client.get(
            "/crm/partials/dashboard",
            headers={"HX-Request": "true"}
        )
        
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_partials_work_without_htmx_header(self, crm_frontend_client):
        """Partials работают и без HTMX заголовка"""
        response = await crm_frontend_client.get("/crm/partials/dashboard")
        
        assert response.status_code == 200
