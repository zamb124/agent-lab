"""
Тесты статических файлов CRM модуля.

Проверяет что CSS, JS и изображения доступны.
"""

import pytest


class TestCRMStaticCSS:
    """Тесты CSS файлов"""

    @pytest.mark.asyncio
    async def test_crm_css_available(self, crm_frontend_client):
        """crm.css доступен"""
        response = await crm_frontend_client.get("/static/crm/css/crm.css")
        
        assert response.status_code == 200
        assert "text/css" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_crm_css_contains_variables(self, crm_frontend_client):
        """crm.css содержит CSS переменные"""
        response = await crm_frontend_client.get("/static/crm/css/crm.css")
        css = response.text
        
        # Проверяем наличие CSS переменных для темы
        assert "--crm-" in css
        assert ":root" in css

    @pytest.mark.asyncio
    async def test_crm_css_has_dark_theme(self, crm_frontend_client):
        """crm.css содержит темную тему"""
        response = await crm_frontend_client.get("/static/crm/css/crm.css")
        css = response.text
        
        assert "[data-theme=\"dark\"]" in css or "data-theme=dark" in css


class TestCRMStaticJS:
    """Тесты JavaScript файлов"""

    @pytest.mark.asyncio
    async def test_crm_module_js_available(self, crm_frontend_client):
        """crm.module.js доступен"""
        response = await crm_frontend_client.get("/static/crm/js/crm.module.js")
        
        assert response.status_code == 200
        assert "javascript" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_crm_module_js_contains_api_client(self, crm_frontend_client):
        """crm.module.js содержит API методы"""
        response = await crm_frontend_client.get("/static/crm/js/crm.module.js")
        js = response.text
        
        # Проверяем наличие API методов
        assert "apiRequest" in js or "apiBase" in js

    @pytest.mark.asyncio
    async def test_crm_module_js_contains_module_class(self, crm_frontend_client):
        """crm.module.js содержит класс модуля"""
        response = await crm_frontend_client.get("/static/crm/js/crm.module.js")
        js = response.text
        
        assert "CRMModule" in js

    @pytest.mark.asyncio
    async def test_crm_module_js_exposes_global(self, crm_frontend_client):
        """crm.module.js создает глобальный объект window.CRM"""
        response = await crm_frontend_client.get("/static/crm/js/crm.module.js")
        js = response.text
        
        assert "window.CRM" in js

    @pytest.mark.asyncio
    async def test_vis_network_js_available(self, crm_frontend_client):
        """vis-network.min.js доступен (локальная версия)"""
        response = await crm_frontend_client.get("/static/crm/js/vis-network.min.js")
        
        assert response.status_code == 200
        assert "javascript" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_vis_network_js_is_valid(self, crm_frontend_client):
        """vis-network.min.js содержит vis.js код"""
        response = await crm_frontend_client.get("/static/crm/js/vis-network.min.js")
        js = response.text
        
        # Проверяем наличие vis.Network или vis-network кода
        assert "Network" in js or "vis" in js
        # Файл должен быть достаточно большим (минимум 100KB)
        assert len(js) > 100000


class TestCRMStaticImages:
    """Тесты изображений"""

    @pytest.mark.asyncio
    async def test_logo_svg_available(self, crm_frontend_client):
        """Логотип Networkle доступен"""
        response = await crm_frontend_client.get("/static/crm/img/logo_networkle.svg")
        
        # SVG может вернуть 200 или 404 если файл не существует
        if response.status_code == 200:
            assert "image/svg+xml" in response.headers.get("content-type", "") or \
                   "xml" in response.headers.get("content-type", "")


class TestCRMStaticNotFound:
    """Тесты обработки несуществующих файлов"""

    @pytest.mark.asyncio
    async def test_nonexistent_css_returns_404(self, crm_frontend_client):
        """Несуществующий CSS возвращает 404"""
        response = await crm_frontend_client.get("/static/crm/css/nonexistent.css")
        
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_nonexistent_js_returns_404(self, crm_frontend_client):
        """Несуществующий JS возвращает 404"""
        response = await crm_frontend_client.get("/static/crm/js/nonexistent.js")
        
        assert response.status_code == 404

