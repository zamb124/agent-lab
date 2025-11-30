"""
Тесты для API переменных.

Используется реальная БД без моков.
"""

import uuid
import pytest
import pytest_asyncio

from apps.agents.models import FlowConfig, AgentConfig, AgentType, CodeMode, LLMConfig


def make_unique_id(prefix: str) -> str:
    """Генерирует уникальный ID"""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@pytest_asyncio.fixture
async def test_agent_for_var_flow(frontend_agent_repo, frontend_client) -> AgentConfig:
    """Тестовый агент для привязки к flow"""
    agent_id = make_unique_id("var_agent")
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
    await frontend_agent_repo.set(agent)
    yield agent
    await frontend_agent_repo.delete(agent_id)


@pytest_asyncio.fixture
async def test_flow_for_variables(frontend_flow_repo, test_agent_for_var_flow, frontend_client) -> FlowConfig:
    """Тестовый flow для тестов переменных"""
    flow_id = make_unique_id("var_flow")
    flow = FlowConfig(
        flow_id=flow_id,
        name="Variables Test Flow",
        description="Flow for variables testing",
        entry_point_agent=test_agent_for_var_flow.agent_id,
        source="test",
        variables={"flow_var_1": "value_1"}
    )
    await frontend_flow_repo.set(flow)
    yield flow
    await frontend_flow_repo.delete(flow_id)


class TestCompanyVariablesAPI:
    """Тесты для API переменных компании"""
    
    @pytest.mark.asyncio
    async def test_list_company_variables(self, frontend_client):
        """Проверяем получение списка переменных компании"""
        response = await frontend_client.get("/frontend/api/variables/admin/variables")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
    
    @pytest.mark.asyncio
    async def test_set_company_variable(self, frontend_client):
        """Проверяем установку переменной компании"""
        var_name = make_unique_id("company_var")
        
        response = await frontend_client.post(
            "/frontend/api/variables/admin/variables",
            json={"key": var_name, "value": "test_value"}
        )
        
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_get_company_variable(self, frontend_client):
        """Проверяем получение переменной компании"""
        var_name = make_unique_id("get_var")
        
        await frontend_client.post(
            "/frontend/api/variables/admin/variables",
            json={"key": var_name, "value": "get_test_value"}
        )
        
        response = await frontend_client.get(f"/frontend/api/variables/admin/variables/{var_name}")
        
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_update_company_variable(self, frontend_client):
        """Проверяем обновление переменной компании"""
        var_name = make_unique_id("update_var")
        await frontend_client.post(
            "/frontend/api/variables/admin/variables",
            json={"key": var_name, "value": "original_value"}
        )

        response = await frontend_client.put(
            f"/frontend/api/variables/admin/variables/{var_name}",
            json={"key": var_name, "value": "updated_value"}
        )
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_delete_company_variable(self, frontend_client):
        """Проверяем удаление переменной компании"""
        var_name = make_unique_id("del_var")
        
        await frontend_client.post(
            "/frontend/api/variables/admin/variables",
            json={"key": var_name, "value": "to_delete"}
        )
        
        response = await frontend_client.delete(f"/frontend/api/variables/admin/variables/{var_name}")
        
        assert response.status_code == 200


class TestFlowVariablesAPI:
    """Тесты для API переменных flow"""
    
    @pytest.mark.asyncio
    async def test_flow_variables_contain_system_vars(self, frontend_client, test_flow_for_variables):
        """Проверяем получение переменных flow"""
        response = await frontend_client.get(
            f"/frontend/api/variables/flow/{test_flow_for_variables.flow_id}"
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
