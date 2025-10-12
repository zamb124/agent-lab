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
from ..models.billing_models import UsageRecord, UsageType, TARIFF_PRICES
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
        
        # 1. Получаем стоимость ресурса с учетом тарифа компании
        resource_cost = await self.get_resource_cost_for_company(company, resource_name)
        
        # 2. Проверяем баланс компании (если ресурс платный)
        if resource_cost > 0:
            if company.balance <= 0:
                return False, "На балансе компании недостаточно средств. Пополните баланс."
            
            if company.balance < resource_cost:
                return False, f"Недостаточно средств на балансе: {company.balance:.2f}₽, требуется: {resource_cost:.2f}₽"
        
        # 3. Проверяем месячный лимит расходов (если установлен)
        if company.monthly_budget > 0 and resource_cost > 0:
            if company.current_month_spent + resource_cost > company.monthly_budget:
                return False, f"Превышен месячный лимит расходов: {company.current_month_spent + resource_cost:.2f}₽/{company.monthly_budget}₽"
        
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
        
        # Обновляем баланс и потраченную сумму компании
        old_balance = company.balance
        old_spent = company.current_month_spent
        
        # Проверяем что баланс не уйдет в минус
        new_balance = company.balance - cost
        if new_balance < 0:
            new_balance = 0
            logger.warning(f"⚠️ Баланс компании {company.company_id} был бы отрицательным, устанавливаем 0")
        
        company.balance = new_balance
        company.current_month_spent += cost
        
        logger.info(f"💰 Обновляем компанию {company.company_id}:")
        logger.info(f"   Баланс: {old_balance:.2f}₽ → {company.balance:.2f}₽")
        logger.info(f"   Потрачено в месяце: {old_spent:.2f}₽ → {company.current_month_spent:.2f}₽")
        
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
    
    async def get_resource_cost_for_company(self, company: Company, resource_name: str) -> float:
        """Получает стоимость ресурса с учетом тарифа компании"""
        
        # Получаем базовую цену
        base_cost = await self._get_base_resource_cost(resource_name)
        
        # Если базовая цена 0 - ресурс бесплатный
        if base_cost == 0:
            return 0.0
        
        # Применяем тарифный множитель
        tariff_prices = TARIFF_PRICES.get(company.tariff_plan, {})
        
        # Парсим формат category:resource
        if ":" not in resource_name:
            return base_cost
        
        category, resource = resource_name.split(":", 1)
        
        # Получаем множитель для категории
        # Нормализуем категорию: tool -> tools для совместимости
        tariff_category = category
        if category == "tool":
            tariff_category = "tools"
        
        category_prices = tariff_prices.get(tariff_category, {})
        
        # Проверяем есть ли специфичная цена для ресурса
        if resource in category_prices:
            multiplier = category_prices[resource]
        elif "*" in category_prices:
            multiplier = category_prices["*"]
        else:
            multiplier = 1.0  # Базовая цена
        
        final_cost = base_cost * multiplier
        logger.debug(f"💰 Цена для {resource_name}: базовая={base_cost}₽, множитель={multiplier}, итого={final_cost}₽")
        
        return final_cost
    
    async def _get_base_resource_cost(self, resource_name: str) -> float:
        """Получает базовую стоимость ресурса"""
        
        # Парсим формат category:resource
        if ":" not in resource_name:
            return 0.0
        
        category, resource = resource_name.split(":", 1)
        
        # Для LLM - получаем из конфигурации или устанавливаем базовую
        if category in ["openai", "gemini", "yandex", "anthropic"]:
            # Базовые цены для LLM (можно переопределить в конфиге)
            llm_base_prices = {
                "openai": {
                    "gpt-4": 1.0,
                    "gpt-4o": 0.8,
                    "gpt-3.5-turbo": 0.1,
                },
                "gemini": {
                    "gemini-2.0-flash-exp": 0.2,
                    "gemini-2.5-pro": 0.5,
                    "gemini-1.5-flash": 0.15,
                    "gemini-1.5-pro": 0.4,
                },
                "yandex": {
                    "yandexgpt/latest": 0.3,
                },
                "anthropic": {
                    "claude-3-sonnet": 0.7,
                }
            }
            provider_prices = llm_base_prices.get(category, {})
            return provider_prices.get(resource, 0.5)  # 0.5 по умолчанию
        
        # Для инструментов
        elif category == "tool":
            tool_base_prices = {
                "weather_api": 0.1,
                "travel_suggest": 0.2,
                "calculator": 0.0,
                "nano_banana_generation": 0.5,
                "fashn_buyer_agent": 0.0,
            }
            return tool_base_prices.get(resource, 0.05)  # 0.05 по умолчанию
        
        return 0.0
    
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
                            stats["by_user"][record.user_id] = {"cost": 0.0, "calls": 0, "user_name": None}
                        stats["by_user"][record.user_id]["cost"] += record.cost
                        stats["by_user"][record.user_id]["calls"] += record.quantity
                except Exception:
                    continue
        
        # Обогащаем данные пользователей именами
        for user_id in stats["by_user"].keys():
            user_data = await self.storage.get(f"user:{user_id}", force_global=True)
            if user_data:
                
                user = User.model_validate_json(user_data)
                stats["by_user"][user_id]["user_name"] = user.name
            else:
                stats["by_user"][user_id]["user_name"] = user_id
        
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
