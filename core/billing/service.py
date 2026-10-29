"""
Сервис биллинга и учета использования ресурсов.
Работает на уровне компаний.
"""

from __future__ import annotations

import copy
import json
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, TypedDict

from core.context import get_context
from core.i18n import t
from core.logging import get_logger
from core.models.billing_models import (
    BillingCostOrigin,
    TariffPlan,
    UsageRecord,
    UsageType,
)
from core.models.i18n_models import Language
from core.models.identity_models import Company, User
from core.tracing.models import Span
from core.types import JsonObject, JsonValue, parse_json_object, require_json_object

if TYPE_CHECKING:
    from core.db.storage import Storage

from core.billing.default_settlement_rules import default_settlement_rules_document
from core.billing.exceptions import BillingBalanceBlockedError
from core.billing.settlement_rules import (
    SettlementRule,
    SettlementRulesDocument,
    parse_settlement_rules_json,
    quantity_from_span,
    resolve_matched_rules_by_priority_asc,
)
from core.billing.span_billing_settlement import SpanBillingSettlement
from core.models.identity_models import SYSTEM_COMPANY_ID
from core.websocket.publisher import Notification, NotificationType, notify_user

logger = get_logger(__name__)
STORAGE_SETTLEMENT_RULES_JSON = "billing:settlement_rules_json"

BALANCE_BLOCK_OPERATION_LLM = "llm"
BALANCE_BLOCK_OPERATION_EMBEDDING = "embedding"
BALANCE_BLOCK_OPERATION_VISION = "vision"
BALANCE_BLOCK_OPERATION_IMAGE = "image"
BALANCE_BLOCK_OPERATION_SPEECH = "speech"
BALANCE_BLOCK_OPERATION_LIVEKIT_ROOM = "livekit_room"
BALANCE_BLOCK_OPERATION_LIVEKIT_EGRESS = "livekit_egress"
BALANCE_BLOCK_OPERATION_SEARCH = "search"
BALANCE_BLOCK_OPERATION_GUEST_RUNTIME = "guest_runtime"

COST_ORIGIN_PLATFORM: BillingCostOrigin = "platform"
COST_ORIGIN_COMPANY: BillingCostOrigin = "company"

_BALANCE_BLOCK_OPERATION_I18N_KEYS: dict[str, str] = {
    BALANCE_BLOCK_OPERATION_LLM: "billing.notifications.blocked_operation.llm",
    BALANCE_BLOCK_OPERATION_EMBEDDING: "billing.notifications.blocked_operation.embedding",
    BALANCE_BLOCK_OPERATION_VISION: "billing.notifications.blocked_operation.vision",
    BALANCE_BLOCK_OPERATION_IMAGE: "billing.notifications.blocked_operation.image",
    BALANCE_BLOCK_OPERATION_SPEECH: "billing.notifications.blocked_operation.speech",
    BALANCE_BLOCK_OPERATION_LIVEKIT_ROOM: "billing.notifications.blocked_operation.livekit_room",
    BALANCE_BLOCK_OPERATION_LIVEKIT_EGRESS: "billing.notifications.blocked_operation.livekit_egress",
    BALANCE_BLOCK_OPERATION_SEARCH: "billing.notifications.blocked_operation.search",
    BALANCE_BLOCK_OPERATION_GUEST_RUNTIME: "billing.notifications.blocked_operation.guest_runtime",
}

def company_resource_prices_storage_key(company_id: str) -> str:
    return f"billing:company:{company_id}:resource_base_prices_json"

def company_settlement_rules_storage_key(company_id: str) -> str:
    return f"billing:company:{company_id}:settlement_rules_json"

def _settlement_rules_document_to_storage_json(doc: SettlementRulesDocument) -> str:
    return json.dumps(doc.model_dump(mode="json"), ensure_ascii=False)


def _merge_resource_base_price_override(
    merged: dict[str, dict[str, float]],
    raw_json: str,
    storage_key: str,
) -> None:
    data = parse_json_object(raw_json, storage_key)
    for category, resources_value in data.items():
        resources = require_json_object(resources_value, f"{storage_key}.{category}")
        bucket = merged.setdefault(category, {})
        for resource_name, price_value in resources.items():
            bucket[resource_name] = _json_price_to_float(price_value, f"{storage_key}.{category}.{resource_name}")


def _json_price_to_float(value: JsonValue, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a number")
    if isinstance(value, int | float | str):
        return float(value)
    raise ValueError(f"{field_name} must be a number")


class UsageStatsBucket(TypedDict):
    cost: float
    calls: int


class UserUsageStatsBucket(UsageStatsBucket):
    user_name: str | None


class CompanyUsageStats(TypedDict):
    total_cost: float
    total_calls: int
    by_resource: dict[str, UsageStatsBucket]
    by_user: dict[str, UserUsageStatsBucket]


class BillingService:
    """Сервис биллинга и контроля лимитов"""

    def __init__(
        self,
        tariff_prices: dict[TariffPlan, dict[str, dict[str, float]]] | None = None,
        resource_base_prices: dict[str, dict[str, float]] | None = None,
        shared_storage: Storage | None = None,
        balance_enforcement_enabled: bool = True,
        balance_enforcement_exempt_company_ids: list[str] | None = None,
    ):
        self._shared_storage: Storage | None = shared_storage

        if tariff_prices is None:
            raise ValueError(
                'tariff_prices is required: pass from settings.billing.tariff_prices'
            )
        self._tariff_prices: dict[TariffPlan, dict[str, dict[str, float]]] = tariff_prices

        if resource_base_prices is None:
            raise ValueError('resource_base_prices is required (pass from settings.billing.resource_base_prices)')
        self._resource_base_prices_static: dict[str, dict[str, float]] = copy.deepcopy(resource_base_prices)
        _ = self._resource_base_prices_static.pop("tool", None)

        self._balance_enforcement_enabled: bool = balance_enforcement_enabled
        exempt = (
            balance_enforcement_exempt_company_ids
            if balance_enforcement_exempt_company_ids is not None
            else [SYSTEM_COMPANY_ID]
        )
        self._balance_enforcement_exempt_company_ids: frozenset[str] = frozenset(exempt)

    async def require_balance_for_billable_operation(
        self,
        company_id: str,
        user_id: str,
        *,
        operation_code: str,
        notification_service: str = "frontend",
        cost_origin: str = COST_ORIGIN_PLATFORM,
    ) -> None:
        """
        Pre-flight перед операцией, которая создаёт span с pending_settlement.
        При блокировке по балансу отправляет notify_user с пояснением (язык из контекста или RU).

        ``cost_origin == "company"`` — вызов идёт через ключ компании, биллинга нет, проверка
        баланса пропускается.
        """
        if cost_origin == COST_ORIGIN_COMPANY:
            return
        if not self._balance_enforcement_enabled:
            return
        cid = (company_id or "").strip()
        if not cid:
            raise ValueError('company_id is required for the balance check')
        uid = (user_id or "").strip()
        if not uid:
            raise ValueError('user_id is required for balance check and notification')
        if operation_code not in _BALANCE_BLOCK_OPERATION_I18N_KEYS:
            raise ValueError(
                f"Unknown billing operation_code: {operation_code!r}. " +
                f"Allowed: {sorted(_BALANCE_BLOCK_OPERATION_I18N_KEYS.keys())}"
            )
        svc = (notification_service or "").strip()
        if not svc:
            raise ValueError('notification_service cannot be empty')
        if cid in self._balance_enforcement_exempt_company_ids:
            return
        company = await Company.get(cid)
        if company is None:
            raise ValueError(f"Company {cid} not found")
        if company.balance <= 0:
            ctx = get_context()
            lang = ctx.language if ctx is not None else Language.RU
            op_key = _BALANCE_BLOCK_OPERATION_I18N_KEYS[operation_code]
            operation_label = t(op_key, language=lang)
            title = t("billing.notifications.balance_blocked_title", language=lang)
            balance_s = f"{company.balance:.2f}"
            message = t(
                "billing.notifications.balance_blocked_message",
                language=lang,
                operation=operation_label,
                company_name=company.name,
                balance=balance_s,
            )
            await notify_user(
                uid,
                Notification(
                    type=NotificationType.SYSTEM,
                    title=title,
                    message=message,
                    service=svc,
                    priority="high",
                    action_url="/billing",
                    data={
                        "event": "billing/balance/blocked",
                        "company_id": cid,
                        "operation_code": operation_code,
                        "code": "billing_balance_blocked",
                    },
                ),
            )
            detail = t(
                "billing.notifications.balance_blocked_api_detail",
                language=lang,
                company_id=cid,
                balance=balance_s,
                operation=operation_label,
            )
            raise BillingBalanceBlockedError(detail)

    async def company_may_incur_billable_operation_charge(self, company_id: str) -> bool:
        """
        Тихая проверка: можно ли запускать платный platform-billed вызов.

        Учитывает ``balance_enforcement_enabled`` и exempt-список. Не отправляет notify_user.
        При отсутствии компании в хранилище возвращает ``False``.
        """
        cid = (company_id or "").strip()
        if not cid:
            raise ValueError('company_id is required for company_may_incur_billable_operation_charge')
        if not self._balance_enforcement_enabled:
            return True
        if cid in self._balance_enforcement_exempt_company_ids:
            return True
        company = await Company.get(cid)
        if company is None:
            return False
        return company.balance > 0

    async def can_use_resource(
        self,
        _user: User,
        company: Company,
        resource_name: str,
        quantity: int = 1,
    ) -> tuple[bool, str]:
        """
        Проверяет может ли компания использовать ресурс
        Возвращает (можно_ли, причина_если_нельзя)
        """
        if quantity < 1:
            return False, "quantity должна быть >= 1"

        # ВАЖНО: загружаем актуальную компанию из БД для проверки реального баланса
        actual_company = await Company.get(company.company_id)
        if not actual_company:
            return False, f"Компания {company.company_id} не найдена"

        unit_cost = await self.get_resource_cost_for_company(actual_company, resource_name)
        resource_cost = unit_cost * quantity

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

    async def get_effective_resource_base_prices(self) -> dict[str, dict[str, float]]:
        merged = copy.deepcopy(self._resource_base_prices_static)
        if self._shared_storage is None:
            return merged
        raw = await self._shared_storage.get("billing:resource_base_prices_json")
        if not raw:
            return merged
        _merge_resource_base_price_override(merged, raw, "billing:resource_base_prices_json")
        _ = merged.pop("tool", None)
        return merged

    def get_static_resource_base_prices(self) -> dict[str, dict[str, float]]:
        return copy.deepcopy(self._resource_base_prices_static)

    def get_tariff_multipliers_for_plan(self, plan: TariffPlan) -> dict[str, dict[str, float]]:
        return copy.deepcopy(self._tariff_prices.get(plan, {}))

    def apply_tariff_multipliers_to_base_prices(
        self,
        base_prices: dict[str, dict[str, float]],
        plan: TariffPlan,
    ) -> dict[str, dict[str, float]]:
        tariff_prices = self._tariff_prices.get(plan, {})
        out: dict[str, dict[str, float]] = {}
        for category, resources in base_prices.items():
            category_multipliers = tariff_prices.get(category, {})
            out_bucket: dict[str, float] = {}
            for resource, base_cost in resources.items():
                if base_cost == 0:
                    out_bucket[resource] = 0.0
                    continue
                if resource in category_multipliers:
                    multiplier = category_multipliers[resource]
                elif "*" in category_multipliers:
                    multiplier = category_multipliers["*"]
                else:
                    multiplier = 1.0
                out_bucket[resource] = float(base_cost) * float(multiplier)
            out[category] = out_bucket
        _ = out.pop("tool", None)
        return out

    async def get_effective_resource_base_prices_for_company(self, company_id: str) -> dict[str, dict[str, float]]:
        merged = await self.get_effective_resource_base_prices()
        if self._shared_storage is None:
            return merged
        raw = await self._shared_storage.get(company_resource_prices_storage_key(company_id))
        if not raw:
            return merged
        _merge_resource_base_price_override(merged, raw, company_resource_prices_storage_key(company_id))
        _ = merged.pop("tool", None)
        return merged

    async def load_settlement_rules_document(self) -> SettlementRulesDocument:
        """Устаревший глобальный каталог (только чтение для миграции). Джоба и API используют per-company."""
        if self._shared_storage is None:
            return SettlementRulesDocument()
        raw = await self._shared_storage.get(STORAGE_SETTLEMENT_RULES_JSON)
        if not raw:
            return SettlementRulesDocument()
        return parse_settlement_rules_json(raw)

    async def load_settlement_rules_document_for_company(self, company_id: str) -> SettlementRulesDocument:
        """
        Правила settlement компании: ключ per-company в storage.

        Ключ отсутствует или rules пустой — в ключ пишется кодовый дефолт (default_settlement_rules_document).
        Глобальный billing:settlement_rules_json не подмешивается: он только для load_settlement_rules_document()
        (чтение без записи в компанию).
        """
        if not company_id:
            raise ValueError('company_id is required for settlement rules')
        if self._shared_storage is None:
            return default_settlement_rules_document()

        key = company_settlement_rules_storage_key(company_id)
        raw = await self._shared_storage.get(key)
        if raw:
            existing = parse_settlement_rules_json(raw)
            if existing.rules:
                return existing

        fresh = default_settlement_rules_document()
        _ = await self._shared_storage.set(
            key,
            _settlement_rules_document_to_storage_json(fresh),
        )
        return fresh

    async def ensure_settlement_rules_materialized_for_all_companies(self, *, limit: int = 50_000) -> int:
        """
        Для каждой компании в хранилище вызывает load_settlement_rules_document_for_company:
        отсутствующий или пустой rules в Redis заменяется кодовым дефолтом.
        """
        if self._shared_storage is None:
            return 0
        companies = await Company.list(limit=limit)
        for company in companies:
            _ = await self.load_settlement_rules_document_for_company(company.company_id)
        return len(companies)

    async def save_settlement_rules_document_for_company(
        self,
        company_id: str,
        document: SettlementRulesDocument,
    ) -> None:
        if not company_id:
            raise ValueError('company_id is required')
        if self._shared_storage is None:
            raise RuntimeError('shared_storage is not configured: cannot persist settlement rules')
        key = company_settlement_rules_storage_key(company_id)
        _ = await self._shared_storage.set(
            key,
            _settlement_rules_document_to_storage_json(document),
        )

    async def record_usage(
        self,
        user: User,
        company: Company,
        resource_name: str,
        cost: float,
        usage_type: UsageType = UsageType.TOOL_CALL,
        quantity: int = 1,
        metadata: JsonObject | None = None,
        cost_origin: BillingCostOrigin = COST_ORIGIN_PLATFORM,
    ) -> str:
        """Записывает использование ресурса. Возвращает usage_id.

        ``cost_origin``:

        - ``platform`` — стандартное списание с баланса компании.
        - ``company`` — компания платит сама (BYOK / custom провайдер); запись создаётся
          с ``cost=0``, баланс и ``current_month_spent`` не трогаются. Метка фиксируется
          в metadata записи, чтобы аналитика видела факт использования и провайдера.
        """

        context = get_context()
        session_id = context.session_id if context else None

        actual_company = await Company.get(company.company_id)
        if not actual_company:
            raise ValueError(f"Company {company.company_id} not found in the database")

        is_company = cost_origin == COST_ORIGIN_COMPANY
        effective_cost = 0.0 if is_company else cost

        record_metadata: JsonObject = dict(metadata) if metadata is not None else {}
        record_metadata["cost_origin"] = cost_origin

        usage_record = UsageRecord(
            usage_id=str(uuid.uuid4()),
            user_id=user.user_id,
            company_id=actual_company.company_id,
            session_id=session_id,
            usage_type=usage_type,
            resource_name=resource_name,
            cost=effective_cost,
            quantity=quantity,
            metadata=record_metadata,
        )

        logger.info(
            "billing.usage_id.cost_origin",
            usage_id=usage_record.usage_id,
            effective_cost=effective_cost,
            cost_origin=cost_origin,
        )

        _ = await UsageRecord.set(usage_record)

        if not is_company:
            balance_before = actual_company.balance
            spent_before = actual_company.current_month_spent
            actual_company.balance -= effective_cost
            actual_company.current_month_spent += effective_cost
            logger.info(
                "billing.event",
                company_id=actual_company.company_id,
                balance_before=balance_before,
                balance=actual_company.balance,
                spent_before=spent_before,
                current_month_spent=actual_company.current_month_spent,
            )
            _ = await Company.set(actual_company)
            company.balance = actual_company.balance
            company.current_month_spent = actual_company.current_month_spent
        else:
            logger.info("billing.cost_origin", resource_name=resource_name, usage_id=usage_record.usage_id)

        return usage_record.usage_id

    async def settle_span_rule_charge(
        self,
        *,
        span: Span,
        rule: SettlementRule,
        settlement: SpanBillingSettlement,
    ) -> str:
        """Списание по одному правилу; идемпотентность по (span_id, rule.rule_id)."""
        span_id = span.span_id
        prev = await settlement.get_usage_id(span_id, rule.rule_id)
        if prev is not None:
            return prev

        company_id = span.company_id
        if not company_id:
            raise ValueError(f"span {span_id}: span column has no company_id")

        uid = span.user_id
        if not uid:
            raise ValueError(f"span {span_id}: span column has no user_id")

        user = await User.get(uid)
        if user is None:
            raise ValueError(f"span {span_id}: user {uid} not found")

        company = await Company.get(company_id)
        if company is None:
            raise ValueError(f"span {span_id}: company {company_id} not found")

        usage_type = rule.usage_type
        quantity = quantity_from_span(rule.quantity_from, span)
        resource_name = rule.resolve_resource_name(span)

        if quantity == 0:
            skip_usage_id = f"skipped:zero_quantity:{span_id}:{rule.rule_id}"
            await settlement.mark(span_id, rule.rule_id, skip_usage_id)
            return skip_usage_id

        unit_cost = await self._unit_cost_for_company(company, resource_name)
        cost = unit_cost * quantity

        custom_pid = span.billing_custom_provider_id()
        meta: JsonObject = {
            "span_id": span_id,
            "trace_id": span.trace_id,
            "rule_id": rule.rule_id,
            "settlement_source": "span_billing_job",
        }
        if custom_pid is not None:
            meta["custom_provider_id"] = custom_pid

        usage_id = await self.record_usage(
            user,
            company,
            resource_name,
            cost,
            usage_type=usage_type,
            quantity=quantity,
            metadata=meta,
            cost_origin=span.billing_cost_origin_or_default(),
        )
        await settlement.mark(span_id, rule.rule_id, usage_id)
        return usage_id

    async def settle_pending_span_in_job(
        self,
        *,
        span: Span,
        settlement: SpanBillingSettlement,
        rules_doc: SettlementRulesDocument,
    ) -> int:
        """
        Один span из джобы: N списаний по совпавшим правилам.
        Возвращает число успешных вызовов record_usage (0 если уже всё списано или нет матча).
        """
        if not rules_doc.rules:
            raise ValueError("settlement rules document must contain at least one enabled rule")

        matched = resolve_matched_rules_by_priority_asc(rules_doc, span)
        if not matched:
            logger.warning("billing.settlement.span_id.operation_name", span_id=span.span_id, operation_name=span.operation_name)
            return 0

        count = 0
        for rule in matched:
            before = await settlement.get_usage_id(span.span_id, rule.rule_id)
            if before is not None:
                continue
            _ = await self.settle_span_rule_charge(
                span=span,
                rule=rule,
                settlement=settlement,
            )
            count += 1
        return count

    async def _unit_cost_for_company(self, company: Company, resource_name: str) -> float:
        if ":" not in resource_name:
            raise ValueError(f"Invalid resource_name format: {resource_name}. Expected 'category:resource'")

        category, resource = resource_name.split(":", 1)
        if category == "tool":
            return 0.0

        base_prices = await self.get_effective_resource_base_prices_for_company(company.company_id)
        category_prices = base_prices.get(category, {})
        base_cost = category_prices.get(resource, category_prices.get("*", 0.0))

        if base_cost == 0:
            return 0.0

        tariff_prices = self._tariff_prices.get(company.tariff_plan, {})
        category_multipliers = tariff_prices.get(category, {})

        if resource in category_multipliers:
            multiplier = category_multipliers[resource]
        elif "*" in category_multipliers:
            multiplier = category_multipliers["*"]
        else:
            multiplier = 1.0

        return base_cost * multiplier

    async def get_resource_cost_for_company(self, company: Company, resource_name: str) -> float:
        """Получает стоимость единицы ресурса с учётом базового прайса (global + company) и тарифа."""
        unit = await self._unit_cost_for_company(company, resource_name)
        logger.debug(
            "billing.event",
            resource_name=resource_name,
            company_id=company.company_id,
            unit=unit,
        )
        return unit

    async def get_company_usage_stats(self, company_id: str) -> CompanyUsageStats:
        """Получает статистику использования компании за месяц (оптимизировано)"""

        current_month = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        all_usage_records = await UsageRecord.list_unordered_since(company_id, current_month)

        stats: CompanyUsageStats = {
            "total_cost": 0.0,
            "total_calls": 0,
            "by_resource": {},
            "by_user": {},
        }

        user_ids: set[str] = set()

        for record in all_usage_records:
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
            users_dict = await User.get_many(list(user_ids))
            for user_id in user_ids:
                if user_id in users_dict:
                    stats["by_user"][user_id]["user_name"] = users_dict[user_id].name
                else:
                    stats["by_user"][user_id]["user_name"] = user_id

        return stats

    async def reset_monthly_billing(self, company_id: str):
        """Сбрасывает месячный биллинг компании (вызывается в начале месяца)"""

        company = await Company.get(company_id)
        if not company:
            raise ValueError(f"Company {company_id} not found")
        company.current_month_spent = 0.0
        company.billing_period_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        _ = await Company.set(company)
        logger.info("billing.monthly_reset", company_id=company_id)
