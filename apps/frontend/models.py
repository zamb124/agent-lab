"""
Модели данных для Frontend сервиса
"""
import re
from datetime import datetime, timezone
from typing import ClassVar, Literal, Self, override

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.billing.settlement_rules import SettlementRulesDocument
from core.clients.llm.config import LLMCallConfig
from core.company_ai import CapabilityLiteral
from core.config.models import LegalConfig, PublicSiteConfig
from core.models.payment_models import TransactionResponse
from core.tracing.models import TraceSpanRecord
from core.types import JsonObject


class ApiKey(BaseModel):
    """API ключ компании"""
    key_id: str = Field(description="ID ключа")
    name: str = Field(description="Название ключа")
    key_prefix: str = Field(description="Префикс ключа (первые 8 символов)")
    scopes: list[str] = Field(description="Разрешения ключа")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_used: datetime | None = Field(default=None, description="Время последнего использования")
    company_id: str = Field(description="ID компании")
    created_by: str = Field(description="ID пользователя, создавшего ключ")


class ApiKeyCreate(BaseModel):
    """Запрос на создание API ключа"""
    name: str = Field(description="Название ключа")
    scopes: list[str] = Field(description="Разрешения")


class ApiKeyUpdate(BaseModel):
    """Запрос на обновление API ключа"""
    name: str = Field(description="Новое название ключа")


class ApiKeyCreated(BaseModel):
    """Ответ при создании ключа (показываем секрет ОДИН раз)"""
    key_id: str
    name: str
    secret: str
    scopes: list[str]
    message: str = "Сохраните секрет - он больше не будет показан"


class TeamMemberUpdate(BaseModel):
    """Обновление участника"""
    roles: list[str] = Field(description="Новые роли")


class TeamMemberRoleUpdateResponse(BaseModel):
    """Результат изменения ролей участника."""

    success: bool = True
    user_id: str
    roles: list[str]


class TeamMemberRemoveResponse(BaseModel):
    """Результат удаления участника из компании."""

    success: bool = True
    message: str


class CompanySettingsUpdate(BaseModel):
    """Обновление базовых настроек компании.

    AI-провайдеры конфигурируются отдельным CRUD-роутером ``/ai-providers``
    (см. core.company_ai). Поля legacy (``rag_embedding`` / ``rag_rerank`` /
    ``crm_summarize_provider``) удалены вместе с парсерами в ``core.company_ai``.
    """

    name: str | None = Field(default=None, description="Название компании")
    monthly_budget: float | None = Field(default=None, description="Месячный лимит")
    metadata: JsonObject | None = Field(default=None, description="Дополнительные данные")


class CompanySettingsResponse(BaseModel):
    """Текущие базовые настройки активной компании."""

    company_id: str
    name: str
    subdomain: str | None
    owner_user_id: str | None
    status: str
    monthly_budget: float
    tariff_plan: str
    created_at: str
    metadata: JsonObject


class CompanySettingsUpdatedCompany(BaseModel):
    """Изменяемая часть настроек компании после PATCH."""

    name: str
    monthly_budget: float
    metadata: JsonObject


class CompanySettingsUpdateResponse(BaseModel):
    """Результат обновления настроек компании."""

    success: bool = True
    message: str
    company: CompanySettingsUpdatedCompany


# === Landing lead requests ===


class LeadCreateBody(BaseModel):
    """Публичная заявка с лендинга."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    contact_name: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=64)
    organization_name: str | None = Field(default=None, max_length=200)
    comment: str | None = Field(default=None, max_length=4000)
    job_title: str | None = Field(default=None, max_length=200)
    headcount_range: Literal["1_49", "50_199", "200_499", "500_plus"]
    interested_products: list[Literal["agents", "rag", "crm", "sync", "documents"]] = Field(min_length=1)

    @field_validator("email", "phone", "organization_name", "comment", "job_title")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if normalized == "":
            return None
        return normalized

    @field_validator("email")
    @classmethod
    def validate_email_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        email_regex = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if not re.match(email_regex, value):
            raise ValueError("Invalid email format")
        return value

    @field_validator("phone")
    @classmethod
    def validate_phone_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        phone_digits = "".join(ch for ch in value if ch.isdigit())
        if len(phone_digits) < 10:
            raise ValueError("Invalid phone format")
        return value

    @model_validator(mode="after")
    def require_email_or_phone(self) -> Self:
        if self.email is None and self.phone is None:
            raise ValueError("Укажите email или телефон")
        return self


class LeadRequestRecord(LeadCreateBody):
    """Каноническая запись заявки в shared storage и ответе system UI."""

    lead_request_id: str
    created_at: datetime


class LeadCreateResponse(BaseModel):
    """Результат приема публичной заявки."""

    success: bool = True
    message: str
    lead_request_id: str


# === Public site ===


class PublicSiteBundle(BaseModel):
    """Публичная конфигурация лендинга."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    legal: LegalConfig
    marketing: PublicSiteConfig


class PublicBlogCard(BaseModel):
    """Карточка публичной статьи блога."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    slug: str = Field(min_length=1)
    title_ru: str = Field(min_length=1)
    title_en: str = Field(min_length=1)
    summary_ru: str = Field(min_length=1)
    summary_en: str = Field(min_length=1)


class PublicBlogPost(PublicBlogCard):
    """Полная публичная статья блога."""

    body_ru: str = Field(min_length=1)
    body_en: str = Field(min_length=1)


class PublicBlogListResponse(BaseModel):
    """Список публичных статей блога."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    items: tuple[PublicBlogCard, ...]


class PublicStartupCard(BaseModel):
    """Карточка продукта для внешних каталогов."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: Literal["Humanitec"]
    tagline_ru: str = Field(min_length=1)
    tagline_en: str = Field(min_length=1)
    website_url: str = Field(min_length=1)
    products: tuple[Literal["AI Studio", "Knowledge Base", "NetWorkle", "Sync", "Documents"], ...]
    deployment_modes: tuple[Literal["cloud", "hybrid", "on-premise"], ...]
    logo_url: str = Field(min_length=1)


class LandingDemoSpec(BaseModel):
    """Seed-контракт публичного демо-агента лендинга."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    embed_id: str = Field(min_length=1)
    flow_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    assistant_title: str = Field(min_length=1)
    greeting_message: str = Field(min_length=1)
    sort: int
    image: str = Field(min_length=1)
    show_tool_calls: bool = False
    guest_max_user_messages: int = Field(default=5, ge=1)


# === AI providers (capabilities + custom OpenAI-compatible) ===


class AIProvidersCapabilityUpdate(BaseModel):
    """PUT /api/settings/ai-providers/{capability}: задать override capability компании.

    - ``provider`` платформенный provider capability, ``none`` для отключения rerank
      или ``custom:<id>``;
      для voice — литералы провайдеров речи или ``custom:<id>`` (кроме VAD).
    - ``api_key`` (plaintext) шифруется на сервере; для ``custom:<id>`` не используется
      (ключ в custom-провайдере).
    """

    provider: str = Field(min_length=1)
    api_key: str | None = None
    base_url: str | None = None
    folder_id: str | None = None
    extra_request_headers: dict[str, str] | None = None
    model: str | None = None
    dimension: int | None = Field(default=None, gt=0)
    mrl_output_dimension: int | None = Field(default=None, gt=0)
    fallback_models: list[LLMCallConfig] | None = None
    voice: str | None = None
    language: str | None = None
    sample_rate: int | None = None


class CustomProviderCreate(BaseModel):
    """POST /api/settings/ai-providers/custom: создание custom OpenAI-compatible провайдера."""

    id: str = Field(min_length=1, max_length=32)
    label: str = Field(min_length=1, max_length=128)
    base_url: str
    api_key: str
    extra_request_headers: dict[str, str] | None = None
    extra_request_body: JsonObject | None = None
    rerank_path: str | None = None
    capabilities: list[CapabilityLiteral] = Field(default_factory=list)
    model_by_capability: dict[str, str] = Field(default_factory=dict)


class CustomProviderUpdate(BaseModel):
    """PATCH /api/settings/ai-providers/custom/{id}."""

    label: str | None = Field(default=None, min_length=1, max_length=128)
    base_url: str | None = None
    api_key: str | None = None
    extra_request_headers: dict[str, str] | None = None
    extra_request_body: JsonObject | None = None
    rerank_path: str | None = None
    capabilities: list[CapabilityLiteral] | None = None
    model_by_capability: dict[str, str] | None = None


class ServiceHealthTarget(BaseModel):
    """Цель health-check для сервисного статуса frontend."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str
    health_url: str


class ServiceStatus(BaseModel):
    """Статус микросервиса"""

    name: str
    status: Literal["healthy", "unhealthy", "unknown"]
    url: str
    response_time: float | None = None


class BillingSubscription(BaseModel):
    """Информация о подписке"""
    plan: str
    balance: float
    monthly_budget: float
    current_month_spent: float
    billing_period_start: datetime


class BillingUsageResourceBucket(BaseModel):
    cost: float
    calls: int


class BillingUsageUserBucket(BillingUsageResourceBucket):
    user_name: str | None = None


class BillingUsage(BaseModel):
    """Статистика использования"""
    total_cost: float
    total_calls: int
    by_resource: dict[str, BillingUsageResourceBucket]
    by_user: dict[str, BillingUsageUserBucket]


class ChangePlanRequest(BaseModel):
    """Запрос на смену тарифа"""
    plan: str = Field(description="Новый тарифный план")


class BillingPlanChangeResponse(BaseModel):
    """Результат смены тарифного плана компании."""

    success: bool
    plan: str
    message: str


class PaymentHistoryResponse(BaseModel):
    """История транзакций пополнения баланса."""

    payments: list[TransactionResponse]


class PlatformTracingFacetItem(BaseModel):
    """Одна подсказка с id для фильтра и человекочитаемой подписью."""

    value: str
    label: str


class PlatformTracingFacetsResponse(BaseModel):
    """Подсказки для автокомплита (distinct значения)."""

    items: list[str]


class PlatformTracingFacetItemsResponse(BaseModel):
    """Подсказки company/user: value = id, label = имя + короткий id."""

    items: list[PlatformTracingFacetItem]


class PlatformTracingSpanItem(TraceSpanRecord):
    """Span для админского API с человекочитаемым enrichment."""

    company_name: str | None = None
    user_display_name: str | None = None

    @classmethod
    def from_trace_span(
        cls,
        span: TraceSpanRecord,
        *,
        company_name: str | None,
        user_display_name: str | None,
    ) -> "PlatformTracingSpanItem":
        return cls(
            span_id=span.span_id,
            trace_id=span.trace_id,
            parent_span_id=span.parent_span_id,
            operation_name=span.operation_name,
            kind=span.kind,
            start_time=span.start_time,
            end_time=span.end_time,
            duration_ms=span.duration_ms,
            status=span.status,
            status_message=span.status_message,
            service_name=span.service_name,
            company_id=span.company_id,
            namespace=span.namespace,
            user_id=span.user_id,
            user_name=span.user_name,
            user_groups=span.user_groups,
            session_auth=span.session_auth,
            session_agent=span.session_agent,
            channel=span.channel,
            event_type=span.event_type,
            resource_type=span.resource_type,
            resource_id=span.resource_id,
            attributes=span.attributes,
            events=span.events,
            flow_id=span.flow_id,
            task_id=span.task_id,
            context_id=span.context_id,
            branch_id=span.branch_id,
            node_id=span.node_id,
            agent_name=span.agent_name,
            is_resume=span.is_resume,
            company_name=company_name,
            user_display_name=user_display_name,
        )

    @override
    def to_json_object(self) -> JsonObject:
        payload = super().to_json_object()
        payload["company_name"] = self.company_name
        payload["user_display_name"] = self.user_display_name
        return payload




class PlatformBillingPricesResponse(BaseModel):
    """Эффективный прайс (конфиг + override) и сырой override из shared storage."""

    static_base: dict[str, dict[str, float]]
    effective: dict[str, dict[str, float]]
    storage_override: dict[str, dict[str, float]] | None = None


class PlatformBillingUsageReportResponse(BaseModel):
    """Строки usage из shared БД для админки."""

    items: list[JsonObject]


class PlatformBillingSettlementRulesResponse(BaseModel):
    """Документ правил span settlement (JSON)."""

    document: SettlementRulesDocument


class PlatformBillingCompanyPricesResponse(BaseModel):
    """Эффективный прайс для компании с учетом override и тарифного множителя."""

    company_id: str
    static_base: dict[str, dict[str, float]]
    effective: dict[str, dict[str, float]]
    unit_effective: dict[str, dict[str, float]] | None = None
    tariff_plan: str | None = None
    tariff_multipliers: dict[str, dict[str, float]] = Field(default_factory=dict)
    storage_override: dict[str, dict[str, float]] | None = None


class PlatformBillingCompanyResolveResponse(BaseModel):
    """Разрешение ввода (company_id или subdomain/slug) в company_id для админки биллинга."""

    company_id: str
    name: str
    subdomain: str | None = None


class PlatformBillingCompanyOverviewItem(BaseModel):
    """Строка сводки по компании для таблицы админки биллинга."""

    company_id: str
    name: str
    subdomain: str | None = None
    status: str
    tariff_plan: str
    balance: float
    monthly_budget: float
    current_month_spent: float


class PlatformBillingCompaniesOverviewResponse(BaseModel):
    """Страница списка компаний с полями биллинга."""

    items: list[PlatformBillingCompanyOverviewItem]
    has_more: bool


class PlatformBillingBalanceGrantRequest(BaseModel):
    """Начисление гранта на баланс (только компания system)."""

    company_id: str = Field(min_length=1, description="ID компании-получателя")
    amount: float = Field(
        ge=0.01,
        le=10_000_000.0,
        description="Сумма в RUB",
    )
    note: str | None = Field(
        default=None,
        max_length=2000,
        description="Комментарий к гранту (аудит)",
    )


class PlatformBillingBalanceGrantResponse(BaseModel):
    """Результат начисления гранта."""

    transaction_id: str
    company_id: str
    amount: float
    balance: float
