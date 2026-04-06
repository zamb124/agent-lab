"""
Модели данных для Frontend сервиса
"""
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
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


class TeamInvite(BaseModel):
    """Приглашение участника"""
    email: str = Field(description="Email пользователя")
    role: str = Field(description="Роль (owner, admin, developer, viewer)")


class TeamMemberUpdate(BaseModel):
    """Обновление участника"""
    roles: List[str] = Field(description="Новые роли")


class CompanySettingsUpdate(BaseModel):
    """Обновление настроек компании"""
    name: Optional[str] = Field(default=None, description="Название компании")
    monthly_budget: Optional[float] = Field(default=None, description="Месячный лимит")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Дополнительные данные")


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


class TopUpRequest(BaseModel):
    """Запрос на пополнение баланса"""
    amount: float = Field(ge=100, le=1000000, description="Сумма пополнения (100-1000000 RUB)")
    payment_method: str = Field(default="card", description="Способ оплаты")


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


class PlatformTracingSpansPageResponse(BaseModel):
    """Страница spans админ-поиска с курсором."""

    items: List[Dict[str, Any]]
    next_cursor: Optional[str] = None


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

