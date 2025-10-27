"""
Сервис биллинга и учета использования ресурсов.
Работает на уровне компаний.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from app.db.repositories import Storage
from ..core.context import get_context
from ..identity.models import User, Company
from ..models.billing_models import UsageRecord, UsageType, TARIFF_PRICES
from ..core.container import get_container
logger = logging.getLogger(__name__)


class BillingService:
    """Сервис биллинга и контроля лимитов"""
    
    def __init__(self, storage: Storage = None):
        if storage is None:
            storage = get_container().storage
        self.storage = storage
    
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
        
        company.balance -= cost
        company.current_month_spent += cost
        
        if company.balance < 0:
            raise ValueError(
                f"Баланс компании {company.company_id} ушел в минус: {company.balance:.2f}₽. "
                f"Это не должно было произойти - была ошибка в can_use_resource"
            )
        
        logger.info(f"💰 Обновляем компанию {company.company_id}:")
        logger.info(f"   Баланс: {old_balance:.2f}₽ → {company.balance:.2f}₽")
        logger.info(f"   Потрачено в месяце: {old_spent:.2f}₽ → {company.current_month_spent:.2f}₽")
        
        await self.storage.set(f"company:{company.company_id}", company.model_dump_json(), force_global=True)
        
        logger.info(f"✅ Записано использование {resource_name} для компании {company.company_id}: {cost}₽")
    
    async def get_resource_cost_for_company(self, company: Company, resource_name: str) -> float:
        """Получает стоимость ресурса с учетом тарифа компании"""
        
        if ":" not in resource_name:
            raise ValueError(f"Неверный формат resource_name: {resource_name}. Ожидается 'category:resource'")
        
        category, resource = resource_name.split(":", 1)
        
        # Базовая стоимость
        if category == "llm":
            # Для LLM минимальная стоимость для проверки баланса
            # Реальная стоимость считается в llm_billing_wrapper.py
            base_cost = 0.001
        elif category == "tool":
            tool_base_prices = {
                "weather_api": 0.1,
                "travel_suggest": 0.2,
                "calculator": 0.0,
                "nano_banana_generation": 0.5,
                "fashn_buyer_agent": 0.0,
            }
            base_cost = tool_base_prices.get(resource, 0.05)
        else:
            base_cost = 0.0
        
        if base_cost == 0:
            return 0.0
        
        # Применяем тарифный множитель
        tariff_prices = TARIFF_PRICES.get(company.tariff_plan, {})
        tariff_category = "tools" if category == "tool" else category
        category_prices = tariff_prices.get(tariff_category, {})
        
        if resource in category_prices:
            multiplier = category_prices[resource]
        elif "*" in category_prices:
            multiplier = category_prices["*"]
        else:
            multiplier = 1.0
        
        final_cost = base_cost * multiplier
        logger.debug(f"💰 Цена {resource_name}: {base_cost}₽ × {multiplier} = {final_cost}₽")
        
        return final_cost
    
    async def get_company_usage_stats(self, company_id: str) -> Dict[str, Any]:
        """Получает статистику использования компании за месяц (оптимизировано)"""
        
        current_month = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Оптимизация: получаем все данные usage за 1 запрос
        company_usage_prefix = f"usage:{company_id}:"
        all_usage_data = await self.storage.get_all_by_prefix(company_usage_prefix, limit=10000, force_global=True)
        
        stats = {
            "total_cost": 0.0,
            "total_calls": 0,
            "by_resource": {},
            "by_user": {}
        }
        
        user_ids = set()
        
        for key, data in all_usage_data.items():
            record = UsageRecord.model_validate_json(data)
            
            if record.timestamp < current_month:
                continue
            
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
            user_ids.add(record.user_id)
        
        # Оптимизация: получаем только нужных пользователей за 1 запрос
        if user_ids:
            user_keys = [f"user:{uid}" for uid in user_ids]
            users_data = await self.storage.get_many(user_keys, force_global=True)
            for user_id in user_ids:
                user_key = f"user:{user_id}"
                if user_key in users_data:
                    user = User.model_validate_json(users_data[user_key])
                    stats["by_user"][user_id]["user_name"] = user.name
                else:
                    stats["by_user"][user_id]["user_name"] = user_id
        
        return stats
    
    async def reset_monthly_billing(self, company_id: str):
        """Сбрасывает месячный биллинг компании (вызывается в начале месяца)"""
        
        company_data = await self.storage.get(f"company:{company_id}")
        if not company_data:
            raise ValueError(f"Компания {company_id} не найдена")
        
        company = Company.model_validate_json(company_data)
        company.current_month_spent = 0.0
        company.billing_period_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        await self.storage.set(f"company:{company_id}", company.model_dump_json(), force_global=True)
        logger.info(f"Сброшен месячный биллинг для компании {company_id}")
