"""
Сервис биллинга и учета использования ресурсов.
Работает на уровне компаний.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from typing import TYPE_CHECKING

from core.context import get_context
from core.models.identity_models import User, Company
from core.models.billing_models import UsageRecord, UsageType, TariffPlan, DEFAULT_TARIFF_PRICES

if TYPE_CHECKING:
    from core.db.repositories.company_repository import CompanyRepository
    from core.db.repositories.usage_repository import UsageRepository
    from core.db.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)


class BillingService:
    """Сервис биллинга и контроля лимитов"""
    
    def __init__(
        self, 
        company_repository: "CompanyRepository",
        user_repository: "UserRepository",
        usage_repository: "UsageRepository",
        tariff_prices: Optional[Dict[TariffPlan, Dict[str, Dict[str, float]]]] = None,
        resource_base_prices: Optional[Dict[str, Dict[str, float]]] = None
    ):
        if not company_repository:
            raise ValueError("company_repository обязателен для BillingService")
        if not user_repository:
            raise ValueError("user_repository обязателен для BillingService")
        if not usage_repository:
            raise ValueError("usage_repository обязателен для BillingService")
        
        self._company_repository = company_repository
        self._user_repository = user_repository
        self._usage_repository = usage_repository
        
        # Тарифные цены (множители к базовой цене)
        self._tariff_prices = tariff_prices or DEFAULT_TARIFF_PRICES
        
        # Базовые цены ресурсов по категориям
        self._resource_base_prices = resource_base_prices or {
            "llm": {
                "*": 0.001  # Минимальная стоимость для проверки баланса
            },
            "tool": {
                "weather_api": 0.1,
                "travel_suggest": 0.2,
                "calculator": 0.0,
                "nano_banana_generation": 0.5,
                "fashn_buyer_agent": 0.0,
                "*": 0.05  # Дефолтная цена для неизвестных инструментов
            }
        }
    
    async def can_use_resource(self, user: User, company: Company, resource_name: str) -> tuple[bool, str]:
        """
        Проверяет может ли компания использовать ресурс
        Возвращает (можно_ли, причина_если_нельзя)
        """
        
        # ВАЖНО: загружаем актуальную компанию из БД для проверки реального баланса
        actual_company = await self._company_repository.get(company.company_id)
        if not actual_company:
            return False, f"Компания {company.company_id} не найдена"
        
        # 1. Получаем стоимость ресурса с учетом тарифа компании
        resource_cost = await self.get_resource_cost_for_company(actual_company, resource_name)
        
        # 2. Проверяем баланс компании (если ресурс платный)
        if resource_cost > 0:
            if actual_company.balance <= 0:
                return False, f"На балансе компании недостаточно средств (баланс: {actual_company.balance:.2f}₽). Пополните баланс."
            
            if actual_company.balance < resource_cost:
                return False, f"Недостаточно средств на балансе: {actual_company.balance:.2f}₽, требуется: {resource_cost:.2f}₽"
        
        # 3. Проверяем месячный лимит расходов (если установлен)
        if actual_company.monthly_budget > 0 and resource_cost > 0:
            if actual_company.current_month_spent + resource_cost > actual_company.monthly_budget:
                return False, f"Превышен месячный лимит расходов: {actual_company.current_month_spent + resource_cost:.2f}₽/{actual_company.monthly_budget}₽"
        
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
        
        # ВАЖНО: загружаем актуальную компанию из БД чтобы не перезаписать данные
        actual_company = await self._company_repository.get(company.company_id)
        if not actual_company:
            raise ValueError(f"Компания {company.company_id} не найдена в БД")
        
        # Создаем запись об использовании
        usage_record = UsageRecord(
            usage_id=str(uuid.uuid4()),
            user_id=user.user_id,
            company_id=actual_company.company_id,
            session_id=session_id,
            usage_type=usage_type,
            resource_name=resource_name,
            cost=cost,
            quantity=quantity,
            metadata=metadata or {}
        )
        
        logger.info(f"Сохраняем запись использования: usage_id={usage_record.usage_id}, стоимость={cost}₽")
        
        if not self._usage_repository:
            raise RuntimeError(
                "UsageRepository не настроен. Биллинг не может работать без репозитория. "
                "Проверьте инициализацию BillingService."
            )
        
        await self._usage_repository.set(usage_record)
        
        # Обновляем баланс и потраченную сумму компании
        old_balance = actual_company.balance
        old_spent = actual_company.current_month_spent
        
        actual_company.balance -= cost
        actual_company.current_month_spent += cost
        
        if actual_company.balance < 0:
            raise ValueError(
                f"Баланс компании {actual_company.company_id} ушел в минус: {actual_company.balance:.2f}₽. "
                f"Это не должно было произойти - была ошибка в can_use_resource"
            )
        
        logger.info(f"Обновляем компанию {actual_company.company_id}:")
        logger.info(f"Баланс: {old_balance:.2f}₽ → {actual_company.balance:.2f}₽")
        logger.info(f"Потрачено в месяце: {old_spent:.2f}₽ → {actual_company.current_month_spent:.2f}₽")
        
        await self._company_repository.set(actual_company)
        
        # Обновляем баланс в переданном объекте для консистентности в текущем контексте
        company.balance = actual_company.balance
        company.current_month_spent = actual_company.current_month_spent
        
        logger.info(f"Записано использование {resource_name} для компании {actual_company.company_id}: {cost}₽")
    
    async def get_resource_cost_for_company(self, company: Company, resource_name: str) -> float:
        """Получает стоимость ресурса с учетом тарифа компании"""
        
        if ":" not in resource_name:
            raise ValueError(f"Неверный формат resource_name: {resource_name}. Ожидается 'category:resource'")
        
        category, resource = resource_name.split(":", 1)
        
        # Получаем базовую стоимость из конфигурации
        category_prices = self._resource_base_prices.get(category, {})
        base_cost = category_prices.get(resource, category_prices.get("*", 0.0))
        
        if base_cost == 0:
            return 0.0
        
        # Применяем тарифный множитель
        tariff_prices = self._tariff_prices.get(company.tariff_plan, {})
        tariff_category = "tools" if category == "tool" else category
        category_multipliers = tariff_prices.get(tariff_category, {})
        
        if resource in category_multipliers:
            multiplier = category_multipliers[resource]
        elif "*" in category_multipliers:
            multiplier = category_multipliers["*"]
        else:
            multiplier = 1.0
        
        final_cost = base_cost * multiplier
        logger.debug(f"💰 Цена {resource_name}: {base_cost}₽ × {multiplier} = {final_cost}₽")
        
        return final_cost
    
    async def get_company_usage_stats(self, company_id: str) -> Dict[str, Any]:
        """Получает статистику использования компании за месяц (оптимизировано)"""
        
        current_month = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        if not self._usage_repository:
            raise RuntimeError("UsageRepository не настроен. Невозможно получить статистику.")
        
        all_usage_records = await self._usage_repository.list_all(limit=10000)
        
        stats = {
            "total_cost": 0.0,
            "total_calls": 0,
            "by_resource": {},
            "by_user": {}
        }
        
        user_ids = set()
        
        for record in all_usage_records:
            
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
        
        if user_ids:
            users_dict = await self._user_repository.get_many(list(user_ids))
            for user_id in user_ids:
                if user_id in users_dict:
                    stats["by_user"][user_id]["user_name"] = users_dict[user_id].name
                else:
                    stats["by_user"][user_id]["user_name"] = user_id
        
        return stats
    
    async def reset_monthly_billing(self, company_id: str):
        """Сбрасывает месячный биллинг компании (вызывается в начале месяца)"""
        
        company = await self.company_repository.get(company_id)
        if not company:
            raise ValueError(f"Компания {company_id} не найдена")
        company.current_month_spent = 0.0
        company.billing_period_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        await self.company_repository.set(company)
        logger.info(f"Сброшен месячный биллинг для компании {company_id}")

