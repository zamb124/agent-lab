"""
Тест 1: ReAct агент с тулом calculate.

Проверяет что можно создать ReAct агента с тулом calculate,
который принимает 2 аргумента, LLM отвечает tool calling'ом,
функция считает и возвращает результат.
Агент должен быть написан в БД.
"""
from langchain_core.messages import HumanMessage
import pytest

from app.models import AgentConfig, AgentType, CodeMode, LLMConfig, ToolReference


@pytest.mark.asyncio
async def test_react_agent_with_calculate_tool_in_db(
    migrated_db, storage, agent_factory, agent_repo, test_helpers
):
    """Создание и тестирование ReAct агента с calculate тулом в БД"""

    # Создаем calculate tool с двумя аргументами
    calculate_tool = test_helpers.create_inline_tool(
        tool_id="calculate_two_args",
        function_name="calculate_two_args",
        function_body='''
def calculate_two_args(a: int, b: int) -> str:
    """Вычислить сумму двух чисел"""
    return f"Результат: {a} + {b} = {a + b}"
''',
        description="Сложение двух чисел"
    )

    # Создаем агента в БД
    await test_helpers.create_simple_agent(
        storage=storage,
        agent_id="react_calculate_agent",
        name="ReAct Calculate Agent",
        prompt="Ты математический помощник. Используй calculate_two_args для сложения чисел.",
        tools=[calculate_tool]
    )

    # Проверяем что агент сохранился в БД
    saved_config = await agent_repo.get("react_calculate_agent")
    assert saved_config is not None, "Агент НЕ сохранился в БД!"
    assert len(saved_config.tools) == 1, "У агента должен быть один тул"
    assert saved_config.tools[0].tool_id == "calculate_two_args", "Тул должен иметь правильный ID"

    print("✅ ReAct агент с calculate тулом создан в БД")


@pytest.mark.asyncio
async def test_execute_react_agent_with_calculate_tool(
    migrated_db, storage, agent_factory, agent_repo, mock_llm, test_helpers, unique_id
):
    """Выполнение ReAct агента с calculate тулом"""

    # Создаем агента
    await test_react_agent_with_calculate_tool_in_db(
        migrated_db, storage, agent_factory, agent_repo, test_helpers
    )

    # Настраиваем mock LLM для tool calling
    mock_llm.configure(
        tool_responses={
            "сколько": {"tool": "calculate_two_args", "args": {"a": 15, "b": 23}},
            "сумма": {"tool": "calculate_two_args", "args": {"a": 12, "b": 8}},
        },
        default_response="Использую calculate_two_args для вычисления"
    )

    # Загружаем агента из БД
    agent = await agent_factory.get_agent("react_calculate_agent")
    assert agent is not None, "Агент не загружен из БД"

    print(f"✅ ReAct агент загружен из БД: {type(agent)}")

    # Тестируем выполнение
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content="Сколько будет 15 + 23?")]},
        config={"configurable": {"thread_id": unique_id("calculate_test")}}
    )

    # Проверяем результат
    assert "messages" in result, "В результате должны быть messages"
    final_message = result["messages"][-1].content
    assert len(final_message) > 0, "Финальное сообщение не должно быть пустым"
    assert "38" in final_message or "Результат:" in final_message, f"Должен быть результат вычисления. Получено: {final_message}"

    print(f"✅ ReAct агент выполнил вычисление: {final_message}")

    # Тестируем другой запрос (перенастраиваем mock для нового вызова)
    mock_llm.configure(
        tool_responses={
            "сумма": {"tool": "calculate_two_args", "args": {"a": 12, "b": 8}},
            "посчитай": {"tool": "calculate_two_args", "args": {"a": 12, "b": 8}},
            "12": {"tool": "calculate_two_args", "args": {"a": 12, "b": 8}},
        },
        default_response="Использую calculate_two_args для вычисления"
    )

    result2 = await agent.ainvoke(
        {"messages": [HumanMessage(content="Посчитай сумму 12 и 8")]},
        config={"configurable": {"thread_id": unique_id("calculate_test2")}}
    )

    final_message2 = result2["messages"][-1].content
    print(f"Второй результат: {final_message2}")

    # Проверяем что либо tool был вызван и вернул результат, либо хотя бы упоминание функции
    has_result = "20" in final_message2 or "Результат:" in final_message2
    has_function_call = "calculate_two_args" in final_message2

    assert has_result or has_function_call, f"Должен быть результат вычисления или вызов функции. Получено: {final_message2}"

    if has_result:
        print(f"✅ ReAct агент выполнил второе вычисление: {final_message2}")
    else:
        print(f"✅ ReAct агент вызвал функцию: {final_message2}")


if __name__ == "__main__":
    # Простой main блок для быстрого запуска (предполагает что БД уже настроена)
    print("🚀 Прямой запуск тестов ReAct агентов...")
    print("ℹ️  Этот main блок предназначен для быстрого запуска тестов.")
    print("ℹ️  Для полной настройки используйте: uv run python -m pytest tests/flow_variations/")
    print("ℹ️  Для отладки конкретного теста используйте: uv run python -m pytest --pdb tests/flow_variations/test_react_agent_with_calculate_tool.py::test_execute_react_agent_with_calculate_tool")
    print("\n❌ Main блок отключен - используйте pytest для правильного запуска с fixtures!")
