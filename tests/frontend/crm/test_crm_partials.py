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
