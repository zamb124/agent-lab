"""
Тесты для FlowRepository.
"""

import pytest
from apps.agents.models import FlowConfig


@pytest.mark.asyncio
async def test_flow_repository_save_and_find(flow_repo):
    """Тест сохранения и поиска flow через репозиторий"""
    config = FlowConfig(
        flow_id="test.repo.flow",
        name="Test Repo Flow",
        entry_point_agent="test.agent",
        platforms={"api": {}}
    )
    
    result = await flow_repo.set(config)
    assert result is True
    
    found = await flow_repo.get("test.repo.flow")
    assert found is not None
    assert found.flow_id == "test.repo.flow"
    assert found.name == "Test Repo Flow"


@pytest.mark.asyncio
async def test_flow_repository_delete(flow_repo):
    """Тест удаления flow через репозиторий"""
    config = FlowConfig(
        flow_id="test.repo.delete.flow",
        name="Test Delete Flow",
        entry_point_agent="test.agent",
        platforms={"api": {}}
    )
    
    await flow_repo.set(config)
    
    result = await flow_repo.delete("test.repo.delete.flow")
    assert result is True
    
    found = await flow_repo.get("test.repo.delete.flow")
    assert found is None


@pytest.mark.asyncio
async def test_flow_repository_find_public(flow_repo):
    """Тест поиска публичных flows"""
    public_flow = FlowConfig(
        flow_id="test.repo.public",
        name="Public Flow",
        entry_point_agent="test.agent",
        platforms={"api": {}},
        is_public=True
    )
    await flow_repo.set(public_flow)
    
    private_flow = FlowConfig(
        flow_id="test.repo.private",
        name="Private Flow",
        entry_point_agent="test.agent",
        platforms={"api": {}},
        is_public=False
    )
    await flow_repo.set(private_flow)
    
    public_flows = await flow_repo.find_public(limit=100)
    
    public_ids = [f.flow_id for f in public_flows]
    assert "test.repo.public" in public_ids
