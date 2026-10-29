"""
Модели для системы биллинга и тарификации.
"""

from datetime import datetime, timezone
from enum import Enum, StrEnum
from typing import ClassVar, Literal, Self

from oxyde import Field as DbField
from oxyde import execute_raw

from core.facet_query import ADMIN_FACETS_MAX_LIMIT, facet_query_fragment
from core.models.platform_model import PlatformModel
from core.pagination import OffsetPage
from core.types import JsonObject, require_json_object

BillingCostOrigin = Literal["platform", "company"]


class TariffPlan(str, Enum):
    """Тарифные планы"""

    FREE = "free"  # Бесплатный
    BASIC = "basic"  # Базовый
    PREMIUM = "premium"  # Премиум
    ENTERPRISE = "enterprise"  # Корпоративный


class UsageType(StrEnum):
    """Типы использования ресурсов"""

    TOOL_CALL = "tool_call"  # Вызов инструмента
    LLM_REQUEST = "llm_request"  # Запрос к LLM
    EMBEDDING_REQUEST = "embedding_request"  # Запрос к Embedding API
    RERANK_REQUEST = "rerank_request"  # Запрос к rerank API
    AGENT_EXECUTION = "agent_execution"  # Выполнение агента
    FLOW_EXECUTION = "flow_execution"  # Выполнение флоу
    FILE_UPLOAD = "file_upload"  # Загрузка файла
    STORAGE_USAGE = "storage_usage"  # Использование хранилища


class UsageRecord(PlatformModel):
    """Запись использования. Глобальная таблица ``usage`` в ``platform_shared``.

    ``company_id`` есть, но модель глобальная: админский поиск читает все компании.
    Список одной компании фильтрует ``company_id`` явно.
    """

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True

    usage_id: str = DbField(db_pk=True, title="ID записи", json_schema_extra={"readOnly": True})

    class Meta:
        is_table: bool = True
        table_name: str = "usage"

    user_id: str = DbField(db_index=True, title="ID пользователя")
    company_id: str = DbField(db_index=True, title="ID компании")
    session_id: str | None = DbField(default=None, title="ID сессии")
    usage_type: UsageType = DbField(db_index=True, title="Тип использования")
    resource_name: str = DbField(db_index=True, title="Название ресурса")
    cost: float = DbField(default=0.0, title="Стоимость в RUB")
    quantity: int = DbField(default=1, title="Количество")
    metadata: JsonObject = DbField(default_factory=dict, title="Дополнительные данные")
    timestamp: datetime = DbField(
        default_factory=lambda: datetime.now(timezone.utc),
        db_index=True,
    )

    @classmethod
    async def list_unordered_since(cls, company_id: str, since: datetime) -> list[Self]:
        """Записи компании с timestamp не раньше since. Порядка и limit нет."""
        return await cls.objects.filter(
            company_id=company_id,
            timestamp__gte=since,
        ).all()

    @classmethod
    async def admin_search_by_timestamp_desc(
        cls,
        *,
        company_id: str | None = None,
        usage_type: str | None = None,
        resource_name: str | None = None,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> OffsetPage[UsageRecord]:
        """Страница записей, ORDER BY timestamp DESC. company_id, usage_type, resource_name и окно времени равные None не фильтруют."""
        if limit < 1 or limit > ADMIN_USAGE_MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {ADMIN_USAGE_MAX_LIMIT}")
        if offset < 0:
            raise ValueError("offset must be >= 0")

        query = cls.objects.order_by("-timestamp")
        if company_id is not None:
            query = query.filter(company_id=company_id)
        if usage_type is not None:
            query = query.filter(usage_type=UsageType(usage_type))
        if resource_name is not None:
            query = query.filter(resource_name=resource_name)
        if from_time is not None:
            query = query.filter(timestamp__gte=from_time)
        if to_time is not None:
            query = query.filter(timestamp__lt=to_time)

        total = await query.count()
        items = await query.offset(offset).limit(limit).all()
        return OffsetPage[UsageRecord].model_validate(
            {
                "items": items,
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        )

    @classmethod
    async def admin_facet_distinct_usage_types(
        cls,
        *,
        q: str | None = None,
        limit: int = ADMIN_FACETS_MAX_LIMIT,
    ) -> list[str]:
        return await cls._distinct_facet("usage_type", q=q, limit=limit)

    @classmethod
    async def admin_facet_distinct_resource_names(
        cls,
        *,
        q: str | None = None,
        limit: int = ADMIN_FACETS_MAX_LIMIT,
    ) -> list[str]:
        return await cls._distinct_facet("resource_name", q=q, limit=limit)

    @classmethod
    async def _distinct_facet(
        cls, column: Literal["usage_type", "resource_name"], *, q: str | None, limit: int
    ) -> list[str]:
        if limit < 1 or limit > ADMIN_FACETS_MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {ADMIN_FACETS_MAX_LIMIT}")
        fragment = facet_query_fragment(q)
        params: list[str | int] = [limit] if fragment is None else [_like_fragment(fragment), limit]
        rows = await execute_raw(
            _facet_sql(column, has_fragment=fragment is not None), params, using="shared"
        )
        values: list[str] = []
        for row in rows:
            parsed = require_json_object(row, "usage_facet")
            cell = parsed["facet_value"]
            if not isinstance(cell, str) or cell == "":
                raise TypeError("usage facet_value must be a non-empty string")
            values.append(cell)
        return values


ADMIN_USAGE_MAX_LIMIT = 5000
_FacetColumn = Literal["usage_type", "resource_name"]


def _like_fragment(fragment: str) -> str:
    escaped = fragment.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _facet_sql(column: _FacetColumn, *, has_fragment: bool) -> str:
    if column == "usage_type":
        expression = "usage_type::text"
        predicate = "usage_type IS NOT NULL"
    else:
        expression = "resource_name"
        predicate = "resource_name <> ''"
    comparison = f" AND {expression} ILIKE $1 ESCAPE '\\'" if has_fragment else ""
    limit_placeholder = "$2" if has_fragment else "$1"
    return (
        f"SELECT DISTINCT {expression} AS facet_value FROM usage "
        f"WHERE {predicate}{comparison} "
        f"ORDER BY {expression} ASC LIMIT {limit_placeholder}"
    )


# Тарифные цены: множители к базовой цене
# Может быть переопределено в конфигурации сервиса
DEFAULT_TARIFF_PRICES: dict[TariffPlan, dict[str, dict[str, float]]] = {
    TariffPlan.FREE: {
        "llm": {"*": 1.5},
        "embedding": {"*": 1.5},
        "livekit": {"*": 1.5},
        "search": {"*": 1.5},
        "guest": {"*": 1.5},
        "billing": {"*": 1.0},
    },
    TariffPlan.BASIC: {
        "llm": {"*": 1.25},
        "embedding": {"*": 1.25},
        "livekit": {"*": 1.25},
        "search": {"*": 1.25},
        "guest": {"*": 1.25},
        "billing": {"*": 1.0},
    },
    TariffPlan.PREMIUM: {
        "llm": {"*": 1.1},
        "embedding": {"*": 1.1},
        "livekit": {"*": 1.1},
        "search": {"*": 1.1},
        "guest": {"*": 1.1},
        "billing": {"*": 1.0},
    },
    TariffPlan.ENTERPRISE: {
        "llm": {"*": 1.1},
        "embedding": {"*": 1.1},
        "livekit": {"*": 1.1},
        "search": {"*": 1.1},
        "guest": {"*": 1.1},
        "billing": {"*": 1.0},
    },
}
