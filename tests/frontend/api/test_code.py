"""
Тесты для API code (валидация, форматирование, автокомплит).

Используется реальная БД без моков.
"""

import pytest


class TestCodeValidateAPI:
    """Тесты для POST /frontend/api/v1/code/validate-python endpoint"""
    
    @pytest.mark.asyncio
    async def test_validate_valid_code(self, frontend_client):
        """Проверяем валидацию валидного кода"""
        response = await frontend_client.post(
            "/frontend/api/v1/code/validate-python",
            json={"code": "x = 1\ny = 2\nprint(x + y)"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["errors"] == []
    
    @pytest.mark.asyncio
    async def test_validate_invalid_syntax(self, frontend_client):
        """Проверяем валидацию невалидного кода"""
        response = await frontend_client.post(
            "/frontend/api/v1/code/validate-python",
            json={"code": "def broken(:\n    pass"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert len(data["errors"]) > 0
    
    @pytest.mark.asyncio
    async def test_validate_empty_code(self, frontend_client):
        """Проверяем валидацию пустого кода"""
        response = await frontend_client.post(
            "/frontend/api/v1/code/validate-python",
            json={"code": ""}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False


class TestCodeFormatAPI:
    """Тесты для POST /frontend/api/v1/code/format-python endpoint"""
    
    @pytest.mark.asyncio
    async def test_format_valid_code(self, frontend_client):
        """Проверяем форматирование кода"""
        response = await frontend_client.post(
            "/frontend/api/v1/code/format-python",
            json={"code": "x=1"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "formatted" in data


class TestCodeAutocompleteAPI:
    """Тесты для POST /frontend/api/v1/code/completion endpoint"""
    
    @pytest.mark.asyncio
    async def test_autocomplete_basic(self, frontend_client):
        """Проверяем базовый автокомплит"""
        response = await frontend_client.post(
            "/frontend/api/v1/code/completion",
            json={"code": "import ", "cursor_position": 7}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert isinstance(data["items"], list)
    
    @pytest.mark.asyncio
    async def test_autocomplete_empty_code(self, frontend_client):
        """Проверяем автокомплит для пустого кода"""
        response = await frontend_client.post(
            "/frontend/api/v1/code/completion",
            json={"code": "", "cursor_position": 0}
        )
        
        assert response.status_code == 200


class TestCodeDocumentationAPI:
    """Тесты для GET /frontend/api/v1/code/documentation endpoint"""
    
    @pytest.mark.asyncio
    async def test_get_documentation(self, frontend_client):
        """Проверяем получение документации библиотек"""
        response = await frontend_client.get("/frontend/api/v1/code/documentation")
        
        assert response.status_code == 200
        data = response.json()
        assert "libraries" in data
        assert isinstance(data["libraries"], list)
