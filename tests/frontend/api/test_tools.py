"""
Тесты для API tools.

Используется реальная БД без моков.
"""

import uuid
import pytest
import pytest_asyncio

from apps.agents.models import ToolReference, CodeMode


def make_unique_id(prefix: str) -> str:
    """Генерирует уникальный ID"""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@pytest_asyncio.fixture
async def test_tool(frontend_tool_repo, frontend_client) -> ToolReference:
    """Тестовый инструмент"""
    tool_id = make_unique_id("tool")
    tool = ToolReference(
        tool_id=tool_id,
        code_mode=CodeMode.CODE_REFERENCE,
        function_path="apps.agents.tools.test_tool",
        description="Test tool for API testing",
        params={}
    )
    await frontend_tool_repo.set(tool)
    yield tool
    await frontend_tool_repo.delete(tool_id)


@pytest_asyncio.fixture
async def test_inline_tool(frontend_tool_repo, frontend_client) -> ToolReference:
    """Тестовый inline инструмент"""
    tool_id = make_unique_id("inline_tool")
    
    inline_code = '''
from apps.agents.services.tool_decorator import tool

@tool
async def test_inline_tool(query: str) -> str:
    """Тестовый inline инструмент"""
    return f"Result for: {query}"
'''
    
    tool = ToolReference(
        tool_id=tool_id,
        code_mode=CodeMode.INLINE_CODE,
        inline_code=inline_code,
        description="Inline test tool",
        params={}
    )
    await frontend_tool_repo.set(tool)
    yield tool
    await frontend_tool_repo.delete(tool_id)


class TestToolsListAPI:
    """Тесты для GET /frontend/api/v1/tools/ endpoint"""
    
    @pytest.mark.asyncio
    async def test_list_tools_returns_tools(self, frontend_client, test_tool):
        """Проверяем получение списка инструментов"""
        response = await frontend_client.get("/frontend/api/v1/tools/")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    @pytest.mark.asyncio
    async def test_list_tools_public_only(self, frontend_client, test_tool):
        """Проверяем фильтр public_only"""
        response = await frontend_client.get("/frontend/api/v1/tools/?public_only=true")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestToolDetailAPI:
    """Тесты для GET /frontend/api/v1/tools/{tool_id} endpoint"""
    
    @pytest.mark.asyncio
    async def test_get_tool_by_id(self, frontend_client, test_tool):
        """Проверяем получение инструмента по ID"""
        response = await frontend_client.get(f"/frontend/api/v1/tools/{test_tool.tool_id}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["id"] == test_tool.tool_id
    
    @pytest.mark.asyncio
    async def test_get_tool_not_found(self, frontend_client):
        """Проверяем 404 для несуществующего инструмента"""
        response = await frontend_client.get("/frontend/api/v1/tools/nonexistent_tool")
        
        assert response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_get_inline_tool(self, frontend_client, test_inline_tool):
        """Проверяем получение inline инструмента"""
        response = await frontend_client.get(f"/frontend/api/v1/tools/{test_inline_tool.tool_id}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["id"] == test_inline_tool.tool_id
        assert data["code_mode"] == "inline_code"


class TestToolCreateAPI:
    """Тесты для POST /frontend/api/v1/tools/ endpoint"""
    
    @pytest.mark.asyncio
    async def test_create_tool(self, frontend_client, frontend_tool_repo):
        """Проверяем создание инструмента"""
        tool_id = make_unique_id("new_tool")
        
        tool_data = {
            "tool_id": tool_id,
            "code_mode": "code_reference",
            "function_path": "apps.agents.tools.new_tool",
            "description": "Newly created tool",
            "params": {}
        }
        
        response = await frontend_client.post("/frontend/api/v1/tools/", json=tool_data)
        
        assert response.status_code == 200
        
        # Очистка
        await frontend_tool_repo.delete(tool_id)
