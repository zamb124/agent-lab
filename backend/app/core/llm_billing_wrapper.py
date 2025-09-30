"""
LLM классы с встроенным биллингом.
"""

import logging
import time
from typing import Any, Dict, Optional, List
from langchain_core.language_models.base import BaseLanguageModel
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI

from ..core.context import get_context
from ..services.billing_service import BillingService
from ..models.billing_models import UsageType
from ..core.config import get_settings

logger = logging.getLogger(__name__)


class ChatOpenAIWithBilling(ChatOpenAI):
    """ChatOpenAI с встроенным биллингом"""
    
    def __init__(self, provider: str, **kwargs):
        model = kwargs.get('model', 'unknown')
        super().__init__(**kwargs)
        
        # Инициализация биллинга
        self._billing_provider = provider
        self._billing_model = model
        self._billing_service = BillingService()
        
        # Получаем стоимость за токен из конфигурации
        settings = get_settings()
        provider_config = settings.llm.providers.get(provider)
        if provider_config and hasattr(provider_config, 'models') and hasattr(provider_config.models, 'get'):
            model_config = provider_config.models.get(model, {})
            self._cost_per_token = model_config.get('cost_per_token', 0.0)
        else:
            self._cost_per_token = 0.0
        
        # Название для биллинга
        self._billing_name = f"{provider}:{model}"
        
        logger.info(f"Создана LLM с биллингом для {provider}:{model}, стоимость: {self._cost_per_token}₽/токен")
    
    async def ainvoke(self, input_data, config=None, **kwargs):
        """Асинхронный вызов с биллингом"""
        logger.error(f"🔥 ВЫЗВАН ChatOpenAIWithBilling.ainvoke для {self._billing_provider}:{self._billing_model}")
        
        context = get_context()
        if not context or not context.user or not context.active_company:
            raise Exception("Нет контекста для биллинга LLM")
        
        user = context.user
        company = context.active_company
        
        # Проверяем можно ли использовать эту LLM
        can_use, reason = await self._billing_service.can_use_resource(user, company, self._billing_name)
        if not can_use:
            raise Exception(f"Доступ к {self._billing_provider}:{self._billing_model} запрещен: {reason}")
        
        # Выполняем запрос
        result = await super().ainvoke(input_data, config, **kwargs)
        
        # Записываем использование (упрощенно)
        await self._billing_service.record_usage(
            user=user,
            company=company,
            resource_name=self._billing_name,
            cost=0.01,  # Фиксированная стоимость пока
            usage_type=UsageType.LLM_REQUEST,
            metadata={
                "provider": self._billing_provider,
                "model": self._billing_model,
            }
        )
        
        logger.info(f"✅ LLM запрос выполнен с биллингом: {self._billing_provider}:{self._billing_model}")
        return result
    
    def _estimate_tokens(self, input_data) -> int:
        """Оценивает количество токенов во входных данных"""
        
        if isinstance(input_data, str):
            # Простая оценка: ~4 символа = 1 токен
            return len(input_data) // 4
        elif isinstance(input_data, list):
            # Список сообщений
            total_chars = 0
            for item in input_data:
                if isinstance(item, BaseMessage):
                    total_chars += len(item.content)
                elif isinstance(item, dict):
                    total_chars += len(str(item))
                else:
                    total_chars += len(str(item))
            return total_chars // 4
        elif isinstance(input_data, dict):
            # Словарь с данными
            return len(str(input_data)) // 4
        else:
            # Прочие типы
            return len(str(input_data)) // 4
    
    def _extract_token_usage(self, result, estimated_input_tokens: int) -> tuple[int, int]:
        """Извлекает реальную информацию о токенах из результата"""
        
        # Пытаемся извлечь из response_metadata
        if hasattr(result, 'response_metadata'):
            metadata = result.response_metadata
            
            # OpenAI format
            if 'token_usage' in metadata:
                token_usage = metadata['token_usage']
                input_tokens = token_usage.get('prompt_tokens', estimated_input_tokens)
                output_tokens = token_usage.get('completion_tokens', 0)
                return input_tokens, output_tokens
            
            # Другие форматы
            if 'usage' in metadata:
                usage = metadata['usage']
                input_tokens = usage.get('input_tokens', estimated_input_tokens)
                output_tokens = usage.get('output_tokens', 0)
                return input_tokens, output_tokens
        
        # Если не удалось извлечь, используем оценку
        if hasattr(result, 'content'):
            output_tokens = len(result.content) // 4
        else:
            output_tokens = len(str(result)) // 4
        
        return estimated_input_tokens, output_tokens
