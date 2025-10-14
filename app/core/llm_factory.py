"""
Фабрика для создания LLM через OpenRouter.
"""

import logging
from typing import Optional, Dict
from langchain_core.language_models import BaseLLM, BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.core.config import get_settings

logger = logging.getLogger(__name__)


# Глобальный реестр mock моделей для тестов
_global_mock_registry: Dict[str, "MockLLM"] = {}


class MockLLM(BaseChatModel):
    """Mock LLM для тестирования с поддержкой tool calls"""
    
    model_name: str = "mock-gpt-4"
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._responses = {}
        self._tool_responses = {}
        self._default_response = "Mock LLM ответ"
        self._call_count = {}  # Счетчик вызовов для каждого ключа
    
    def set_responses(self, responses: dict):
        """Настройка mock ответов для разных запросов"""
        self._responses = responses
    
    def set_tool_responses(self, tool_responses: dict):
        """
        Настройка mock ответов с tool calls.
        
        Example:
            mock.set_tool_responses({
                "сложи": {"tool": "add_tool", "args": {"a": 15, "b": 23}},
                "погода": {"tool": "weather_tool", "args": {"city": "Москва"}}
            })
        
        Логика:
        - При первом вызове с ключом -> возвращает tool_call
        - При втором вызове с тем же ключом -> возвращает текстовый ответ из _responses или default
        """
        self._tool_responses = tool_responses
    
    def set_default_response(self, response: str):
        """Установить дефолтный ответ"""
        self._default_response = response
    
    def reset_call_counts(self):
        """Сбросить счетчики вызовов (для изоляции тестов)"""
        self._call_count = {}
    
    def configure(self, tool_responses: dict = None, responses: dict = None, default_response: str = None):
        """
        Удобный метод для настройки всех mock ответов сразу.
        
        Args:
            tool_responses: Словарь с tool calls
            responses: Словарь с текстовыми ответами
            default_response: Дефолтный ответ
            
        Returns:
            self для цепочки вызовов
        """
        if tool_responses:
            self.set_tool_responses(tool_responses)
        if responses:
            self.set_responses(responses)
        if default_response:
            self.set_default_response(default_response)
        return self
    
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        """Синхронная генерация (не используется в async коде)"""
        raise NotImplementedError("Используйте ainvoke")
    
    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        """Асинхронная генерация с поддержкой tool calls через счетчик вызовов"""
        from langchain_core.messages import ToolMessage
        
        logger.debug(f"MockLLM._agenerate вызван, messages count: {len(messages) if messages else 0}")
        
        if not messages:
            content = self._default_response
            message = AIMessage(content=content)
            logger.debug("MockLLM: нет messages, возвращаем default")
        else:
            # Проверяем есть ли ToolMessage - если да, значит tool выполнился
            has_tool_message = any(isinstance(msg, ToolMessage) for msg in messages)
            
            if has_tool_message:
                # После tool возвращаем текстовый ответ
                last_tool_msg = next((msg for msg in reversed(messages) if isinstance(msg, ToolMessage)), None)
                if last_tool_msg and last_tool_msg.content:
                    message = AIMessage(content=last_tool_msg.content)
                    logger.debug(f"MockLLM: возвращаем результат tool: {last_tool_msg.content[:50]}...")
                else:
                    message = AIMessage(content=self._default_response)
                    logger.debug("MockLLM: нет content в ToolMessage, возвращаем default")
            else:
                # Нет ToolMessage - проверяем нужен ли tool call
                last_message = messages[-1]
                content_str = last_message.content if isinstance(last_message, BaseMessage) else str(last_message)
                
                # Проверяем tool responses с использованием счетчика
                tool_call_found = False
                for key, tool_config in self._tool_responses.items():
                    if key.lower() in content_str.lower():
                        # Получаем счетчик для этого ключа
                        call_count = self._call_count.get(key, 0)
                        self._call_count[key] = call_count + 1
                        
                        if call_count == 0:
                            # Первый вызов - возвращаем tool_call
                            tool_calls = [{
                                "name": tool_config["tool"],
                                "args": tool_config.get("args", {}),
                                "id": f"call_mock_{tool_config['tool']}_{call_count}",
                                "type": "tool_call"
                            }]
                            message = AIMessage(content="", tool_calls=tool_calls)
                            logger.debug(f"MockLLM: [вызов #{call_count}] вызываем tool {tool_config['tool']} для '{key}'")
                        else:
                            # Второй и последующие - возвращаем текст
                            content = self._responses.get(key, self._default_response)
                            message = AIMessage(content=content)
                            logger.debug(f"MockLLM: [вызов #{call_count}] возвращаем текст для '{key}'")
                        
                        tool_call_found = True
                        break
                
                if not tool_call_found:
                    # Ищем обычный текстовый ответ
                    content = self._default_response
                    for key, response in self._responses.items():
                        if key.lower() in content_str.lower():
                            content = response
                            logger.debug(f"MockLLM: нашли текстовый ответ для '{key}'")
                            break
                    message = AIMessage(content=content)
                    if content == self._default_response:
                        logger.debug(f"MockLLM: используем default response")
        
        generation = ChatGeneration(message=message)
        
        return ChatResult(
            generations=[generation],
            llm_output={"model": self.model_name}
        )
    
    @property
    def _llm_type(self) -> str:
        return "mock"
    
    def bind_tools(self, tools, **kwargs):
        """Привязывает tools к MockLLM (просто возвращаем self, tools уже известны LangGraph)"""
        return self


def get_global_mock_llm(model_name: str = "mock-gpt-4") -> Optional[MockLLM]:
    """Получить глобальный mock LLM для настройки в тестах"""
    return _global_mock_registry.get(model_name)


def setup_mock_responses(
    responses: Optional[dict] = None, 
    tool_responses: Optional[dict] = None,
    default_response: Optional[str] = None, 
    model_name: str = "mock-gpt-4"
):
    """
    Удобная функция для настройки mock ответов в тестах.
    
    Args:
        responses: Словарь с ключами (подстроки в вопросе) и текстовыми ответами
        tool_responses: Словарь с ключами и tool calls. 
                       Формат: {"ключ": {"tool": "tool_name", "args": {...}}}
        default_response: Дефолтный ответ если ключ не найден
        model_name: Название mock модели
        
    Example:
        setup_mock_responses(
            tool_responses={
                "сложи": {"tool": "add_tool", "args": {"a": 15, "b": 23}},
            },
            responses={
                "привет": "Привет! Я готов помочь."
            },
            default_response="Я mock LLM"
        )
    """
    # Создаем mock если его еще нет
    get_llm(model_name)
    
    # Получаем и настраиваем mock
    mock_llm = get_global_mock_llm(model_name)
    if mock_llm:
        # ВАЖНО: сбрасываем счетчики перед каждым тестом
        mock_llm.reset_call_counts()
        
        if responses:
            mock_llm.set_responses(responses)
        if tool_responses:
            mock_llm.set_tool_responses(tool_responses)
        if default_response:
            mock_llm.set_default_response(default_response)
        
        text_count = len(responses) if responses else 0
        tool_count = len(tool_responses) if tool_responses else 0
        logger.info(
            f"Mock LLM настроен: {text_count} текстовых ответов, "
            f"{tool_count} tool calls, default={default_response is not None}"
        )


def get_llm(model: Optional[str] = None, **kwargs) -> BaseLLM:
    """
    Создает LLM через OpenRouter или Mock для тестов.

    Args:
        model: ID модели в формате "provider/model" (например, "anthropic/claude-sonnet-4.5")
        **kwargs: Дополнительные параметры (temperature, max_tokens, etc.)

    Returns:
        Экземпляр LLM с биллингом или Mock для тестов
    """
    settings = get_settings()
    model_name = model or settings.llm.default_model
    
    # Mock режим для тестов - ВСЕГДА возвращаем один и тот же экземпляр
    if model_name.startswith("mock-"):
        logger.debug(f"Возвращаем глобальный Mock LLM: {model_name}")
        # Создаем глобальный mock один раз и всегда возвращаем его
        if model_name not in _global_mock_registry:
            logger.info(f"Создаем новый Mock LLM: {model_name}")
            _global_mock_registry[model_name] = MockLLM(model_name=model_name)
        # ВАЖНО: всегда возвращаем тот же самый экземпляр
        return _global_mock_registry[model_name]
    
    # Проверяем что OpenRouter включен для реальных моделей
    if not hasattr(settings.llm, 'openrouter'):
        raise ValueError("OpenRouter не настроен в конфигурации")
    
    openrouter_config = settings.llm.openrouter

    if not openrouter_config.enabled:
        raise ValueError("OpenRouter отключен в конфигурации. Используйте mock- модели для тестов.")

    # Получаем конфигурацию модели
    model_config = settings.llm.models.get(model_name)
    
    # Собираем параметры для LLM
    llm_kwargs = {
        "base_url": openrouter_config.base_url,
        "api_key": openrouter_config.api_key,
        "model": model_name,
        "timeout": openrouter_config.timeout,
        "max_retries": openrouter_config.max_retries,
    }

    # Добавляем настройки из конфигурации модели
    if model_config:
        if model_config.temperature is not None:
            llm_kwargs["temperature"] = model_config.temperature
        if model_config.max_tokens is not None:
            llm_kwargs["max_tokens"] = model_config.max_tokens
    
    # Добавляем OpenRouter-специфичные headers для статистики
    llm_kwargs["default_headers"] = {
        "HTTP-Referer": openrouter_config.site_url,
        "X-Title": openrouter_config.site_name,
    }

    # Переопределяем параметрами от агента
    for key, value in kwargs.items():
        if key not in ["api_key", "base_url"]:
            llm_kwargs[key] = value

    logger.info(f"Создаем LLM через OpenRouter: {model_name}")

    from app.core.llm_billing_wrapper import ChatOpenAIWithBilling
    return ChatOpenAIWithBilling(**llm_kwargs)
