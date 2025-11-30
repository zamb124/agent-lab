"""
Тесты для API переменных.

Используется реальная БД без моков.
"""

import pytest
import pytest_asyncio

from apps.agents.models import FlowConfig, AgentConfig, AgentType, CodeMode, LLMConfig


@pytest_asyncio.fixture
async def test_agent_for_flow(agent_repo, unique_id, test_context) -> AgentConfig:
    """Тестовый агент для привязки к flow"""
    agent_id = unique_id("var_agent")
    agent = AgentConfig(
        agent_id=agent_id,
        name="Variables Test Agent",
        description="Agent for variables testing",
        type=AgentType.REACT,
        code_mode=CodeMode.CODE_REFERENCE,
        prompt="You are a test agent",
        tools=[],
        llm_config=LLMConfig(model="mock-gpt-4", context_window=10000),
        source="test"
    )
    await agent_repo.set(agent)
    yield agent
    await agent_repo.delete(agent_id)


@pytest_asyncio.fixture
async def test_flow_for_variables(flow_repo, test_agent_for_flow, unique_id, test_context) -> FlowConfig:
    """Тестовый flow для тестов переменных"""
    flow_id = unique_id("var_flow")
    flow = FlowConfig(
        flow_id=flow_id,
        name="Variables Test Flow",
        description="Flow for variables testing",
        entry_point_agent=test_agent_for_flow.agent_id,
        source="test"
    )
    await flow_repo.set(flow)
    yield flow
    await flow_repo.delete(flow_id)


class TestCompanyVariablesAPI:
    """Тесты для API переменных компании (/admin/variables)"""
    
    @pytest.mark.asyncio
    async def test_list_company_variables(self, frontend_client):
        """Проверяем получение списка переменных компании"""
        response = await frontend_client.get("/frontend/api/variables/admin/variables")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
    
    @pytest.mark.asyncio
    async def test_set_company_variable(self, frontend_client, unique_id):
        """Проверяем установку переменной компании"""
        var_key = unique_id("company_var")
        
        response = await frontend_client.post(
            "/frontend/api/variables/admin/variables",
            json={
                "key": var_key,
                "value": "test_value",
                "secret": False,
                "groups": [],
                "description": "Test variable"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["key"] == var_key
        
        # Удалим переменную
        await frontend_client.delete(f"/frontend/api/variables/admin/variables/{var_key}")
    
    @pytest.mark.asyncio
    async def test_get_company_variable(self, frontend_client, unique_id):
        """Проверяем получение переменной компании"""
        var_key = unique_id("get_var")
        
        await frontend_client.post(
            "/frontend/api/variables/admin/variables",
            json={
                "key": var_key,
                "value": "get_test_value",
                "secret": False,
                "groups": [],
                "description": ""
            }
        )
        
        response = await frontend_client.get(f"/frontend/api/variables/admin/variables/{var_key}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["key"] == var_key
        assert data["value"] == "get_test_value"
        
        await frontend_client.delete(f"/frontend/api/variables/admin/variables/{var_key}")
    
    @pytest.mark.asyncio
    async def test_get_company_variable_not_found(self, frontend_client):
        """Проверяем 404 для несуществующей переменной"""
        response = await frontend_client.get("/frontend/api/variables/admin/variables/nonexistent_var")
        
        assert response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_update_company_variable(self, frontend_client, unique_id):
        """Проверяем обновление переменной компании"""
        var_key = unique_id("upd_var")
        
        await frontend_client.post(
            "/frontend/api/variables/admin/variables",
            json={
                "key": var_key,
                "value": "original_value",
                "secret": False,
                "groups": [],
                "description": ""
            }
        )
        
        response = await frontend_client.put(
            f"/frontend/api/variables/admin/variables/{var_key}",
            json={
                "key": var_key,
                "value": "updated_value",
                "secret": False,
                "groups": [],
                "description": "Updated"
            }
        )
        
        assert response.status_code == 200
        
        get_response = await frontend_client.get(f"/frontend/api/variables/admin/variables/{var_key}")
        data = get_response.json()
        assert data["value"] == "updated_value"
        
        await frontend_client.delete(f"/frontend/api/variables/admin/variables/{var_key}")
    
    @pytest.mark.asyncio
    async def test_delete_company_variable(self, frontend_client, unique_id):
        """Проверяем удаление переменной компании"""
        var_key = unique_id("del_var")
        
        await frontend_client.post(
            "/frontend/api/variables/admin/variables",
            json={
                "key": var_key,
                "value": "to_delete",
                "secret": False,
                "groups": [],
                "description": ""
            }
        )
        
        response = await frontend_client.delete(f"/frontend/api/variables/admin/variables/{var_key}")
        
        assert response.status_code == 200
        
        get_response = await frontend_client.get(f"/frontend/api/variables/admin/variables/{var_key}")
        assert get_response.status_code == 404


class TestFlowVariablesAPI:
    """Тесты для API переменных flow"""
    
    @pytest.mark.asyncio
    async def test_get_flow_variables(self, frontend_client, test_flow_for_variables):
        """Проверяем получение всех переменных доступных для flow"""
        response = await frontend_client.get(
            f"/frontend/api/variables/flow/{test_flow_for_variables.flow_id}"
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # API возвращает VariablesResponse с категориями
        assert "system" in data
        assert "company" in data
        assert "user" in data
        assert "flow" in data
        assert "local" in data
        assert "store" in data
        
        assert isinstance(data["system"], list)
        assert isinstance(data["company"], list)
    
    @pytest.mark.asyncio
    async def test_get_flow_variables_for_new_flow(self, frontend_client):
        """Проверяем получение переменных для нового flow (flow_id='new')"""
        response = await frontend_client.get("/frontend/api/variables/flow/new")
        
        assert response.status_code == 200
        data = response.json()
        
        # Для нового flow должны быть системные переменные
        assert "system" in data
        assert len(data["system"]) > 0
    
    @pytest.mark.asyncio
    async def test_get_flow_variables_not_found(self, frontend_client):
        """Проверяем 404 для несуществующего flow"""
        response = await frontend_client.get("/frontend/api/variables/flow/nonexistent_flow")
        
        assert response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_flow_variables_contain_system_vars(self, frontend_client, test_flow_for_variables):
        """Проверяем что системные переменные присутствуют"""
        response = await frontend_client.get(
            f"/frontend/api/variables/flow/{test_flow_for_variables.flow_id}"
        )
        
        assert response.status_code == 200
        data = response.json()
        
        system_var_names = [v["name"] for v in data["system"]]
        assert "current_date" in system_var_names
        assert "current_time" in system_var_names
