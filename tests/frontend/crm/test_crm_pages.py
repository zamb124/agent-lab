"""
Тесты HTML страниц CRM модуля.

Проверяет что все страницы рендерятся корректно.
Никаких моков - реальное приложение через ASGITransport.
"""

import pytest


class TestCRMMainPages:
    """Тесты основных страниц CRM"""

    @pytest.mark.asyncio
    async def test_crm_dashboard_page(self, frontend_client):
        """Главная страница CRM (Dashboard)"""
        response = await frontend_client.get("/crm/")
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        
        html = response.text
        assert "crm-app" in html
        assert "crm-sidebar" in html
        assert "crm-content" in html

    @pytest.mark.asyncio
    async def test_crm_notes_page(self, frontend_client):
        """Страница ежедневных заметок"""
        response = await frontend_client.get("/crm/notes")
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        
        html = response.text
        assert "crm-app" in html
        assert 'current_page' in html or 'notes' in html.lower()

    @pytest.mark.asyncio
    async def test_crm_notes_database_page(self, frontend_client):
        """Страница базы заметок"""
        response = await frontend_client.get("/crm/notes/database")
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_crm_entities_page(self, frontend_client):
        """Страница сущностей"""
        response = await frontend_client.get("/crm/entities")
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_crm_entities_page_with_type_filter(self, frontend_client):
        """Страница сущностей с фильтром по типу"""
        for entity_type in ["person", "company", "project"]:
            response = await frontend_client.get(f"/crm/entities?type={entity_type}")
            
            assert response.status_code == 200
            assert "text/html" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_crm_entity_detail_page(self, frontend_client, unique_id):
        """Страница детальной информации о сущности"""
        entity_id = unique_id("entity")
        response = await frontend_client.get(f"/crm/entities/{entity_id}")
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_crm_tasks_page(self, frontend_client):
        """Страница задач"""
        response = await frontend_client.get("/crm/tasks")
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_crm_graph_page(self, frontend_client):
        """Страница Knowledge Graph"""
        response = await frontend_client.get("/crm/graph")
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_crm_settings_page(self, frontend_client):
        """Страница настроек"""
        response = await frontend_client.get("/crm/settings")
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")


class TestCRMPageStructure:
    """Тесты структуры HTML страниц"""

    @pytest.mark.asyncio
    async def test_crm_base_has_sidebar(self, frontend_client):
        """Страница содержит sidebar с навигацией"""
        response = await frontend_client.get("/crm/")
        html = response.text
        
        # Проверяем наличие sidebar элементов
        assert "crm-sidebar" in html
        assert "crm-sidebar-nav" in html

    @pytest.mark.asyncio
    async def test_crm_base_has_header(self, frontend_client):
        """Страница содержит header"""
        response = await frontend_client.get("/crm/")
        html = response.text
        
        assert "crm-header" in html

    @pytest.mark.asyncio
    async def test_crm_base_has_tasks_panel(self, frontend_client):
        """Страница содержит панель задач справа"""
        response = await frontend_client.get("/crm/")
        html = response.text
        
        assert "crm-tasks-panel" in html

    @pytest.mark.asyncio
    async def test_crm_base_includes_css(self, frontend_client):
        """Страница подключает crm.css"""
        response = await frontend_client.get("/crm/")
        html = response.text
        
        assert "crm.css" in html or "crm/css" in html

    @pytest.mark.asyncio
    async def test_crm_base_has_modal_container(self, frontend_client):
        """Страница содержит контейнер для модальных окон"""
        response = await frontend_client.get("/crm/")
        html = response.text
        
        assert "modal-container" in html

    @pytest.mark.asyncio
    async def test_crm_base_has_htmx_triggers(self, frontend_client):
        """Страница содержит HTMX атрибуты"""
        response = await frontend_client.get("/crm/")
        html = response.text
        
        # HTMX атрибуты для динамической загрузки
        assert "hx-get" in html
        assert "hx-target" in html


class TestCRMNavigation:
    """Тесты навигации между страницами"""

    @pytest.mark.asyncio
    async def test_sidebar_contains_all_nav_items(self, frontend_client):
        """Sidebar содержит все пункты навигации"""
        response = await frontend_client.get("/crm/")
        html = response.text
        
        # Основные пункты навигации
        nav_items = ["/crm/", "/crm/notes", "/crm/entities", "/crm/tasks", "/crm/graph"]
        
        for nav_item in nav_items:
            assert nav_item in html, f"Навигация {nav_item} отсутствует"

    @pytest.mark.asyncio
    async def test_back_to_dashboard_link(self, frontend_client):
        """Есть ссылка возврата в основной дашборд"""
        response = await frontend_client.get("/crm/")
        html = response.text
        
        assert "/frontend/" in html


class TestCRMAuthentication:
    """Тесты авторизации CRM страниц"""

    @pytest.mark.asyncio
    async def test_crm_requires_auth(self, frontend_app):
        """CRM страницы требуют авторизации"""
        import httpx
        from httpx import ASGITransport
        
        transport = ASGITransport(app=frontend_app)
        
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test.localhost:8002",
            headers={"Host": "test.localhost:8002"}
        ) as client:
            response = await client.get("/crm/")
            
            # Редирект на логин или 401
            assert response.status_code in [302, 401, 403]

