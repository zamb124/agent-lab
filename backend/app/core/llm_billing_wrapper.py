"""
Обертка для LLM с поддержкой биллинга и контроля доступа.
"""

import logging
import time
from typing import Any, Dict, Optional, List
from langchain_core.language_models.base import BaseLanguageModel
from langchain_core.messages import BaseMessage

from ..core.context import get_context
from ..services.billing_service import BillingService
from ..models.billing_models import UsageType
from ..core.config import get_settings

logger = logging.getLogger(__name__)


class LLMBillingWrapper:
    """Обертка для LLM с биллингом и контролем доступа"""
    
    def __init__(self, llm: BaseLanguageModel, provider: str, model: str):
        self.llm = llm
        self.provider = provider
        self.model = model
        self.billing_service = BillingService()
        
        # Получаем стоимость за токен из конфигурации
        settings = get_settings()
        provider_config = settings.llm.providers.get(provider, {})
        model_config = provider_config.get('models', {}).get(model, {})
        self.cost_per_token = model_config.get('cost_per_token', 0.0)
        
        # Название для биллинга
        self.billing_name = f"{provider}_{model}".replace("-", "_").replace(".", "_")
        
        logger.info(f"Создана LLM обертка для {provider}:{model}, стоимость: {self.cost_per_token}₽/токен")
    
    async def ainvoke(self, input_data, config=None):
        """Асинхронный вызов LLM с биллингом"""
        return await self._invoke_with_billing(input_data, config, async_call=True)
    
    def invoke(self, input_data, config=None):
        """Синхронный вызов LLM с биллингом"""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self._invoke_with_billing(input_data, config, async_call=False))
        except RuntimeError:
            # Если нет event loop, выполняем без биллинга
            logger.warning("Нет event loop для биллинга LLM, выполняем без учета")
            return self.llm.invoke(input_data, config)
    
    async def _invoke_with_billing(self, input_data, config, async_call=True):
        """Основная логика вызова с биллингом"""
        
        context = get_context()
        
        # Если нет контекста - выполняем без биллинга
        if not context or not context.user or not context.active_company:
            logger.info("Нет контекста для биллинга LLM, выполняем без учета")
            if async_call:
                return await self.llm.ainvoke(input_data, config)
            else:
                return self.llm.invoke(input_data, config)
        
        user = context.user
        company = context.active_company
        
        # Проверяем можно ли использовать эту LLM
        can_use, reason = await self.billing_service.can_use_resource(user, company, self.billing_name)
        if not can_use:
            raise Exception(f"Доступ к {self.provider}:{self.model} запрещен: {reason}")
        
        # Оцениваем количество токенов во входных данных
        input_tokens = self._estimate_tokens(input_data)
        estimated_cost = input_tokens * self.cost_per_token * 2  # *2 для учета выходных токенов
        
        # Проверяем бюджет компании (предварительно)
        if company.monthly_budget > 0 and estimated_cost > 0:
            if company.current_month_spent + estimated_cost > company.monthly_budget:
                raise Exception(f"Недостаточно средств для LLM запроса. Оценочная стоимость: {estimated_cost:.2f}₽")
        
        # Выполняем запрос к LLM
        start_time = time.time()
        try:
            if async_call:
                result = await self.llm.ainvoke(input_data, config)
            else:
                result = self.llm.invoke(input_data, config)
            
            execution_time = time.time() - start_time
            
            # Извлекаем реальную информацию о токенах
            actual_input_tokens, actual_output_tokens = self._extract_token_usage(result, input_tokens)
            actual_cost = (actual_input_tokens + actual_output_tokens) * self.cost_per_token
            
            # Записываем использование
            await self.billing_service.record_usage(
                user=user,
                company=company,
                resource_name=self.billing_name,
                cost=actual_cost,
                usage_type=UsageType.LLM_REQUEST,
                quantity=actual_input_tokens + actual_output_tokens,
                metadata={
                    "provider": self.provider,
                    "model": self.model,
                    "input_tokens": actual_input_tokens,
                    "output_tokens": actual_output_tokens,
                    "execution_time": execution_time,
                    "cost_per_token": self.cost_per_token
                }
            )
            
            logger.info(f"LLM запрос выполнен: {self.provider}:{self.model}, "
                       f"токены: {actual_input_tokens}+{actual_output_tokens}, "
                       f"стоимость: {actual_cost:.4f}₽")
            
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Ошибка LLM запроса ({execution_time:.2f}с): {e}")
            # Если запрос упал, не списываем деньги
            raise e
    
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
    
    # Делегируем остальные методы к оригинальному LLM
    def __getattr__(self, name):
        return getattr(self.llm, name)
