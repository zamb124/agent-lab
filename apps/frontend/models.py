"""
Модели данных для Frontend сервиса
"""
import re
from datetime import datetime
from typing import ClassVar, Literal, Self, override

from oxyde import Field as DbField
from oxyde import Index
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from apps.frontend.cookie_consent import CookieConsentDecision, CookieConsentLocale
from core.ai.company_settings import CapabilityLiteral
from core.ai.llm_config import LLMCallConfig
from core.billing.settlement_rules import SettlementRulesDocument
from core.config.models import LegalConfig, PublicSiteConfig
from core.models.platform_model import PlatformModel
from core.tracing.models import Span
from core.types import JsonObject


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
    (см. core.ai.company_settings). Поля legacy (``rag_embedding`` / ``rag_rerank`` /
    ``crm_summarize_provider``) удалены вместе с парсерами в ``core.ai.company_settings``.
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
            raise ValueError("Provide email or phone")
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
    cookie_consent_text_version: str
    analytics_configured: bool


class CookieConsentCreateBody(BaseModel):
    """Тело публичной записи согласия на аналитические cookie."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    decision: CookieConsentDecision
    analytics_allowed: bool
    consent_text_version: str = Field(min_length=1)
    locale: CookieConsentLocale
    supersedes_cookie_consent_id: str | None = None

    @field_validator("supersedes_cookie_consent_id")
    @classmethod
    def supersedes_id_non_empty(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value.strip() == "":
            raise ValueError("supersedes_cookie_consent_id must be non-empty when set")
        return value.strip()


class CookieConsentRecord(PlatformModel):
    """Журнал согласия на cookie. Таблица ``cookie_consents`` в ``platform_shared``."""

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    cookie_consent_id: str = DbField(db_pk=True, max_length=36)

    class Meta:
        is_table: bool = True
        table_name: str = "cookie_consents"
        indexes: list[Index] = [Index(("apex_domain", "created_at"))]

    created_at: datetime = DbField(db_index=True)
    brand_host: str = DbField(max_length=255)
    apex_domain: str = DbField(max_length=255)
    decision: CookieConsentDecision = DbField()
    analytics_allowed: bool = DbField()
    consent_text_version: str = DbField(max_length=64)
    locale: CookieConsentLocale = DbField()
    request_id: str = DbField(max_length=128)
    user_agent: str = DbField(max_length=512)
    ip_hash: str = DbField(max_length=64)
    supersedes_cookie_consent_id: str | None = DbField(default=None, max_length=36)


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

    name: str = Field(min_length=1)
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
    sort: int
    image: str = Field(min_length=1)
    guest_max_user_messages: int = Field(default=5, ge=1)


# === AI providers (capabilities + custom OpenAI-compatible) ===


class AIProvidersCapabilityUpdate(BaseModel):
    """PUT /api/settings/ai-providers/{capability}: задать override capability компании.

    - ``enabled=false`` отключает rerank; включённые capability используют
      платформенный provider capability или ``custom:<id>``;
      для voice — литералы провайдеров речи или ``custom:<id>`` (кроме VAD).
    - ``api_key`` (plaintext) шифруется на сервере; для ``custom:<id>`` не используется
      (ключ в custom-провайдере).
    """

    enabled: bool | None = None
    provider: str | None = Field(default=None, min_length=1)
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


class PlatformTracingSpanItem(Span):
    """Span для админского API с человекочитаемым enrichment."""

    company_name: str | None = None
    user_display_name: str | None = None

    @classmethod
    def from_trace_span(
        cls,
        span: Span,
        *,
        company_name: str | None,
        user_display_name: str | None,
    ) -> "PlatformTracingSpanItem":
        item = cls.model_validate(span.model_dump(include=set(Span.model_fields)))
        item.company_name = company_name
        item.user_display_name = user_display_name
        return item

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
