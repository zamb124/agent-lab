"""
Тесты для ContextWindowManager и автосуммаризации диалога.
"""

import pytest
import logging
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from apps.agents.services.context_window_manager import ContextWindowManager
from core.context import set_context
from core.models import Context

logger = logging.getLogger(__name__)
pytestmark = pytest.mark.asyncio


class TestContextWindowManager:
    """Unit тесты для ContextWindowManager"""
    
    async def test_count_tokens(self):
        """Проверка подсчета токенов с учетом content, tool_calls и т.д."""
        manager = ContextWindowManager()
        
        messages = [
            SystemMessage(content="Ты помощник" * 100),  # ~1200 символов
            HumanMessage(content="Привет" * 50),  # ~300 символов
            AIMessage(content="Здравствуйте" * 50),  # ~600 символов
        ]
        
        token_count = manager._count_tokens(messages)
        
        # С коэффициентом 2.5: (1200+300+600)/2.5 + 3*10 = 840 + 30 = 870
        assert token_count > 0
        assert 700 < token_count < 1000  # Консервативная оценка дает больше токенов
    
    async def test_no_summarization_under_threshold(self, test_company, test_user):
        """Суммаризация НЕ происходит если контекст в норме"""
        context = Context(user=test_user, active_company=test_company, platform="test")
        set_context(context)
        
        manager = ContextWindowManager()
        
        llm_config = {
            "model": "mock-gpt-4",
            "context_window": 10000,
            "summarization_threshold": 0.8,
            "enable_auto_summarization": True
        }
        
        messages = [
            SystemMessage(content="Ты помощник"),
            HumanMessage(content="Привет"),
            AIMessage(content="Здравствуйте"),
        ]
        
        run_config = {"configurable": {"thread_id": "test"}}
        
        result, was_summarized = await manager.check_and_summarize_if_needed(
            messages=messages,
            llm_config=llm_config,
            config=run_config,
            update_checkpoint=False
        )
        
        assert was_summarized is False
        assert len(result) == len(messages)
    
    async def test_summarization_disabled(self, test_company, test_user):
        """Суммаризация не происходит если отключена в конфиге"""
        context = Context(user=test_user, active_company=test_company, platform="test")
        set_context(context)
        
        manager = ContextWindowManager()
        
        llm_config = {
            "model": "mock-gpt-4",
            "context_window": 100,
            "enable_auto_summarization": False
        }
        
        messages = [SystemMessage(content="Системный промпт")]
        for i in range(50):
            messages.append(HumanMessage(content=f"Сообщение {i} " * 20))
        
        run_config = {"configurable": {"thread_id": "test"}}
        
        result, was_summarized = await manager.check_and_summarize_if_needed(
            messages=messages,
            llm_config=llm_config,
            config=run_config,
            update_checkpoint=False
        )
        
        assert was_summarized is False
        assert len(result) == len(messages)
    
    async def test_get_context_window_priority(self):
        """Проверка приоритета: llm_config > глобальная конфигурация > исключение"""
        manager = ContextWindowManager()
        
        # Приоритет 1: из llm_config
        window = manager._get_context_window(
            "anthropic/claude-sonnet-4.5",
            {"context_window": 50000}
        )
        assert window == 50000
        
        # Приоритет 2: из conf.json
        window = manager._get_context_window(
            "anthropic/claude-sonnet-4.5",
            {"model": "anthropic/claude-sonnet-4.5"}
        )
        assert window == 200000
        
        # Неизвестная модель - исключение
        with pytest.raises(ValueError, match="не найден"):
            manager._get_context_window("unknown/model", {})
    
    async def test_error_on_missing_thread_id(self):
        """Исключение при попытке обновить checkpoint без thread_id"""
        manager = ContextWindowManager()
        
        with pytest.raises(ValueError, match="thread_id обязателен"):
            await manager._update_checkpoint_messages(
                {"configurable": {}},
                [HumanMessage(content="test")]
            )
