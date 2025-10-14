"""
Тесты для FlowRepository.
"""

import pytest
from app.db.repositories import FlowRepository
from app.models import FlowConfig


@pytest.mark.asyncio
async def test_flow_repository_save_and_find(storage):
    """Тест сохранения и поиска flow через репозиторий"""
    repo = FlowRepository(storage)
    
    config = FlowConfig(
        flow_id="test.repo.flow",
        name="Test Repo Flow",
        entry_point_agent="test.agent",
        platforms={"api": {}}
    )
    
    # Сохраняем
    result = await repo.set(config)
    assert result is True
    
    # Находим
    found = await repo.get("test.repo.flow")
    assert found is not None
    assert found.flow_id == "test.repo.flow"
    assert found.name == "Test Repo Flow"


@pytest.mark.asyncio
async def test_flow_repository_delete(storage):
    """Тест удаления flow через репозиторий"""
    repo = FlowRepository(storage)
    
    config = FlowConfig(
        flow_id="test.repo.delete.flow",
        name="Test Delete Flow",
        entry_point_agent="test.agent",
        platforms={"api": {}}
    )
    
    await repo.set(config)
    
    # Удаляем
    result = await repo.delete("test.repo.delete.flow")
    assert result is True
    
    # Проверяем что удален
    found = await repo.get("test.repo.delete.flow")
    assert found is None


@pytest.mark.asyncio
async def test_flow_repository_find_public(storage):
    """Тест поиска публичных flows"""
    repo = FlowRepository(storage)
    
    # Создаем публичный flow
    public_flow = FlowConfig(
        flow_id="test.repo.public",
        name="Public Flow",
        entry_point_agent="test.agent",
        platforms={"api": {}},
        is_public=True
    )
    await repo.set(public_flow)
    
    # Создаем приватный flow
    private_flow = FlowConfig(
        flow_id="test.repo.private",
        name="Private Flow",
        entry_point_agent="test.agent",
        platforms={"api": {}},
        is_public=False
    )
    await repo.set(private_flow)
    
    # Получаем публичные
    public_flows = await repo.find_public(limit=100)
    
    # Проверяем что публичный flow есть
    public_ids = [f.flow_id for f in public_flows]
    assert "test.repo.public" in public_ids

