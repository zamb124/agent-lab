#!/usr/bin/env python3
"""
Тест для проверки работы @tool декоратора в StateGraph агенте
"""

import logging
import pytest
from apps.agents.services.tool_decorator import tool
from core.variables import get_state, set_state_in_context
from apps.agents.models.core_models import AgentConfig, AgentType
from core.context import set_context
from core.models.context_models import Context

logger = logging.getLogger(__name__)

@tool
def test_state_tool(message: str) -> str:
    """Тестовая функция, которая изменяет state"""
    logger.info(f"🔧 test_state_tool вызвана с: {message}")

    # Получаем текущий state
    state = get_state()
    logger.info(f"🔍 Получен state: {state}")

    # Изменяем state
    if state:
        if "test_data" not in state:
            state["test_data"] = []
        state["test_data"].append(message)
        logger.info(f"✅ Добавлено в state: {message}")

    return f"Обработано: {message}"

@pytest.mark.asyncio
async def test_stategraph_tool(test_user, test_company):
    """Тест работы tool в StateGraph контексте"""
    logger.info("🚀 Начинаем тест StateGraph tool")

    # Создаем контекст с обязательными полями
    context = Context(
        user=test_user,
        platform="test"
    )
    set_context(context)

    # Создаем mock state (как в StateGraph)
    mock_state = {
        "messages": [],
        "store": {},
        "test_data": []
    }

    # Устанавливаем state в контекст
    set_state_in_context(mock_state)

    # Создаем mock agent_config для StateGraph
    context.agent_config = AgentConfig(
        agent_id="test_stategraph",
        name="Test StateGraph Agent",
        type=AgentType.STATEGRAPH,
        prompt="Test agent"
    )
    set_context(context)

    logger.info(f"📋 Исходный state: {mock_state}")

    # Вызываем tool как StateGraph node (с state параметром)
    result = test_state_tool.invoke({"message": "Привет StateGraph!", "state": mock_state})

    logger.info(f"📋 Результат: {result}")
    logger.info(f"📋 Обновленный state: {mock_state}")

    # Проверяем, что state изменился
    assert "test_data" in mock_state, "test_data должен быть в state"
    assert len(mock_state["test_data"]) > 0, "test_data должен содержать данные"
    assert mock_state["test_data"][0] == "Привет StateGraph!", "Данные должны совпадать"

    # Проверяем, что результат - это delta для StateGraph
    assert isinstance(result, dict), "Результат должен быть словарем (delta)"
    assert "test_data" in result, "Delta должен содержать test_data"

    logger.info("✅ State успешно обновлен в StateGraph!")
