"""
Сервис биллинга и учета использования ресурсов.
Работает на уровне компаний.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from ..core.storage import Storage
from ..core.context import get_context
from ..identity.models import User, Company
from ..models.billing_models import UsageRecord, UsageType, TariffPlan, TARIFF_LIMITS

logger = logging.getLogger(__name__)


class BillingService:
    """Сервис биллинга и контроля лимитов"""
    
    def __init__(self):
        self.storage = Storage()
    
    async def can_use_resource(self, user: User, company: Company, resource_name: str) -> tuple[bool, str]:
        """
        Проверяет может ли компания использовать ресурс
        Возвращает (можно_ли, причина_если_нельзя)
        """
        
        # 1. Проверяем лимиты тарифного плана
        logger.debug(f"🔥 company.tariff_plan = {company.tariff_plan} (тип: {type(company.tariff_plan)})")
        logger.debug(f"🔥 TARIFF_LIMITS.keys() = {list(TARIFF_LIMITS.keys())}")
        tariff_limits = TARIFF_LIMITS.get(company.tariff_plan, {})
        logger.debug(f"🔥 tariff_limits для {company.tariff_plan}: {tariff_limits}")
        
        # Определяем тип ресурса и лимит
        resource_limit = 0
        
        # Парсим формат category:resource
        if ":" not in resource_name:
            logger.debug(f"🔥 НЕПРАВИЛЬНЫЙ ФОРМАТ resource_name: '{resource_name}' (нет ':')")
            return False, f"Неправильный формат ресурса: {resource_name}"
            
        category, resource = resource_name.split(":", 1)
        
        if category in ["openai", "gemini", "yandex", "anthropic"]:
            # LLM ресурсы: openai:gpt-4o, gemini:gemini-1.5-pro
            provider_limits = tariff_limits.get(category, {})
            if "*" in provider_limits:
                resource_limit = provider_limits["*"]
            else:
                resource_limit = provider_limits.get(resource, 0)
                
        elif category == "platform":
            # Платформенные ресурсы: platform:max_agents
            platform_limits = tariff_limits.get("platform", {})
            if "*" in platform_limits:
                resource_limit = platform_limits["*"]
            else:
                resource_limit = platform_limits.get(resource, 0)
                
        elif category == "tool":
            # Тулы: tool:weather_api
            tools_limits = tariff_limits.get("tools", {})
            if "*" in tools_limits:
                resource_limit = tools_limits["*"]
            else:
                resource_limit = tools_limits.get(resource, 0)
                
        else:
            logger.debug(f"🔥 НЕИЗВЕСТНАЯ КАТЕГОРИЯ: '{category}'")
            return False, f"Неизвестная категория ресурса: {category}"
        
        logger.debug(f"🔥 ИТОГОВЫЙ resource_limit = {resource_limit}")
        if resource_limit == 0:
            logger.debug(f"🔥 БЛОКИРУЕМ: resource_limit = 0")
            return False, f"Ресурс {resource_name} недоступен на тарифе {company.tariff_plan}"
        
        # 2. Если лимит не безлимитный, проверяем использование
        if resource_limit > 0:
            current_usage = await self._get_monthly_usage(company.company_id, resource_name)
            if current_usage >= resource_limit:
                return False, f"Превышен месячный лимит для {resource_name}: {current_usage}/{resource_limit}"
        
        # 3. Проверяем бюджет компании
        # ВАЖНО: Если бюджет не установлен (0 или None), запрещаем использование
        if not company.monthly_budget or company.monthly_budget <= 0:
            return False, f"У компании не установлен месячный бюджет. Обратитесь к администратору."
        
        # Проверяем не превышен ли бюджет
        resource_cost = await self._get_resource_cost(resource_name)
        if company.current_month_spent + resource_cost > company.monthly_budget:
            return False, f"Превышен месячный бюджет компании: {company.current_month_spent + resource_cost:.2f}₽/{company.monthly_budget}₽"
        
        return True, ""
    
    async def record_usage(
        self, 
        user: User, 
        company: Company, 
        resource_name: str, 
        cost: float,
        usage_type: UsageType = UsageType.TOOL_CALL,
        quantity: int = 1,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Записывает использование ресурса"""
        
        context = get_context()
        session_id = context.session_id if context else None
        
        # Создаем запись об использовании
        usage_record = UsageRecord(
            usage_id=str(uuid.uuid4()),
            user_id=user.user_id,
            company_id=company.company_id,
            session_id=session_id,
            usage_type=usage_type,
            resource_name=resource_name,
            cost=cost,
            quantity=quantity,
            metadata=metadata or {}
        )
        
        # Сохраняем запись с составным ключом для эффективного поиска
        # Формат: usage:{company_id}:{resource_name}:{usage_id}
        usage_key = f"usage:{company.company_id}:{resource_name}:{usage_record.usage_id}"
        
        logger.info(f"💾 Сохраняем запись использования: ключ={usage_key}, стоимость={cost}₽")
        
        await self.storage.set(usage_key, usage_record.model_dump_json(), force_global=True)
        
        # Обновляем потраченную сумму компании
        old_spent = company.current_month_spent
        company.current_month_spent += cost
        
        logger.info(f"💰 Обновляем баланс компании {company.company_id}: {old_spent}₽ → {company.current_month_spent}₽")
        
        await self.storage.set(f"company:{company.company_id}", company.model_dump_json(), force_global=True)
        
        logger.info(f"✅ Записано использование {resource_name} для компании {company.company_id}: {cost}₽")
    
    async def _get_monthly_usage(self, company_id: str, resource_name: str) -> int:
        """Получает количество использований ресурса компанией за месяц"""
        
        # Получаем начало текущего месяца
        current_month = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Эффективный поиск по составному ключу
        # Ищем все записи для конкретной компании и ресурса
        search_prefix = f"usage:{company_id}:{resource_name}:"
        usage_keys = await self.storage.list_by_prefix(search_prefix, force_global=True)
        
        count = 0
        for key in usage_keys:
            data = await self.storage.get(key, force_global=True)
            if data:
                try:
                    record = UsageRecord.model_validate_json(data)
                    # Проверяем только дату (company_id и resource_name уже отфильтрованы ключом)
                    if record.timestamp >= current_month:
                        count += record.quantity
                except Exception:
                    continue
        
        return count
    
    async def _get_resource_cost(self, resource_name: str) -> float:
        """Получает стоимость ресурса из конфигурации"""
        
        # Для LLM - получаем из конфигурации
        if "_" in resource_name and any(provider in resource_name for provider in ["openai", "yandex", "anthropic", "ollama", "gemini"]):
            return await self._get_llm_cost(resource_name)
        
        # Стандартные стоимости для инструментов (потом из ToolReference)
        default_costs = {
            "weather_api": 0.1,
            "travel_suggest": 0.2,
            "calculator": 0.0,
        }
        
        return default_costs.get(resource_name, 0.0)
    
    async def _get_llm_cost(self, llm_resource_name: str) -> float:
        """Получает стоимость LLM из конфигурации"""
        
        from ..core.config import get_settings
        
        try:
            # Парсим название: "openai_gpt_4" -> provider="openai", model="gpt-4"
            parts = llm_resource_name.split("_")
            if len(parts) < 2:
                return 0.0
            
            provider = parts[0]
            model = "_".join(parts[1:]).replace("_", "-")  # gpt_4 -> gpt-4
            
            settings = get_settings()
            provider_config = settings.llm.providers.get(provider)
            if provider_config and hasattr(provider_config, 'models'):
                model_config = provider_config.models.get(model, {})
                cost_per_token = model_config.get('cost_per_token', 0.0)
            else:
                cost_per_token = 0.0
            
            # Возвращаем стоимость за средний запрос (примерно 1000 токенов)
            return cost_per_token * 1000
            
        except Exception as e:
            logger.warning(f"Не удалось получить стоимость для {llm_resource_name}: {e}")
            return 0.0
    
    async def get_company_usage_stats(self, company_id: str) -> Dict[str, Any]:
        """Получает статистику использования компании за месяц"""
        
        current_month = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Эффективный поиск только записей этой компании
        company_usage_prefix = f"usage:{company_id}:"
        usage_keys = await self.storage.list_by_prefix(company_usage_prefix, force_global=True)
        
        stats = {
            "total_cost": 0.0,
            "total_calls": 0,
            "by_resource": {},
            "by_user": {}
        }
        
        for key in usage_keys:
            data = await self.storage.get(key, force_global=True)
            if data:
                try:
                    record = UsageRecord.model_validate_json(data)
                    # Проверяем только дату (company_id уже отфильтрован ключом)
                    if record.timestamp >= current_month:
                        # Общая статистика
                        stats["total_cost"] += record.cost
                        stats["total_calls"] += record.quantity
                        
                        # По ресурсам
                        if record.resource_name not in stats["by_resource"]:
                            stats["by_resource"][record.resource_name] = {"cost": 0.0, "calls": 0}
                        stats["by_resource"][record.resource_name]["cost"] += record.cost
                        stats["by_resource"][record.resource_name]["calls"] += record.quantity
                        
                        # По пользователям
                        if record.user_id not in stats["by_user"]:
                            stats["by_user"][record.user_id] = {"cost": 0.0, "calls": 0}
                        stats["by_user"][record.user_id]["cost"] += record.cost
                        stats["by_user"][record.user_id]["calls"] += record.quantity
                except Exception:
                    continue
        
        return stats
    
    async def reset_monthly_billing(self, company_id: str):
        """Сбрасывает месячный биллинг компании (вызывается в начале месяца)"""
        
        company_data = await self.storage.get(f"company:{company_id}")
        if not company_data:
            logger.warning(f"Компания {company_id} не найдена для сброса биллинга")
            return
        
        company = Company(**company_data)
        company.current_month_spent = 0.0
        company.billing_period_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        await self.storage.set(f"company:{company_id}", company.model_dump_json(), force_global=True)
        logger.info(f"Сброшен месячный биллинг для компании {company_id}")
