"""
Тесты для API tools.

Используется реальная БД без моков.
"""

import pytest
import pytest_asyncio

from apps.agents.models import ToolReference, CodeMode


@pytest_asyncio.fixture
async def test_tool(tool_repo, unique_id, test_context) -> ToolReference:
    """Тестовый инструмент"""
    tool_id = unique_id("tool")
    tool = ToolReference(
        tool_id=tool_id,
        code_mode=CodeMode.CODE_REFERENCE,
        function_path="apps.agents.tools.test_tool",
        description="Test tool for API testing",
        params={}
    )
    await tool_repo.set(tool)
    yield tool
    await tool_repo.delete(tool_id)


@pytest_asyncio.fixture
async def test_inline_tool(tool_repo, unique_id, test_context) -> ToolReference:
    """Тестовый inline инструмент"""
    tool_id = unique_id("inline_tool")
    
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
    await tool_repo.set(tool)
    yield tool
    await tool_repo.delete(tool_id)


class TestToolsListAPI:
    """Тесты для GET /frontend/api/tools/ endpoint"""
    
    @pytest.mark.asyncio
    async def test_list_tools_returns_tools(self, frontend_client, test_tool):
        """Проверяем получение списка инструментов"""
        response = await frontend_client.get("/frontend/api/tools/")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        # API возвращает id вместо tool_id
        tool_ids = [t["id"] for t in data]
        assert test_tool.tool_id in tool_ids
    
    @pytest.mark.asyncio
    async def test_list_tools_public_only(self, frontend_client, test_tool):
        """Проверяем фильтрацию публичных инструментов"""
        response = await frontend_client.get("/frontend/api/tools/?public_only=true")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestToolDetailAPI:
    """Тесты для GET /frontend/api/tools/{tool_id} endpoint"""
    
    @pytest.mark.asyncio
    async def test_get_tool_by_id(self, frontend_client, test_tool):
        """Проверяем получение инструмента по ID"""
        response = await frontend_client.get(f"/frontend/api/tools/{test_tool.tool_id}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["id"] == test_tool.tool_id
        assert data["code_mode"] == "code_reference"
        assert data["description"] == "Test tool for API testing"
    
    @pytest.mark.asyncio
    async def test_get_tool_not_found(self, frontend_client):
        """Проверяем 404 для несуществующего инструмента"""
        response = await frontend_client.get("/frontend/api/tools/nonexistent_tool")
        
        assert response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_get_inline_tool(self, frontend_client, test_inline_tool):
        """Проверяем получение inline инструмента"""
        response = await frontend_client.get(f"/frontend/api/tools/{test_inline_tool.tool_id}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["id"] == test_inline_tool.tool_id
        assert data["code_mode"] == "inline_code"


class TestToolCreateAPI:
    """Тесты для POST /frontend/api/tools/ endpoint"""
    
    @pytest.mark.asyncio
    async def test_create_tool(self, frontend_client, tool_repo):
        """Проверяем создание инструмента (tool_id генерируется автоматически)"""
        response = await frontend_client.post(
            "/frontend/api/tools/",
            params={
                "name": "New Test Tool",
                "description": "Newly created tool",
                "category": "general"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        tool_id = data["tool_id"]
        assert tool_id.startswith("tool_")
        
        await tool_repo.delete(tool_id)


class TestToolUpdateAPI:
    """Тесты для PUT /frontend/api/tools/{tool_id} endpoint"""
    
    @pytest.mark.asyncio
    async def test_update_tool(self, frontend_client, test_tool, tool_repo):
        """Проверяем обновление инструмента"""
        updates = {
            "description": "Updated description"
        }
        
        response = await frontend_client.put(
            f"/frontend/api/tools/{test_tool.tool_id}",
            json=updates
        )
        
        assert response.status_code == 200
        
        updated_tool = await tool_repo.get(test_tool.tool_id)
        assert updated_tool.description == "Updated description"
    
    @pytest.mark.asyncio
    async def test_update_tool_not_found(self, frontend_client):
        """Проверяем 404 для несуществующего инструмента"""
        response = await frontend_client.put(
            "/frontend/api/tools/nonexistent_tool",
            json={"description": "New desc"}
        )
        
        assert response.status_code == 404


class TestToolDeleteAPI:
    """Тесты для DELETE /frontend/api/tools/{tool_id} endpoint"""
    
    @pytest.mark.asyncio
    async def test_delete_tool(self, frontend_client, tool_repo, unique_id):
        """Проверяем удаление инструмента"""
        tool_id = unique_id("tool_to_delete")
        tool = ToolReference(
            tool_id=tool_id,
            code_mode=CodeMode.INLINE_CODE,
            inline_code="pass",
            description="Tool to delete",
            params={}
        )
        await tool_repo.set(tool)
        
        response = await frontend_client.delete(f"/frontend/api/tools/{tool_id}")
        
        assert response.status_code == 200
        
        deleted_tool = await tool_repo.get(tool_id)
        assert deleted_tool is None
    
    @pytest.mark.asyncio
    async def test_delete_tool_not_found(self, frontend_client):
        """Проверяем 404 для несуществующего инструмента"""
        response = await frontend_client.delete("/frontend/api/tools/nonexistent_tool")
        
        assert response.status_code == 404
