"""
Модели данных для Frontend сервиса
"""
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field


class ApiKey(BaseModel):
    """API ключ компании"""
    key_id: str = Field(description="ID ключа")
    name: str = Field(description="Название ключа")
    key_prefix: str = Field(description="Префикс ключа (первые 8 символов)")
    scopes: List[str] = Field(description="Разрешения ключа")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_used: Optional[datetime] = Field(default=None, description="Время последнего использования")
    company_id: str = Field(description="ID компании")
    created_by: str = Field(description="ID пользователя, создавшего ключ")


class ApiKeyCreate(BaseModel):
    """Запрос на создание API ключа"""
    name: str = Field(description="Название ключа")
    scopes: List[str] = Field(description="Разрешения")


class ApiKeyUpdate(BaseModel):
    """Запрос на обновление API ключа"""
    name: str = Field(description="Новое название ключа")


class ApiKeyCreated(BaseModel):
    """Ответ при создании ключа (показываем секрет ОДИН раз)"""
    key_id: str
    name: str
    secret: str
    scopes: List[str]
    message: str = "Сохраните секрет - он больше не будет показан"


class TeamMemberInfo(BaseModel):
    """Информация об участнике команды"""
    user_id: str = Field(description="ID пользователя")
    name: str = Field(description="Имя")
    email: Optional[str] = Field(default=None, description="Email")
    roles: List[str] = Field(description="Роли в компании")
    joined_at: Optional[datetime] = Field(default=None, description="Дата вступления")
    avatar_url: Optional[str] = Field(default=None, description="URL аватара")


class TeamMemberUpdate(BaseModel):
    """Обновление участника"""
    roles: List[str] = Field(description="Новые роли")


class CompanySettingsUpdate(BaseModel):
    """Обновление базовых настроек компании.

    AI-провайдеры конфигурируются отдельным CRUD-роутером ``/ai-providers``
    (см. core.company_ai). Поля legacy (``rag_embedding`` / ``rag_rerank`` /
    ``crm_summarize_provider``) удалены вместе с парсерами в ``core.company_ai``.
    """

    name: Optional[str] = Field(default=None, description="Название компании")
    monthly_budget: Optional[float] = Field(default=None, description="Месячный лимит")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Дополнительные данные")


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
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    folder_id: Optional[str] = None
    extra_request_headers: Optional[Dict[str, str]] = None
    model: Optional[str] = None
    voice: Optional[str] = None
    language: Optional[str] = None
    sample_rate: Optional[int] = None


class CustomProviderCreate(BaseModel):
    """POST /api/settings/ai-providers/custom: создание custom OpenAI-compatible провайдера."""

    id: str = Field(min_length=1, max_length=32)
    label: str = Field(min_length=1, max_length=128)
    base_url: str
    api_key: str
    extra_request_headers: Optional[Dict[str, str]] = None
    extra_request_body: Optional[Dict[str, Any]] = None
    rerank_path: Optional[str] = None
    capabilities: List[str] = Field(default_factory=list)
    model_by_capability: Dict[str, str] = Field(default_factory=dict)


class CustomProviderUpdate(BaseModel):
    """PATCH /api/settings/ai-providers/custom/{id}."""

    label: Optional[str] = Field(default=None, min_length=1, max_length=128)
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    extra_request_headers: Optional[Dict[str, str]] = None
    extra_request_body: Optional[Dict[str, Any]] = None
    rerank_path: Optional[str] = None
    capabilities: Optional[List[str]] = None
    model_by_capability: Optional[Dict[str, str]] = None


class ServiceStatus(BaseModel):
    """Статус микросервиса"""
    name: str
    status: str  # healthy, unhealthy, unknown
    url: str
    response_time: Optional[float] = None


class BillingSubscription(BaseModel):
    """Информация о подписке"""
    plan: str
    balance: float
    monthly_budget: float
    current_month_spent: float
    billing_period_start: datetime


class BillingUsage(BaseModel):
    """Статистика использования"""
    total_cost: float
    total_calls: int
    by_resource: Dict[str, Dict[str, float]]
    by_user: Dict[str, Dict[str, Any]]


class ChangePlanRequest(BaseModel):
    """Запрос на смену тарифа"""
    plan: str = Field(description="Новый тарифный план")


class PlatformTracingFacetItem(BaseModel):
    """Одна подсказка с id для фильтра и человекочитаемой подписью."""

    value: str
    label: str


class PlatformTracingFacetsResponse(BaseModel):
    """Подсказки для автокомплита (distinct значения)."""

    items: List[str]


class PlatformTracingFacetItemsResponse(BaseModel):
    """Подсказки company/user: value = id, label = имя + короткий id."""

    items: List[PlatformTracingFacetItem]




class PlatformBillingPricesResponse(BaseModel):
    """Эффективный прайс (конфиг + override) и сырой override из shared storage."""

    effective: Dict[str, Dict[str, float]]
    storage_override: Optional[Dict[str, Dict[str, float]]] = None


class PlatformBillingUsageReportResponse(BaseModel):
    """Строки usage из shared БД для админки."""

    items: List[Dict[str, Any]]


class PlatformBillingSettlementRulesResponse(BaseModel):
    """Документ правил span settlement (JSON)."""

    document: Dict[str, Any]


class PlatformBillingCompanyPricesResponse(BaseModel):
    """Эффективный прайс для компании (global merge + override компании)."""

    company_id: str
    effective: Dict[str, Dict[str, float]]
    storage_override: Optional[Dict[str, Dict[str, float]]] = None


class PlatformBillingCompanyResolveResponse(BaseModel):
    """Разрешение ввода (company_id или subdomain/slug) в company_id для админки биллинга."""

    company_id: str
    name: str
    subdomain: Optional[str] = None


class PlatformBillingCompanyOverviewItem(BaseModel):
    """Строка сводки по компании для таблицы админки биллинга."""

    company_id: str
    name: str
    subdomain: Optional[str] = None
    status: str
    tariff_plan: str
    balance: float
    monthly_budget: float
    current_month_spent: float


class PlatformBillingCompaniesOverviewResponse(BaseModel):
    """Страница списка компаний с полями биллинга."""

    items: List[PlatformBillingCompanyOverviewItem]
    has_more: bool


class PlatformBillingBalanceGrantRequest(BaseModel):
    """Начисление гранта на баланс (только компания system)."""

    company_id: str = Field(min_length=1, description="ID компании-получателя")
    amount: float = Field(
        ge=0.01,
        le=10_000_000.0,
        description="Сумма в RUB",
    )
    note: Optional[str] = Field(
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

