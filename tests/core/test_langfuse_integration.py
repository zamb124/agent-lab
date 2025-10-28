"""
Тесты для интеграции Langfuse
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from langchain_core.messages import HumanMessage

from app.core.langfuse_init import (
    get_langfuse,
    get_langfuse_callback,
    flush_langfuse,
    shutdown_langfuse
)
from app.core.config import get_settings
from app.agents.base import BaseAgent
from app.models import AgentConfig, AgentType


class TestLangfuseIntegration:
    """Тесты интеграции Langfuse"""

    @pytest.fixture
    def mock_langfuse_config(self):
        """Мок конфигурации Langfuse"""
        return {
            "enabled": True,
            "host": "http://localhost:3000",
            "public_key": "pk-lf-test",
            "secret_key": "sk-lf-test",
            "sample_rate": 1.0,
            "flush_interval": 1,
            "flush_at": 1
        }

    @pytest.fixture
    def mock_disabled_langfuse_config(self):
        """Мок отключенной конфигурации Langfuse"""
        return {
            "enabled": False,
            "host": None,
            "public_key": None,
            "secret_key": None
        }

    def test_get_langfuse_disabled(self, mock_disabled_langfuse_config):
        """Тест получения Langfuse при отключенной конфигурации"""
        with patch('app.core.langfuse_init.get_settings') as mock_settings:
            mock_settings.return_value.langfuse = Mock(**mock_disabled_langfuse_config)

            result = get_langfuse()
            assert result is None

    def test_get_langfuse_enabled(self, mock_langfuse_config):
        """Тест получения Langfuse при включенной конфигурации"""
        with patch('app.core.langfuse_init.get_settings') as mock_settings, \
             patch('app.core.langfuse_init.Langfuse') as mock_langfuse_class:

            mock_settings.return_value.langfuse = Mock(**mock_langfuse_config)
            mock_instance = Mock()
            mock_langfuse_class.return_value = mock_instance

            result = get_langfuse()
            assert result == mock_instance

            # Проверяем что Langfuse был создан с правильными параметрами
            mock_langfuse_class.assert_called_once_with(
                public_key="pk-lf-test",
                secret_key="sk-lf-test",
                host="http://localhost:3000",
                sample_rate=1.0,
                flush_interval=1,
                flush_at=1
            )

    def test_get_langfuse_callback_disabled(self, mock_disabled_langfuse_config):
        """Тест получения callback при отключенном Langfuse"""
        with patch('app.core.langfuse_init.get_settings') as mock_settings:
            mock_settings.return_value.langfuse = Mock(**mock_disabled_langfuse_config)

            result = get_langfuse_callback()
            assert result is None

    def test_get_langfuse_callback_enabled(self, mock_langfuse_config):
        """Тест получения callback при включенном Langfuse"""
        with patch('app.core.langfuse_init.get_settings') as mock_settings, \
             patch('app.core.langfuse_init.Langfuse') as mock_langfuse_class, \
             patch('app.core.langfuse_init.CallbackHandler') as mock_callback_class:

            mock_settings.return_value.langfuse = Mock(**mock_langfuse_config)
            mock_langfuse_instance = Mock()
            mock_langfuse_class.return_value = mock_langfuse_instance
            mock_callback_instance = Mock()
            mock_callback_class.return_value = mock_callback_instance

            result = get_langfuse_callback()
            assert result == mock_callback_instance

    def test_flush_langfuse_no_instance(self):
        """Тест flush при отсутствии экземпляра Langfuse"""
        # Сброс глобального состояния
        import app.core.langfuse_init as lf_init
        lf_init._langfuse_instance = None

        # Flush не должен вызывать ошибки
        flush_langfuse()

    def test_flush_langfuse_with_instance(self):
        """Тест flush с существующим экземпляром Langfuse"""
        mock_instance = Mock()
        import app.core.langfuse_init as lf_init
        lf_init._langfuse_instance = mock_instance

        flush_langfuse()

        mock_instance.flush.assert_called_once()

    def test_shutdown_langfuse(self):
        """Тест завершения работы Langfuse"""
        mock_instance = Mock()
        import app.core.langfuse_init as lf_init
        lf_init._langfuse_instance = mock_instance

        shutdown_langfuse()

        mock_instance.flush.assert_called_once()
        assert lf_init._langfuse_instance is None

    @pytest.mark.asyncio
    async def test_agent_with_langfuse_callback(self, mock_langfuse_config):
        """Тест интеграции Langfuse callback в BaseAgent"""
        with patch('app.core.langfuse_init.get_settings') as mock_settings, \
             patch('app.core.langfuse_init.Langfuse') as mock_langfuse_class, \
             patch('app.core.langfuse_init.CallbackHandler') as mock_callback_class, \
             patch('app.agents.base.get_checkpointer') as mock_checkpointer, \
             patch('app.agents.base.get_container') as mock_container:

            # Настройка моков
            mock_settings.return_value.langfuse = Mock(**mock_langfuse_config)
            mock_langfuse_instance = Mock()
            mock_langfuse_class.return_value = mock_langfuse_instance
            mock_callback_instance = Mock()
            mock_callback_class.return_value = mock_callback_instance

            # Мок агента
            agent_config = AgentConfig(
                agent_id="test_agent",
                name="Test Agent",
                type=AgentType.REACT,
                prompt="You are a test agent",
                tools=[]
            )

            # Мок checkpointer и container
            mock_checkpointer_instance = AsyncMock()
            mock_checkpointer.return_value = mock_checkpointer_instance
            mock_container_instance = Mock()
            mock_container.return_value = mock_container_instance
            mock_container_instance.get_agent_factory.return_value = Mock()

            # Мок graph
            mock_graph = AsyncMock()
            mock_graph.aget_state.return_value = None

            # Создание агента
            agent = BaseAgent(agent_config)
            agent.compile_graph = Mock(return_value=mock_graph)

            # Вызов ainvoke
            input_data = {"messages": [HumanMessage(content="test")], "store": {}}
            result = await agent.ainvoke(input_data)

            # Проверяем что callback был добавлен
            call_args = mock_graph.ainvoke.call_args
            run_config = call_args[1]['config']  # kwargs
            assert 'callbacks' in run_config
            assert mock_callback_instance in run_config['callbacks']

    @pytest.mark.asyncio
    async def test_llm_factory_with_langfuse_callback(self, mock_langfuse_config):
        """Тест интеграции Langfuse callback в LLM factory"""
        with patch('app.core.langfuse_init.get_settings') as mock_settings, \
             patch('app.core.langfuse_init.Langfuse') as mock_langfuse_class, \
             patch('app.core.langfuse_init.CallbackHandler') as mock_callback_class, \
             patch('app.core.llm_factory.get_settings') as mock_llm_settings, \
             patch('app.core.llm_factory.ChatOpenAIWithBilling') as mock_chat_openai:

            # Настройка моков
            mock_settings.return_value.langfuse = Mock(**mock_langfuse_config)
            mock_langfuse_instance = Mock()
            mock_langfuse_class.return_value = mock_langfuse_instance
            mock_callback_instance = Mock()
            mock_callback_class.return_value = mock_callback_instance

            # Мок настроек LLM
            mock_llm_config = Mock()
            mock_llm_config.enabled = True
            mock_llm_config.base_url = "https://openrouter.ai/api/v1"
            mock_llm_config.api_key = "test-key"
            mock_llm_config.timeout = 60
            mock_llm_config.max_retries = 3

            mock_openrouter_config = Mock()
            mock_openrouter_config.enabled = True
            mock_openrouter_config.base_url = "https://openrouter.ai/api/v1"
            mock_openrouter_config.api_key = "test-key"
            mock_openrouter_config.timeout = 60
            mock_openrouter_config.max_retries = 3
            mock_openrouter_config.site_url = "https://example.com"
            mock_openrouter_config.site_name = "Test"

            mock_llm_settings_instance = Mock()
            mock_llm_settings_instance.llm.models = {}
            mock_llm_settings_instance.llm.openrouter = mock_openrouter_config
            mock_llm_settings_instance.llm.default_model = "gpt-4"
            mock_llm_settings.return_value = mock_llm_settings_instance

            mock_llm_instance = Mock()
            mock_chat_openai.return_value = mock_llm_instance

            # Вызов get_llm
            from app.core.llm_factory import get_llm
            result = get_llm("gpt-4")

            # Проверяем что ChatOpenAIWithBilling был вызван с callbacks
            call_args = mock_chat_openai.call_args
            kwargs = call_args[1]

            assert 'callbacks' in kwargs
            assert mock_callback_instance in kwargs['callbacks']
            assert result == mock_llm_instance

    def test_langfuse_config_in_settings(self):
        """Тест что LangfuseConfig доступен в настройках"""
        settings = get_settings()
        assert hasattr(settings, 'langfuse')
        assert hasattr(settings.langfuse, 'enabled')
        assert hasattr(settings.langfuse, 'host')
        assert hasattr(settings.langfuse, 'public_key')
        assert hasattr(settings.langfuse, 'secret_key')
        assert hasattr(settings.langfuse, 'sample_rate')
        assert hasattr(settings.langfuse, 'flush_interval')
        assert hasattr(settings.langfuse, 'flush_at')

    def test_langfuse_config_defaults(self):
        """Тест дефолтных значений LangfuseConfig"""
        from app.core.config import LangfuseConfig

        config = LangfuseConfig()
        assert config.enabled is False
        assert config.host is None
        assert config.public_key is None
        assert config.secret_key is None
        assert config.sample_rate == 1.0
        assert config.flush_interval == 1
        assert config.flush_at == 1
