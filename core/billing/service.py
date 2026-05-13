"""
Сервис биллинга и учета использования ресурсов.
Работает на уровне компаний.
"""

import copy
import json
import uuid

from core.logging import get_logger
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from typing import TYPE_CHECKING

from core.context import get_context
from core.i18n import t
from core.models.i18n_models import Language
from core.models.identity_models import User, Company
from core.models.billing_models import UsageRecord, UsageType, TariffPlan, DEFAULT_TARIFF_PRICES
from core.tracing import attributes as trace_attr

if TYPE_CHECKING:
    from core.db.repositories.company_repository import CompanyRepository
    from core.db.repositories.usage_repository import UsageRepository
    from core.db.repositories.user_repository import UserRepository
    from core.db.storage import Storage

from core.billing.exceptions import BillingBalanceBlockedError
from core.websocket.publisher import Notification, NotificationType, notify_user
from core.billing.default_settlement_rules import default_settlement_rules_document
from core.identity.system_bootstrap import SYSTEM_COMPANY_ID
from core.billing.span_billing_settlement import LEGACY_SPAN_ONLY_RULE_ID, SpanBillingSettlement
from core.billing.settlement_rules import (
    SettlementRule,
    SettlementRulesDocument,
    parse_settlement_rules_json,
    quantity_from_span,
    resolve_matched_rules,
)

logger = get_logger(__name__)
STORAGE_SETTLEMENT_RULES_JSON = "billing:settlement_rules_json"

BALANCE_BLOCK_OPERATION_LLM = "llm"
BALANCE_BLOCK_OPERATION_EMBEDDING = "embedding"
BALANCE_BLOCK_OPERATION_VISION = "vision"
BALANCE_BLOCK_OPERATION_LIVEKIT_ROOM = "livekit_room"
BALANCE_BLOCK_OPERATION_LIVEKIT_EGRESS = "livekit_egress"

COST_ORIGIN_PLATFORM = "platform"
COST_ORIGIN_COMPANY = "company"

_BALANCE_BLOCK_OPERATION_I18N_KEYS: dict[str, str] = {
    BALANCE_BLOCK_OPERATION_LLM: "billing.notifications.blocked_operation.llm",
    BALANCE_BLOCK_OPERATION_EMBEDDING: "billing.notifications.blocked_operation.embedding",
    BALANCE_BLOCK_OPERATION_VISION: "billing.notifications.blocked_operation.vision",
    BALANCE_BLOCK_OPERATION_LIVEKIT_ROOM: "billing.notifications.blocked_operation.livekit_room",
    BALANCE_BLOCK_OPERATION_LIVEKIT_EGRESS: "billing.notifications.blocked_operation.livekit_egress",
}

def company_resource_prices_storage_key(company_id: str) -> str:
    return f"billing:company:{company_id}:resource_base_prices_json"

def company_settlement_rules_storage_key(company_id: str) -> str:
    return f"billing:company:{company_id}:settlement_rules_json"

def _settlement_rules_document_to_storage_json(doc: SettlementRulesDocument) -> str:
    return json.dumps(doc.model_dump(mode="json"), ensure_ascii=False)

class BillingService:
    """Сервис биллинга и контроля лимитов"""
    
    def __init__(
        self, 
        company_repository: "CompanyRepository",
        user_repository: "UserRepository",
        usage_repository: "UsageRepository",
        tariff_prices: Optional[Dict[TariffPlan, Dict[str, Dict[str, float]]]] = None,
        resource_base_prices: Optional[Dict[str, Dict[str, float]]] = None,
        shared_storage: Optional["Storage"] = None,
        balance_enforcement_enabled: bool = True,
        balance_enforcement_exempt_company_ids: Optional[list[str]] = None,
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
        self._shared_storage = shared_storage
        
        # Тарифные цены (множители к базовой цене)
        self._tariff_prices = tariff_prices or DEFAULT_TARIFF_PRICES
        
        if resource_base_prices is None:
            raise ValueError("resource_base_prices обязателен (передавайте из settings.billing.resource_base_prices)")
        self._resource_base_prices_static = copy.deepcopy(resource_base_prices)
        self._resource_base_prices_static.pop("tool", None)

        self._balance_enforcement_enabled = balance_enforcement_enabled
        exempt = (
            balance_enforcement_exempt_company_ids
            if balance_enforcement_exempt_company_ids is not None
            else [SYSTEM_COMPANY_ID]
        )
        self._balance_enforcement_exempt_company_ids = frozenset(exempt)
    
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
            raise ValueError("company_id обязателен для проверки баланса")
        uid = (user_id or "").strip()
        if not uid:
            raise ValueError("user_id обязателен для проверки баланса и уведомления")
        if operation_code not in _BALANCE_BLOCK_OPERATION_I18N_KEYS:
            raise ValueError(
                f"Неизвестный operation_code для биллинга: {operation_code!r}. "
                f"Допустимо: {sorted(_BALANCE_BLOCK_OPERATION_I18N_KEYS.keys())}"
            )
        svc = (notification_service or "").strip()
        if not svc:
            raise ValueError("notification_service не может быть пустым")
        if cid in self._balance_enforcement_exempt_company_ids:
            return
        company = await self._company_repository.get(cid)
        if company is None:
            raise ValueError(f"Компания {cid} не найдена")
        if company.balance <= 0:
            ctx = get_context()
            lang = ctx.language if ctx is not None and ctx.language is not None else Language.RU
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
                        "event": "billing.balance_blocked",
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

    async def company_may_incur_embedding_charge(self, company_id: str) -> bool:
        """
        Тихая проверка для фоновых задач (reembed): можно ли запускать платный embedding.

        Учитывает ``balance_enforcement_enabled`` и exempt-список. Не отправляет notify_user.
        При отсутствии компании в хранилище возвращает ``False``.
        """
        cid = (company_id or "").strip()
        if not cid:
            raise ValueError("company_id обязателен для company_may_incur_embedding_charge")
        if not self._balance_enforcement_enabled:
            return True
        if cid in self._balance_enforcement_exempt_company_ids:
            return True
        company = await self._company_repository.get(cid)
        if company is None:
            return False
        return company.balance > 0

    async def can_use_resource(
        self,
        user: User,
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
        actual_company = await self._company_repository.get(company.company_id)
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
    
    async def get_effective_resource_base_prices(self) -> Dict[str, Dict[str, float]]:
        merged = copy.deepcopy(self._resource_base_prices_static)
        if self._shared_storage is None:
            return merged
        raw = await self._shared_storage.get("billing:resource_base_prices_json", force_global=True)
        if not raw:
            return merged
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("billing:resource_base_prices_json должен быть JSON-объектом категорий")
        for cat, resources in data.items():
            if not isinstance(cat, str):
                raise ValueError(f"Неверный ключ категории в override: {cat!r}")
            if not isinstance(resources, dict):
                raise ValueError(f"Категория {cat!r} в override должна быть объектом resource->price")
            bucket = merged.setdefault(cat, {})
            for res_name, price in resources.items():
                bucket[str(res_name)] = float(price)
        merged.pop("tool", None)
        return merged

    async def get_effective_resource_base_prices_for_company(self, company_id: str) -> Dict[str, Dict[str, float]]:
        merged = await self.get_effective_resource_base_prices()
        if self._shared_storage is None:
            return merged
        raw = await self._shared_storage.get(company_resource_prices_storage_key(company_id), force_global=True)
        if not raw:
            return merged
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError(
                f"{company_resource_prices_storage_key(company_id)} должен быть JSON-объектом категорий"
            )
        for cat, resources in data.items():
            if not isinstance(cat, str):
                raise ValueError(f"Неверный ключ категории в company override: {cat!r}")
            if not isinstance(resources, dict):
                raise ValueError(f"Категория {cat!r} в company override должна быть объектом resource->price")
            bucket = merged.setdefault(cat, {})
            for res_name, price in resources.items():
                bucket[str(res_name)] = float(price)
        merged.pop("tool", None)
        return merged

    async def load_settlement_rules_document(self) -> SettlementRulesDocument:
        """Устаревший глобальный каталог (только чтение для миграции). Джоба и API используют per-company."""
        if self._shared_storage is None:
            return SettlementRulesDocument()
        raw = await self._shared_storage.get(STORAGE_SETTLEMENT_RULES_JSON, force_global=True)
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
        if not company_id or not isinstance(company_id, str):
            raise ValueError("company_id обязателен для правил settlement")
        if self._shared_storage is None:
            return default_settlement_rules_document()

        key = company_settlement_rules_storage_key(company_id)
        raw = await self._shared_storage.get(key, force_global=True)
        if raw:
            existing = parse_settlement_rules_json(raw)
            if existing.rules:
                return existing

        fresh = default_settlement_rules_document()
        await self._shared_storage.set(
            key,
            _settlement_rules_document_to_storage_json(fresh),
            force_global=True,
        )
        return fresh

    async def ensure_settlement_rules_materialized_for_all_companies(self, *, limit: int = 50_000) -> int:
        """
        Для каждой компании в хранилище вызывает load_settlement_rules_document_for_company:
        отсутствующий или пустой rules в Redis заменяется кодовым дефолтом.
        """
        if self._shared_storage is None:
            return 0
        companies = await self._company_repository.list(limit=limit)
        for company in companies:
            await self.load_settlement_rules_document_for_company(company.company_id)
        return len(companies)

    async def save_settlement_rules_document_for_company(
        self,
        company_id: str,
        document: SettlementRulesDocument,
    ) -> None:
        if not company_id or not isinstance(company_id, str):
            raise ValueError("company_id обязателен")
        if self._shared_storage is None:
            raise RuntimeError("shared_storage не настроен: сохранение правил settlement невозможно")
        key = company_settlement_rules_storage_key(company_id)
        await self._shared_storage.set(
            key,
            _settlement_rules_document_to_storage_json(document),
            force_global=True,
        )

    async def record_usage(
        self, 
        user: User, 
        company: Company, 
        resource_name: str, 
        cost: float,
        usage_type: UsageType = UsageType.TOOL_CALL,
        quantity: int = 1,
        metadata: Optional[Dict[str, Any]] = None,
        cost_origin: str = COST_ORIGIN_PLATFORM,
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

        actual_company = await self._company_repository.get(company.company_id)
        if not actual_company:
            raise ValueError(f"Компания {company.company_id} не найдена в БД")

        is_company = cost_origin == COST_ORIGIN_COMPANY
        effective_cost = 0.0 if is_company else cost

        record_metadata = dict(metadata or {})
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
            "Сохраняем запись использования: usage_id=%s, стоимость=%s₽, cost_origin=%s",
            usage_record.usage_id,
            effective_cost,
            cost_origin,
        )

        if not self._usage_repository:
            raise RuntimeError(
                "UsageRepository не настроен. Биллинг не может работать без репозитория. "
                "Проверьте инициализацию BillingService."
            )

        await self._usage_repository.set(usage_record)

        if not is_company:
            old_balance = actual_company.balance
            old_spent = actual_company.current_month_spent
            actual_company.balance -= effective_cost
            actual_company.current_month_spent += effective_cost
            logger.info(
                "Обновляем компанию %s: баланс %.2f → %.2f, потрачено %.2f → %.2f",
                actual_company.company_id,
                old_balance,
                actual_company.balance,
                old_spent,
                actual_company.current_month_spent,
            )
            await self._company_repository.set(actual_company)
            company.balance = actual_company.balance
            company.current_month_spent = actual_company.current_month_spent
        else:
            logger.info(
                "cost_origin=company: ресурс %s, баланс не списан (запись %s — для аналитики)",
                resource_name,
                usage_record.usage_id,
            )

        return usage_record.usage_id

    async def settle_span_charge(
        self,
        *,
        span_dict: Dict[str, Any],
        settlement: SpanBillingSettlement,
        fallback_user_id: str,
    ) -> str:
        """
        Legacy: списание по platform.billing.* на span.
        Идемпотентность: LEGACY_SPAN_ONLY_RULE_ID + старый ключ billing:settled_span:{span_id}.
        """
        span_id = span_dict["span_id"]
        prev = await settlement.get_usage_id(span_id, LEGACY_SPAN_ONLY_RULE_ID)
        if prev is not None:
            return prev

        attrs = span_dict.get("attributes") or {}
        resource_name = attrs.get(trace_attr.ATTR_BILLING_RESOURCE_NAME)
        if not resource_name or not isinstance(resource_name, str):
            raise ValueError(f"span {span_id}: отсутствует {trace_attr.ATTR_BILLING_RESOURCE_NAME}")

        company_id = span_dict.get("company_id")
        if not company_id or not isinstance(company_id, str):
            raise ValueError(f"span {span_id}: нет company_id в колонке span")

        uid = span_dict.get("user_id")
        if not uid or not isinstance(uid, str):
            if not fallback_user_id:
                raise ValueError(
                    f"span {span_id}: нет user_id; задайте billing.span_settlement.fallback_user_id в конфиге"
                )
            uid = fallback_user_id

        user = await self._user_repository.get(uid)
        if user is None:
            raise ValueError(f"span {span_id}: пользователь {uid} не найден")

        company = await self._company_repository.get(company_id)
        if company is None:
            raise ValueError(f"span {span_id}: компания {company_id} не найдена")

        ut_raw = attrs.get(trace_attr.ATTR_BILLING_USAGE_TYPE)
        if ut_raw is not None and ut_raw != "":
            try:
                usage_type = UsageType(str(ut_raw))
            except ValueError as e:
                raise ValueError(f"span {span_id}: неизвестный UsageType {ut_raw!r}") from e
        else:
            usage_type = UsageType.TOOL_CALL

        qty_raw = attrs.get(trace_attr.ATTR_BILLING_QUANTITY, 1)
        quantity = int(qty_raw) if qty_raw is not None else 1
        if quantity < 1:
            raise ValueError(f"span {span_id}: platform.billing.quantity должна быть >= 1")

        unit_cost = await self.get_resource_cost_for_company(company, resource_name)
        cost = unit_cost * quantity

        cost_origin = attrs.get(trace_attr.ATTR_BILLING_COST_ORIGIN, COST_ORIGIN_PLATFORM)
        meta: Dict[str, Any] = {
            "span_id": span_id,
            "trace_id": span_dict.get("trace_id"),
            "settlement_source": "span_billing_job",
        }
        custom_pid = attrs.get(trace_attr.ATTR_BILLING_CUSTOM_PROVIDER_ID)
        if custom_pid:
            meta["custom_provider_id"] = custom_pid

        usage_id = await self.record_usage(
            user,
            company,
            resource_name,
            cost,
            usage_type=usage_type,
            quantity=quantity,
            metadata=meta,
            cost_origin=cost_origin,
        )
        await settlement.mark(span_id, LEGACY_SPAN_ONLY_RULE_ID, usage_id)
        return usage_id

    async def settle_span_rule_charge(
        self,
        *,
        span_dict: Dict[str, Any],
        rule: SettlementRule,
        settlement: SpanBillingSettlement,
        fallback_user_id: str,
    ) -> str:
        """Списание по одному правилу; идемпотентность по (span_id, rule.rule_id)."""
        span_id = span_dict["span_id"]
        prev = await settlement.get_usage_id(span_id, rule.rule_id)
        if prev is not None:
            return prev

        company_id = span_dict.get("company_id")
        if not company_id or not isinstance(company_id, str):
            raise ValueError(f"span {span_id}: нет company_id в колонке span")

        uid = span_dict.get("user_id")
        if not uid or not isinstance(uid, str):
            if not fallback_user_id:
                raise ValueError(
                    f"span {span_id}: нет user_id; задайте billing.span_settlement.fallback_user_id в конфиге"
                )
            uid = fallback_user_id

        user = await self._user_repository.get(uid)
        if user is None:
            raise ValueError(f"span {span_id}: пользователь {uid} не найден")

        company = await self._company_repository.get(company_id)
        if company is None:
            raise ValueError(f"span {span_id}: компания {company_id} не найдена")

        usage_type = UsageType(rule.usage_type)
        quantity = quantity_from_span(rule.quantity_from, span_dict)
        resource_name = rule.resource_name

        if quantity == 0:
            skip_usage_id = f"skipped:zero_quantity:{span_id}:{rule.rule_id}"
            await settlement.mark(span_id, rule.rule_id, skip_usage_id)
            return skip_usage_id

        unit_cost = await self._unit_cost_for_company(company, resource_name)
        cost = unit_cost * quantity

        attrs = span_dict.get("attributes") or {}
        cost_origin = attrs.get(trace_attr.ATTR_BILLING_COST_ORIGIN, COST_ORIGIN_PLATFORM)
        custom_pid = attrs.get(trace_attr.ATTR_BILLING_CUSTOM_PROVIDER_ID)
        meta: Dict[str, Any] = {
            "span_id": span_id,
            "trace_id": span_dict.get("trace_id"),
            "rule_id": rule.rule_id,
            "settlement_source": "span_billing_job",
        }
        if custom_pid:
            meta["custom_provider_id"] = custom_pid

        usage_id = await self.record_usage(
            user,
            company,
            resource_name,
            cost,
            usage_type=usage_type,
            quantity=quantity,
            metadata=meta,
            cost_origin=cost_origin,
        )
        await settlement.mark(span_id, rule.rule_id, usage_id)
        return usage_id

    async def settle_pending_span_in_job(
        self,
        *,
        span_dict: Dict[str, Any],
        settlement: SpanBillingSettlement,
        fallback_user_id: str,
        rules_doc: SettlementRulesDocument,
    ) -> int:
        """
        Один span из джобы: либо legacy (пустой каталог правил), либо N списаний по совпавшим правилам.
        Возвращает число успешных вызовов record_usage (0 если уже всё списано или нет матча).
        """
        if not rules_doc.rules:
            sid = span_dict["span_id"]
            if await settlement.get_usage_id(sid, LEGACY_SPAN_ONLY_RULE_ID) is not None:
                return 0
            await self.settle_span_charge(
                span_dict=span_dict,
                settlement=settlement,
                fallback_user_id=fallback_user_id,
            )
            return 1

        matched = resolve_matched_rules(rules_doc, span_dict)
        if not matched:
            logger.warning(
                "settlement: ни одно правило не матчит span_id=%s operation_name=%s",
                span_dict.get("span_id"),
                span_dict.get("operation_name"),
            )
            return 0

        count = 0
        for rule in matched:
            before = await settlement.get_usage_id(span_dict["span_id"], rule.rule_id)
            if before is not None:
                continue
            await self.settle_span_rule_charge(
                span_dict=span_dict,
                rule=rule,
                settlement=settlement,
                fallback_user_id=fallback_user_id,
            )
            count += 1
        return count

    async def _unit_cost_for_company(self, company: Company, resource_name: str) -> float:
        if ":" not in resource_name:
            raise ValueError(f"Неверный формат resource_name: {resource_name}. Ожидается 'category:resource'")

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
        logger.debug("Цена %s для %s: %s₽", resource_name, company.company_id, unit)
        return unit
    
    async def get_company_usage_stats(self, company_id: str) -> Dict[str, Any]:
        """Получает статистику использования компании за месяц (оптимизировано)"""
        
        current_month = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        if not self._usage_repository:
            raise RuntimeError("UsageRepository не настроен. Невозможно получить статистику.")
        
        all_usage_records = await self._usage_repository.list(limit=10000)
        
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
            if record.company_id != company_id:
                continue

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
        
        company = await self._company_repository.get(company_id)
        if not company:
            raise ValueError(f"Компания {company_id} не найдена")
        company.current_month_spent = 0.0
        company.billing_period_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        await self._company_repository.set(company)
        logger.info(f"Сброшен месячный биллинг для компании {company_id}")

