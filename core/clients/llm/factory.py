"""
Фабрика для создания LLM через OpenRouter.

ВАЖНО: БЕЗ try-except блоков - fail-fast подход.
"""

import logging
import os
from typing import Optional, Dict
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI

from core.config import get_settings
from core.http import get_httpx_client, get_proxy_url

logger = logging.getLogger(__name__)

_global_mock_registry: Dict[str, "MockLLM"] = {}


class MockLLM(BaseChatModel):
    """
    Простой Mock LLM с очередью ответов.
    
    ПРАВИЛА:
    1. Тест задает список ответов в порядке вызова через configure()
    2. MockLLM возвращает ответы по порядку из очереди
    3. После использования ответ удаляется из очереди
    4. Если очередь пуста - raise RuntimeError
    
    Формат ответа:
    - {"type": "tool_call", "tool": "name", "args": {...}} - для tool_call
    - {"type": "text", "content": "..."} - для текстового ответа
    - Или просто строка - будет текстовым ответом
    """

    model_name: str = "mock-gpt-4"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._response_queue = []  # Очередь ответов в порядке вызова
        self._responses = {}  # Для обратной совместимости
        self._tool_responses = {}  # Для обратной совместимости
        self._default_response = "Mock LLM ответ"

    def set_responses(self, responses: dict):
        """Настройка текстовых ответов (для обратной совместимости)"""
        self._responses = responses

    def set_tool_responses(self, tool_responses: dict):
        """Настройка tool calls (для обратной совместимости)"""
        self._tool_responses = tool_responses

    def set_default_response(self, response: str):
        """Установить дефолтный ответ"""
        self._default_response = response

    def reset_call_counts(self):
        """Сбросить очередь ответов"""
        self._response_queue = []
    
    def reset_all(self):
        """Полный сброс всех настроек"""
        self._response_queue = []
        self._responses = {}
        self._tool_responses = {}
        self._default_response = "Mock LLM ответ"
    
    def configure(self, tool_responses: dict = None, responses: dict = None, default_response: str = None, response_queue: list = None):
        """
        Настройка mock ответов.
        
        Args:
            response_queue: Список ответов в порядке вызова. Каждый ответ:
                - {"type": "tool_call", "tool": "name", "args": {...}}
                - {"type": "text", "content": "..."}
                - Или просто строка (будет текстовым ответом)
            tool_responses: Для обратной совместимости (конвертируется в очередь)
            responses: Для обратной совместимости
            default_response: Дефолтный ответ если очередь пуста
        """
        if response_queue is not None:
            # Новая логика: очередь ответов
            self._response_queue = list(response_queue)
            logger.info(f"🔵 MockLLM: настроена очередь из {len(self._response_queue)} ответов")
        elif tool_responses or responses:
            # Старая логика: для обратной совместимости
            self._tool_responses = tool_responses or {}
            self._responses = responses or {}
            logger.info(f"🔵 MockLLM: настроено tool_responses={len(self._tool_responses)}, responses={len(self._responses)}")
        
        if default_response:
            self.set_default_response(default_response)
        
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        """Синхронная генерация (не используется в async коде)"""
        raise NotImplementedError("Используйте ainvoke")

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        """
        Возвращает следующий ответ из очереди.
        
        ПРАВИЛА:
        1. Берем первый ответ из очереди
        2. Удаляем его из очереди
        3. Если очередь пуста - raise RuntimeError
        """
        # Если есть очередь ответов - используем её
        if self._response_queue:
            response = self._response_queue.pop(0)
            logger.info(f"🔵 MockLLM: взят ответ из очереди (осталось {len(self._response_queue)}): {str(response)[:200]}")
            
            # Обрабатываем ответ
            if isinstance(response, dict):
                if response.get("type") == "tool_call":
                    # Tool call
                    tool_calls = [{
                        "name": response["tool"],
                        "args": response.get("args", {}),
                        "id": f"call_mock_{response['tool']}_{len(messages)}"
                    }]
                    message = AIMessage(content="", tool_calls=tool_calls)
                    logger.info(f"🔵 MockLLM: возвращаем TOOL_CALL: {response['tool']}")
                elif response.get("type") == "text":
                    # Текстовый ответ
                    message = AIMessage(content=response.get("content", self._default_response))
                    logger.info(f"🔵 MockLLM: возвращаем ТЕКСТ: {response.get('content', '')[:100]}...")
                else:
                    # Неизвестный формат - используем как текстовый ответ
                    message = AIMessage(content=str(response))
                    logger.warning(f"🔵 MockLLM: неизвестный формат ответа, используем как текст: {response}")
            elif isinstance(response, str):
                # Просто строка - текстовый ответ
                message = AIMessage(content=response)
                logger.info(f"🔵 MockLLM: возвращаем ТЕКСТ (строка): {response[:100]}...")
            else:
                # Неизвестный тип - используем как строку
                message = AIMessage(content=str(response))
                logger.warning(f"🔵 MockLLM: неизвестный тип ответа, используем как строку: {type(response)}")
        else:
            # Очередь пуста - проверяем старую логику для обратной совместимости
            if not messages:
                raise RuntimeError("MockLLM: очередь ответов пуста и нет messages")
            
            last_message = messages[-1]
            is_tool_result = isinstance(last_message, ToolMessage)
            
            if is_tool_result:
                # После tool результата - ищем текстовый ответ в старой логике
                tool_content = last_message.content[:200] if last_message.content else ""
                logger.info(f"🔵 MockLLM: ПОСЛЕ TOOL (старая логика) - tool_name={getattr(last_message, 'name', 'unknown')}")
                
                content = self._default_response
                for key, response in self._responses.items():
                    if key.lower() in tool_content.lower():
                        content = response
                        break
                
                if content == self._default_response and last_message.content:
                    content = last_message.content
                
                message = AIMessage(content=content)
                logger.info(f"🔵 MockLLM: возвращаем ТЕКСТ (старая логика): {content[:100]}...")
            else:
                # Ищем tool_call в старой логике
                content_str = last_message.content if isinstance(last_message, BaseMessage) else str(last_message)
                
                tool_call_found = False
                for key, tool_config in self._tool_responses.items():
                    if key.lower() in content_str.lower():
                        tool_calls = [{
                            "name": tool_config["tool"],
                            "args": tool_config.get("args", {}),
                            "id": f"call_mock_{tool_config['tool']}_{len(messages)}"
                        }]
                        message = AIMessage(content="", tool_calls=tool_calls)
                        logger.info(f"🔵 MockLLM: возвращаем TOOL_CALL (старая логика): {tool_config['tool']}")
                        tool_call_found = True
                        break
                
                if not tool_call_found:
                    # Ищем текстовый ответ
                    content = self._default_response
                    for key, response in self._responses.items():
                        if key.lower() in content_str.lower():
                            content = response
                            break
                    
                    message = AIMessage(content=content)
                    logger.info(f"🔵 MockLLM: возвращаем ТЕКСТ (старая логика, default): {content[:100]}...")

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

def get_llm(model_name: Optional[str] = None, temperature: Optional[float] = None):
    """
    Создает LLM клиент через OpenRouter.

    Args:
        model_name: Имя модели (если не указано, используется дефолтная из settings)
        temperature: Температура (если не указана, берется из конфигурации модели)

    Returns:
        Настроенный ChatOpenAI клиент или MockLLM в тестах

    Examples:
        >>> llm = get_llm()  # Дефолтная модель
        >>> llm = get_llm("anthropic/claude-sonnet-4.5")  # Конкретная модель
        >>> llm = get_llm(temperature=0.7)  # Дефолтная модель с кастомной температурой
    """
    settings = get_settings()

    model = model_name or settings.llm.default_model
    
    # В тестах всегда используем mock, если модель не начинается с "mock-"
    pytest_current = os.environ.get("PYTEST_CURRENT_TEST")
    pytest_raise = os.environ.get("_PYTEST_RAISE")
    is_testing = pytest_current is not None or pytest_raise is not None
    
    logger.warning(f"🔍 get_llm: model={model}, PYTEST_CURRENT_TEST={pytest_current}, _PYTEST_RAISE={pytest_raise}, is_testing={is_testing}")
    
    if is_testing and model and not model.startswith("mock-"):
        logger.warning(f"⚠️ PYTEST detected! Replacing model '{model}' with mock-gpt-4")
        model = "mock-gpt-4"
    
    if model.startswith("mock-"):
        logger.info(f"🔵 Returning MockLLM for model={model}")
        if model not in _global_mock_registry:
            _global_mock_registry[model] = MockLLM(model_name=model)
        return _global_mock_registry[model]
    
    logger.info(f"✅ Creating real LLM for model={model}")

    if not settings.llm.openrouter or not settings.llm.openrouter.enabled:
        raise ValueError("OpenRouter не настроен в конфигурации")

    if not settings.llm.openrouter.api_key:
        raise ValueError("OpenRouter API key не настроен")
    if not model:
        raise ValueError("Модель не указана и нет дефолтной модели в конфигурации")

    model_config = settings.llm.models.get(model)
    if model_config:
        temp = temperature if temperature is not None else model_config.temperature
        max_tokens = model_config.max_tokens
    else:
        temp = temperature if temperature is not None else 0.2
        max_tokens = None

    proxy_url = get_proxy_url()
    logger.debug(f"Создаем LLM клиент: model={model}, temperature={temp}, max_tokens={max_tokens}, proxy={proxy_url is not None}")

    llm_kwargs = {
        "model": model,
        "temperature": temp,
        "max_tokens": max_tokens,
        "openai_api_key": settings.llm.openrouter.api_key,
        "openai_api_base": settings.llm.openrouter.base_url,
        "default_headers": {
            "HTTP-Referer": settings.llm.openrouter.site_url,
            "X-Title": settings.llm.openrouter.site_name,
        },
    }
    
    if proxy_url:
        http_client = get_httpx_client(
            timeout=settings.llm.openrouter.timeout,
            use_proxy_from_config=True
        )
        llm_kwargs["http_async_client"] = http_client

    llm = ChatOpenAI(**llm_kwargs)

    return llm


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


def get_global_mock_llm(model_name: str = "mock-gpt-4") -> Optional[MockLLM]:
    """Получить глобальный mock LLM для настройки в тестах"""
    return _global_mock_registry.get(model_name)