"""
Тесты для API code (валидация и автодополнение).

Используется реальная БД без моков.
"""

import pytest
import pytest_asyncio


class TestCodeValidateAPI:
    """Тесты для POST /frontend/api/code/validate endpoint"""
    
    @pytest.mark.asyncio
    async def test_validate_valid_code(self, frontend_client):
        """Проверяем валидацию корректного кода"""
        code = """
def hello(name: str) -> str:
    return f"Hello, {name}!"
"""
        
        response = await frontend_client.post(
            "/frontend/api/code/validate",
            json={"code": code}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["valid"] is True
        assert data["errors"] == []
    
    @pytest.mark.asyncio
    async def test_validate_invalid_syntax(self, frontend_client):
        """Проверяем валидацию кода с синтаксической ошибкой"""
        code = """
def hello(name
    return f"Hello, {name}!"
"""
        
        response = await frontend_client.post(
            "/frontend/api/code/validate",
            json={"code": code}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["valid"] is False
        assert len(data["errors"]) > 0
    
    @pytest.mark.asyncio
    async def test_validate_empty_code(self, frontend_client):
        """Проверяем валидацию пустого кода"""
        response = await frontend_client.post(
            "/frontend/api/code/validate",
            json={"code": ""}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["valid"] is True
    
    @pytest.mark.asyncio
    async def test_validate_async_code(self, frontend_client):
        """Проверяем валидацию асинхронного кода"""
        code = """
from apps.agents.services.tool_decorator import tool

@tool
async def my_tool(query: str) -> str:
    \"\"\"My async tool\"\"\"
    return f"Result: {query}"
"""
        
        response = await frontend_client.post(
            "/frontend/api/code/validate",
            json={"code": code}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["valid"] is True


class TestCodeAutocompleteAPI:
    """Тесты для POST /frontend/api/code/autocomplete endpoint"""
    
    @pytest.mark.asyncio
    async def test_autocomplete_basic(self, frontend_client):
        """Проверяем базовое автодополнение"""
        response = await frontend_client.post(
            "/frontend/api/code/autocomplete",
            json={
                "code": "from apps.",
                "cursor_position": 10
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "completions" in data
        assert isinstance(data["completions"], list)
    
    @pytest.mark.asyncio
    async def test_autocomplete_empty_code(self, frontend_client):
        """Проверяем автодополнение для пустого кода"""
        response = await frontend_client.post(
            "/frontend/api/code/autocomplete",
            json={
                "code": "",
                "cursor_position": 0
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "completions" in data


class TestCodeFormatAPI:
    """Тесты для POST /frontend/api/code/format endpoint"""
    
    @pytest.mark.asyncio
    async def test_format_code(self, frontend_client):
        """Проверяем форматирование кода"""
        code = """
def    hello(  name:str)->str:
    return f"Hello, {name}!"
"""
        
        response = await frontend_client.post(
            "/frontend/api/code/format",
            json={"code": code}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "formatted" in data
    
    @pytest.mark.asyncio
    async def test_format_invalid_code(self, frontend_client):
        """Проверяем форматирование невалидного кода"""
        code = """
def hello(name
    return 
"""
        
        response = await frontend_client.post(
            "/frontend/api/code/format",
            json={"code": code}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "formatted" in data or "error" in data

