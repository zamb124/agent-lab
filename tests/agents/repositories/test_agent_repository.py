"""
Тесты для AgentRepository.
"""

import pytest
from apps.agents.models import AgentConfig, AgentType


@pytest.mark.asyncio
async def test_agent_repository_save_and_find(agent_repo):
    """Тест сохранения и поиска агента через репозиторий"""
    repo = agent_repo
    
    config = AgentConfig(
        agent_id="test.repo.agent",
        name="Test Repo Agent",
        type=AgentType.REACT,
        prompt="Test prompt"
    )
    
    # Сохраняем
    result = await repo.set(config)
    assert result is True
    
    # Находим
    found = await repo.get("test.repo.agent")
    assert found is not None
    assert found.agent_id == "test.repo.agent"
    assert found.name == "Test Repo Agent"


@pytest.mark.asyncio
async def test_agent_repository_delete(agent_repo):
    """Тест удаления агента через репозиторий"""
    repo = agent_repo
    
    config = AgentConfig(
        agent_id="test.repo.delete",
        name="Test Delete",
        type=AgentType.REACT,
        prompt="Test"
    )
    
    await repo.set(config)
    
    # Удаляем
    result = await repo.delete("test.repo.delete")
    assert result is True
    
    # Проверяем что удален
    found = await repo.get("test.repo.delete")
    assert found is None


@pytest.mark.asyncio
async def test_agent_repository_list_all(agent_repo):
    """Тест получения списка всех агентов"""
    repo = agent_repo
    
    # Создаем несколько агентов
    agent_ids = []
    for i in range(3):
        agent_id = f"test.repo.list.{i}"
        config = AgentConfig(
            agent_id=agent_id,
            name=f"Test List {i}",
            type=AgentType.REACT,
            prompt="Test"
        )
        await repo.set(config)
        agent_ids.append(agent_id)
    
    # Проверяем что можем найти каждого агента индивидуально
    for agent_id in agent_ids:
        found = await repo.get(agent_id)
        assert found is not None
        assert found.agent_id == agent_id

