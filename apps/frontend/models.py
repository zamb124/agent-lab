"""
Модели данных для Frontend сервиса
"""
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from core.clients.llm.config import LLMCallConfig
from core.company_ai import CapabilityLiteral


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


class TeamMemberInfo(BaseModel):
    """Информация об участнике команды"""
    user_id: str = Field(description="ID пользователя")
    name: str = Field(description="Имя")
    email: str | None = Field(default=None, description="Email")
    roles: list[str] = Field(description="Роли в компании")
    joined_at: datetime | None = Field(default=None, description="Дата вступления")
    avatar_url: str | None = Field(default=None, description="URL аватара")


class TeamMemberUpdate(BaseModel):
    """Обновление участника"""
    roles: list[str] = Field(description="Новые роли")


class CompanySettingsUpdate(BaseModel):
    """Обновление базовых настроек компании.

    AI-провайдеры конфигурируются отдельным CRUD-роутером ``/ai-providers``
    (см. core.company_ai). Поля legacy (``rag_embedding`` / ``rag_rerank`` /
    ``crm_summarize_provider``) удалены вместе с парсерами в ``core.company_ai``.
    """

    name: str | None = Field(default=None, description="Название компании")
    monthly_budget: float | None = Field(default=None, description="Месячный лимит")
    metadata: dict[str, Any] | None = Field(default=None, description="Дополнительные данные")


# === AI providers (capabilities + custom OpenAI-compatible) ===


class AIProvidersCapabilityUpdate(BaseModel):
    """PUT /api/settings/ai-providers/{capability}: задать override capability компании.

    - ``provider`` платформенный (``openrouter|openai|bothub|yandex|provider_litserve``)
      или ``custom:<id>``; для rerank допустимы ``inherit|none|provider_litserve|custom:<id>``;
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
    extra_request_body: dict[str, Any] | None = None
    rerank_path: str | None = None
    capabilities: list[CapabilityLiteral] = Field(default_factory=list)
    model_by_capability: dict[str, str] = Field(default_factory=dict)


class CustomProviderUpdate(BaseModel):
    """PATCH /api/settings/ai-providers/custom/{id}."""

    label: str | None = Field(default=None, min_length=1, max_length=128)
    base_url: str | None = None
    api_key: str | None = None
    extra_request_headers: dict[str, str] | None = None
    extra_request_body: dict[str, Any] | None = None
    rerank_path: str | None = None
    capabilities: list[CapabilityLiteral] | None = None
    model_by_capability: dict[str, str] | None = None


class ServiceStatus(BaseModel):
    """Статус микросервиса"""
    name: str
    status: str  # healthy, unhealthy, unknown
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




class PlatformBillingPricesResponse(BaseModel):
    """Эффективный прайс (конфиг + override) и сырой override из shared storage."""

    static_base: dict[str, dict[str, float]]
    effective: dict[str, dict[str, float]]
    storage_override: dict[str, dict[str, float]] | None = None


class PlatformBillingUsageReportResponse(BaseModel):
    """Строки usage из shared БД для админки."""

    items: list[dict[str, Any]]


class PlatformBillingSettlementRulesResponse(BaseModel):
    """Документ правил span settlement (JSON)."""

    document: dict[str, Any]


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
