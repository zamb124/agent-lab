"""
LLM с встроенным биллингом для OpenRouter.
"""

import logging
from langchain_openai import ChatOpenAI

from app.core.context import get_context
from app.services.billing_service import BillingService
from app.models.billing_models import UsageType
from app.exceptions import TariffError, BillingError

logger = logging.getLogger(__name__)


class ChatOpenAIWithBilling(ChatOpenAI):
    """ChatOpenAI с встроенным биллингом для OpenRouter"""
    
    def __init__(self, **kwargs):
        model = kwargs.get('model', 'unknown')
        super().__init__(**kwargs)
        
        self._billing_model = model
        self._billing_service = BillingService()
        
        logger.info(f"Создана LLM с биллингом: {model}")
    
    async def ainvoke(self, input_data, config=None, **kwargs):
        """Асинхронный вызов с биллингом"""
        logger.debug(f"Вызов LLM: {self._billing_model}")
        
        # Mock модели не проверяем баланс (для тестов)
        is_mock = self._billing_model.startswith("mock-")
        
        if not is_mock:
            context = get_context()
            if not context or not context.user or not context.active_company:
                raise Exception("Нет контекста для биллинга LLM")
            
            user = context.user
            company = context.active_company
            
            resource_name = f"llm:{self._billing_model}"
            
            # Проверяем доступ к ресурсу
            can_use, reason = await self._billing_service.can_use_resource(
                user, company, resource_name
            )
            if not can_use:
                if "недоступен на тарифе" in reason:
                    raise TariffError(f"Доступ к {self._billing_model} запрещен: {reason}")
                else:
                    raise BillingError(f"Доступ к {self._billing_model} запрещен: {reason}")
        else:
            # Для mock моделей используем тестовый контекст если есть
            context = get_context()
            user = context.user if context else None
            company = context.active_company if context else None
        
        # Выполняем запрос
        result = await super().ainvoke(input_data, config, **kwargs)
        
        # Извлекаем информацию о токенах из OpenRouter response
        input_tokens = 0
        output_tokens = 0
        total_tokens = 0
        
        if hasattr(result, 'response_metadata') and result.response_metadata:
            metadata = result.response_metadata
            
            # OpenRouter возвращает usage в том же формате что и OpenAI
            if 'token_usage' in metadata:
                token_usage = metadata['token_usage']
                input_tokens = token_usage.get('prompt_tokens', 0)
                output_tokens = token_usage.get('completion_tokens', 0)
                total_tokens = token_usage.get('total_tokens', 0)
            elif 'usage' in metadata:
                usage = metadata['usage']
                input_tokens = usage.get('prompt_tokens', 0)
                output_tokens = usage.get('completion_tokens', 0)
                total_tokens = usage.get('total_tokens', 0)
        
        # Если не удалось извлечь, используем оценку
        if total_tokens == 0:
            logger.warning(f"Не удалось извлечь токены из response для {self._billing_model}, используем оценку")
            input_tokens = self._estimate_tokens(input_data)
            if hasattr(result, 'content'):
                output_tokens = len(result.content) // 4
            total_tokens = input_tokens + output_tokens
        
        # Получаем стоимость input и output токенов из конфигурации
        from app.core.config import get_settings
        settings = get_settings()
        model_config = settings.llm.models.get(self._billing_model)
        
        if model_config and hasattr(model_config, 'input_cost_per_token') and hasattr(model_config, 'output_cost_per_token'):
            input_cost_per_token = model_config.input_cost_per_token
            output_cost_per_token = model_config.output_cost_per_token
        else:
            # Дефолтные значения если не настроено
            input_cost_per_token = 0.00001
            output_cost_per_token = 0.00001
        
        # Рассчитываем реальную стоимость: input и output отдельно
        input_cost = input_tokens * input_cost_per_token
        output_cost = output_tokens * output_cost_per_token
        cost = input_cost + output_cost
        
        # Записываем использование с реальной стоимостью (только для не-mock моделей)
        if not is_mock and user and company:
            await self._billing_service.record_usage(
                user=user,
                company=company,
                resource_name=resource_name,
                cost=cost,
                usage_type=UsageType.LLM_REQUEST,
                metadata={
                    "model": self._billing_model,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                    "input_cost": input_cost,
                    "output_cost": output_cost,
                    "input_cost_per_token": input_cost_per_token,
                    "output_cost_per_token": output_cost_per_token,
                }
            )
        
        if is_mock:
            logger.debug(f"Mock LLM запрос выполнен: {self._billing_model}")
        else:
            logger.info(
                f"LLM запрос выполнен: {self._billing_model}, "
                f"токены: {input_tokens}/{output_tokens}, стоимость: {cost:.4f}₽"
            )
        return result
    
    def _estimate_tokens(self, input_data) -> int:
        """Оценивает количество токенов во входных данных (если не удалось извлечь из API)"""
        from langchain_core.messages import BaseMessage
        
        if isinstance(input_data, str):
            return len(input_data) // 4
        elif isinstance(input_data, list):
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
            return len(str(input_data)) // 4
        else:
            return len(str(input_data)) // 4
