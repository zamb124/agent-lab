"""
Фабрика для создания LLM экземпляров на основе конфигурации.
"""

import asyncio
import logging
from typing import Optional
from langchain_core.language_models import BaseLLM, BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatResult, ChatGeneration

from app.core.config import get_settings, LLMProviderConfig

# Условные импорты для опциональных провайдеров
try:
    from langchain_anthropic import ChatAnthropic
except ImportError:
    ChatAnthropic = None

try:
    from langchain_community.llms import Ollama
except ImportError:
    Ollama = None

logger = logging.getLogger(__name__)

# Глобальный мок для тестов
_global_mock_llm = None


def get_llm(
    provider: Optional[str] = None, model: Optional[str] = None, **kwargs
) -> BaseLLM:
    """
    Создает экземпляр LLM на основе конфигурации.

    Args:
        provider: Имя провайдера (openai, anthropic, yandex, etc.). Если None, используется default_provider
        model: Имя модели. Если None, используется default_model провайдера
        **kwargs: Дополнительные параметры (temperature, api_key, etc.)

    Returns:
        Экземпляр LLM
    """

    # Получаем актуальные настройки
    settings = get_settings()

    provider_name = provider or settings.llm.default_provider
    model_name = model

    # Получаем конфигурацию провайдера из глобальных настроек
    provider_config = settings.llm.providers.get(provider_name)
    if not provider_config:
        raise ValueError(f"Провайдер {provider_name} не найден в конфигурации")

    if not provider_config.enabled:
        raise ValueError(f"Провайдер {provider_name} отключен")

    # Используем модель из параметров или дефолтную для провайдера
    final_model = model_name or provider_config.default_model

    try:
        # Создаем базовый LLM
        if provider_name == "openai":
            llm = _create_openai_llm(provider_config, final_model, **kwargs)
        elif provider_name == "anthropic":
            llm = _create_anthropic_llm(provider_config, final_model)
        elif provider_name == "yandex":
            llm = _create_yandex_llm(provider_config, final_model)
        elif provider_name == "ollama":
            llm = _create_ollama_llm(provider_config, final_model)
        elif provider_name == "gemini":
            llm = _create_gemini_llm(provider_config, final_model, **kwargs)
        elif provider_name == "mock":
            llm = _create_mock_llm(provider_config, final_model)
            logger.debug(f"🔥 Возвращаем MOCK LLM без биллинга: {type(llm)}")
            return llm
        else:
            raise ValueError(f"Неподдерживаемый провайдер LLM: {provider_name}")
        
        logger.debug(f"🔥 Возвращаем LLM: {type(llm)} для {provider_name}:{final_model}")
        return llm

    except Exception as e:
        logger.error(f"Ошибка создания LLM {provider_name}: {e}")
        raise


def _create_openai_llm(
    provider_config: LLMProviderConfig, model: str, **agent_kwargs
) -> BaseLLM:
    """Создает OpenAI LLM, объединяя глобальные настройки с параметрами агента"""
    try:
        # Начинаем с глобальных настроек провайдера (без timeout и max_retries)
        kwargs = {
            "model": model,
            "temperature": provider_config.default_temperature,
            # "timeout": provider_config.timeout,  # ВРЕМЕННО ОТКЛЮЧЕНО
            # "max_retries": provider_config.max_retries,  # ВРЕМЕННО ОТКЛЮЧЕНО
        }

        # ВСЕГДА используем глобальные api_key и base_url
        if provider_config.api_key:
            # Используем openai_api_key вместо api_key для совместимости с LangChain
            kwargs["openai_api_key"] = provider_config.api_key
        if provider_config.base_url:
            kwargs["openai_api_base"] = provider_config.base_url

        # Добавляем специфичные настройки модели из глобальной конфигурации
        if hasattr(provider_config.models, 'get'):
            model_config = provider_config.models.get(model, {})
            if "max_tokens" in model_config:
                kwargs["max_tokens"] = model_config["max_tokens"]

        # Переопределяем параметрами от агента (но НЕ api_key и base_url!)
        for key, value in agent_kwargs.items():
            if key not in [
                "api_key",
                "base_url",
            ]:  # Эти параметры ВСЕГДА из глобальной конфигурации
                kwargs[key] = value

        from .llm_billing_wrapper import ChatOpenAIWithBilling
        return ChatOpenAIWithBilling(provider="openai", **kwargs)

    except ImportError:
        raise ImportError(
            "Для использования OpenAI установите: pip install langchain-openai"
        )


def _create_anthropic_llm(provider_config: LLMProviderConfig, model: str) -> BaseLLM:
    """Создает Anthropic LLM"""
    if ChatAnthropic is None:
        raise ImportError("langchain_anthropic не установлен. Установите: pip install langchain-anthropic")
    
    try:
        kwargs = {
            "model": model,
            "temperature": provider_config.default_temperature,
            "timeout": provider_config.timeout,
            "max_retries": provider_config.max_retries,
        }

        if provider_config.api_key:
            kwargs["api_key"] = provider_config.api_key

        # Добавляем специфичные настройки модели
        model_config = provider_config.models.get(model, {})
        if "max_tokens" in model_config:
            kwargs["max_tokens"] = model_config["max_tokens"]

        return ChatAnthropic(**kwargs)

    except ImportError:
        raise ImportError(
            "Для использования Anthropic установите: pip install langchain-anthropic"
        )


def _create_yandex_llm(provider_config: LLMProviderConfig, model: str) -> BaseLLM:
    """Создает Yandex LLM"""
    # Заглушка для YandexGPT - нужна будет кастомная реализация
    # или использование langchain-community
    raise NotImplementedError("Yandex LLM пока не реализован")


def _create_ollama_llm(provider_config: LLMProviderConfig, model: str) -> BaseLLM:
    """Создает Ollama LLM"""
    if Ollama is None:
        raise ImportError("langchain_community не установлен. Установите: pip install langchain-community")
    
    try:
        kwargs = {
            "model": model,
            "temperature": provider_config.default_temperature,
            "openai_api_base": provider_config.base_url,
        }

        # Добавляем специфичные настройки модели
        if hasattr(provider_config.models, 'get'):
            model_config = provider_config.models.get(model, {})
            if "max_tokens" in model_config:
                kwargs["num_predict"] = model_config[
                    "max_tokens"
                ]  # Ollama использует num_predict

        return Ollama(**kwargs)

    except ImportError:
        raise ImportError(
            "Для использования Ollama установите: pip install langchain-community"
        )


def _create_mock_llm(provider_config: LLMProviderConfig, model: str) -> BaseLLM:
    """Создает Mock LLM для тестов"""
    global _global_mock_llm

    # Переиспользуем глобальный экземпляр для тестов
    if _global_mock_llm is not None:
        return _global_mock_llm

    class MockLLM(BaseChatModel):
        """Настраиваемая моковая LLM для тестов"""

        def __init__(self, model, temperature, **kwargs):
            super().__init__(**kwargs)
            # Используем object.__setattr__ для обхода Pydantic валидации
            object.__setattr__(self, "_model", model)
            object.__setattr__(self, "_temperature", temperature)
            object.__setattr__(self, "responses", {})
            object.__setattr__(
                self,
                "default_response",
                "Я обработаю ваш запрос используя доступные инструменты.",
            )
            object.__setattr__(self, "call_count", 0)

        def set_response(self, keyword: str, response: str):
            """Устанавливает ответ для определенного ключевого слова"""
            self.responses[keyword.lower()] = response

        def set_responses(self, responses_dict: dict):
            """Устанавливает несколько ответов сразу"""
            for keyword, response in responses_dict.items():
                self.set_response(keyword, response)

        def set_default_response(self, response: str):
            """Устанавливает ответ по умолчанию"""
            object.__setattr__(self, "default_response", response)

        def bind_tools(self, tools, **kwargs):
            """Привязывает инструменты к модели (для ReAct агентов)"""
            # Просто возвращаем себя - мок не нуждается в привязке инструментов
            return self

        async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
            """Генерирует ответы на основе настроек"""
            object.__setattr__(self, "call_count", self.call_count + 1)
            logger.info(f"🤖 MockLLM вызван {self.call_count} раз")

            # Извлекаем последнее сообщение пользователя
            if messages and len(messages) > 0:
                last_messages = messages[-1]
                if hasattr(last_messages, "content"):
                    user_message = last_messages.content
                else:
                    user_message = str(last_messages)
            else:
                user_message = ""

            user_message_lower = user_message.lower()

            # Ищем совпадения в настроенных ответах
            response_text = self.default_response
            for keyword, response in self.responses.items():
                if keyword in user_message_lower:
                    response_text = response
                    break

            logger.info(f"🤖 MockLLM отвечает: {response_text[:50]}...")

            # Создаем правильный результат для Chat модели
            message = AIMessage(content=response_text)
            generation = ChatGeneration(message=message)

            return ChatResult(generations=[generation])

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            """Синхронная версия"""
            try:
                loop = asyncio.get_event_loop()
                return loop.run_until_complete(
                    self._agenerate(messages, stop, run_manager, **kwargs)
                )
            except RuntimeError:
                return asyncio.run(
                    self._agenerate(messages, stop, run_manager, **kwargs)
                )

        @property
        def _llm_type(self) -> str:
            return "mock"

    mock_instance = MockLLM(
        model=model, temperature=provider_config.default_temperature
    )

    # Сохраняем в глобальной переменной для переиспользования
    _global_mock_llm = mock_instance

    return mock_instance


def _create_gemini_llm(
    provider_config: LLMProviderConfig, model: str, **agent_kwargs
) -> BaseLLM:
    """Создает Gemini LLM через нативный Google SDK"""
    try:
        from app.llms.gemini_chat import GeminiChatModel
        
        kwargs = {
            "model_name": model,
            "api_key": provider_config.api_key,
            "temperature": provider_config.default_temperature,
        }

        # Добавляем специфичные настройки модели
        if hasattr(provider_config.models, 'get'):
            model_config = provider_config.models.get(model, {})
            if "max_tokens" in model_config:
                kwargs["max_tokens"] = model_config["max_tokens"]

        # Переопределяем параметрами от агента
        for key, value in agent_kwargs.items():
            if key not in ["api_key"]:
                kwargs[key] = value

        return GeminiChatModel(**kwargs)

    except ImportError:
        raise ImportError(
            "Для использования Gemini установите: pip install google-generativeai"
        )


def get_global_mock_llm():
    """Получает глобальный мок для настройки в тестах"""
    return _global_mock_llm
