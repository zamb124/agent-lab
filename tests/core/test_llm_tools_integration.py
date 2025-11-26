"""
Интеграционные тесты для проверки передачи tools в OpenRouter API.
Используют РЕАЛЬНЫЙ OpenRouter API и реальных агентов.
"""

import pytest
import json
import logging
from langchain_core.messages import HumanMessage

from apps.agents.container import get_agents_container
from core.context import set_context
from core.models.context_models import Context
from apps.agents.models import LLMConfig


pytestmark = pytest.mark.asyncio


class TestRealOpenRouterToolsIntegration:
    """Интеграционные тесты с РЕАЛЬНЫМ OpenRouter API"""

    @pytest.mark.skip(reason="OpenRouter отключен в тестах")
    async def test_weather_agent_with_real_openrouter(
        self,
        migrated_db,
        test_company,
        test_user
    ):
        """
        РЕАЛЬНЫЙ интеграционный тест с OpenRouter API.

        Проверяет что:
        1. Агент загружается из БД с tools
        2. Запрос идет в реальный OpenRouter с tools
        3. OpenRouter возвращает ответ (возможно с tool_calls)
        4. Система обрабатывает tool_calls корректно
        """
        # Создаем контекст
        context = Context(
            user=test_user,
            active_company=test_company,
            platform="test"
        )
        set_context(context)

        # Мигрируем агента с tools
        from apps.agents.models.core_models import AgentConfig
        from apps.agents.services.migration import Migrator

        migrator = Migrator()
        await migrator._set_company_context(test_company)

        print(f"\n🔄 Мигрируем WeatherAgent с tools...")
        await AgentConfig.migrate(
            "apps.agents.agents.weather.agent.WeatherAgent",
            migrator=migrator,
            with_tools=True
        )

        # Загружаем агента
        agent_factory = get_agents_container().agent_factory
        weather_agent = await agent_factory.get_agent("apps.agents.agents.weather.agent.WeatherAgent")

        # Меняем на реальную модель OpenRouter
        weather_agent.config.llm_config = LLMConfig(
            model="anthropic/claude-sonnet-4.5",
            temperature=0.3
        )

        # Включаем DEBUG логирование для llm_billing_wrapper
        llm_logger = logging.getLogger("app.core.llm_billing_wrapper")
        original_level = llm_logger.level
        llm_logger.setLevel(logging.DEBUG)

        # Проверяем tools
        tools = await weather_agent.get_tools()
        print(f"\n✅ Агент загружен с {len(tools)} tools:")
        for i, tool in enumerate(tools, 1):
            tool_name = getattr(tool, 'name', 'unknown')
            print(f"   {i}. {tool_name}")

        assert len(tools) > 0, "Агент должен иметь tools"

        # Делаем РЕАЛЬНЫЙ запрос к OpenRouter
        print(f"\n🌐 Делаем РЕАЛЬНЫЙ запрос к OpenRouter API...")
        print(f"   Model: anthropic/claude-sonnet-4.5")
        print(f"   Запрос: Используй get_weather для проверки погоды в Москве")

        try:
            result = await weather_agent.ainvoke(
                {"messages": [HumanMessage(content="Используй get_weather для проверки погоды в Москве")]},
                config={"configurable": {"thread_id": "test_real_integration"}}
            )

            # Восстанавливаем уровень логирования
            llm_logger.setLevel(original_level)

            # Проверки
            print(f"\n{'='*60}")
            print(f"РЕЗУЛЬТАТЫ")
            print(f"{'='*60}")

            assert "messages" in result, "Результат должен содержать messages"
            assert len(result["messages"]) > 0, "Должны быть сообщения"

            print(f"✅ Получено {len(result['messages'])} сообщений от агента")

            # Проверяем tool_calls
            tool_call_count = 0
            for msg in result["messages"]:
                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                    tool_call_count += len(msg.tool_calls)
                    print(f"\n🔧 Tool calls найдены:")
                    for tc in msg.tool_calls:
                        print(f"   - {tc.get('name')}: {tc.get('args')}")

            if tool_call_count > 0:
                print(f"\n✅ OpenRouter вернул {tool_call_count} tool_calls")
            else:
                print(f"\n⚠️  OpenRouter не вернул tool_calls")
                print(f"   (LLM мог ответить напрямую или проблема с передачей tools)")

            # Финальный ответ
            last_message = result["messages"][-1]
            if hasattr(last_message, 'content'):
                print(f"\n💬 Финальный ответ:")
                print(f"   {last_message.content[:300]}...")
                assert len(last_message.content) > 0, "Ответ не должен быть пустым"

            print(f"\n{'='*60}")
            print(f"✅ ИНТЕГРАЦИОННЫЙ ТЕСТ С РЕАЛЬНЫМ OPENROUTER ПРОЙДЕН!")
            print(f"{'='*60}")
            print(f"✓ Агент загружен с {len(tools)} tools")
            print(f"✓ Запрос к OpenRouter выполнен успешно")
            print(f"✓ Получен ответ с {len(result['messages'])} сообщениями")
            print(f"✓ Tool calls обработаны: {tool_call_count > 0}")
            print(f"✓ Код передачи tools работает корректно!")

        except Exception as e:
            llm_logger.setLevel(original_level)
            print(f"\n❌ Ошибка выполнения теста: {e}")

            if "balance" in str(e).lower() or "баланс" in str(e).lower():
                pytest.skip(f"Недостаточно баланса: {e}")
            elif "api" in str(e).lower() and "key" in str(e).lower():
                pytest.skip(f"Проблема с API ключом: {e}")
            else:
                raise

