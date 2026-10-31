"""Таблица идентичности."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index, atomic
from pydantic import Field

from core.models.billing_models import TariffPlan
from core.models.identity_models.contracts import SYSTEM_COMPANY_ID
from core.models.platform_model import PlatformModel
from core.types import JsonObject


class Company(PlatformModel):
    """Компания. Глобальная таблица ``companies`` в ``platform_shared``.

    ``members`` — JSON-поле этой модели: состав ролей читается вместе с компанией.
    """

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True

    company_id: str = DbField(
        db_pk=True,
        title="ID компании",
        description="Уникальный ID компании",
        json_schema_extra={"readonly": True},
    )

    class Meta:
        is_table: bool = True
        table_name: str = "companies"
        indexes: list[Index] = [
            Index(["subdomain"], unique=True, where="subdomain IS NOT NULL"),
        ]

    name: str = DbField(
        title="Название",
        description="Название компании",
        json_schema_extra={"placeholder": "Моя компания"},
    )
    subdomain: str | None = DbField(
        default=None,
        title="Поддомен",
        description="Поддомен компании (company.linnex.io)",
        json_schema_extra={"groups": {"admin": {"readonly": False}, "user": {"readonly": True}}},
    )
    owner_user_id: str | None = Field(
        default=None,
        title="Владелец",
        description="ID пользователя-владельца компании",
        json_schema_extra={"groups": {"admin": {"readonly": False}, "user": {"readonly": True}}},
    )
    members: dict[str, list[str]] = Field(
        default_factory=dict,
        title="Участники",
        description="user_id -> [role1, role2]",
        json_schema_extra={"groups": {"admin": {"readonly": False}, "user": {"readonly": True}}},
    )
    status: str = Field(
        default="active",
        title="Статус",
        description="Статус компании (active, suspended)",
        json_schema_extra={
            "groups": {"admin": {"editable_in_table": True}, "user": {"readonly": True}}
        },
    )
    metadata: JsonObject = Field(
        default_factory=dict,
        title="Метаданные",
        description="Дополнительные данные компании",
        json_schema_extra={"groups": {"admin": {"readonly": False}, "user": {"readonly": True}}},
    )
    tariff_plan: TariffPlan = Field(
        default=TariffPlan.FREE,
        title="Тарифный план",
        description="Тарифный план компании (free, basic, premium, enterprise)",
        json_schema_extra={"groups": {"admin": {"readonly": False}, "user": {"readonly": True}}},
    )
    balance: float = Field(
        default=50.0,
        title="Баланс",
        description="Баланс компании в RUB; отрицательное значение — задолженность после списаний",
        json_schema_extra={"groups": {"admin": {"readonly": False}, "user": {"readonly": True}}},
    )
    monthly_budget: float = Field(
        default=0.0,
        title="Месячный лимит",
        description="Месячное самоограничение в RUB (0 = без самоограничения)",
        ge=0.0,
        json_schema_extra={"groups": {"admin": {"readonly": False}, "user": {"readonly": True}}},
    )
    current_month_spent: float = Field(
        default=0.0,
        title="Потрачено в месяце",
        description="Потрачено компанией в текущем месяце в RUB",
        ge=0.0,
        json_schema_extra={"readonly": True},
    )
    billing_period_start: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        ),
        title="Начало расчетного периода",
        description="Начало текущего расчетного периода",
        json_schema_extra={"readonly": True},
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Создана",
        description="Время создания компании",
        json_schema_extra={"readonly": True},
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Обновлена",
        description="Время последнего обновления",
        json_schema_extra={"readonly": True},
    )

    @classmethod
    async def page_named_after_system_by_name_and_company_id_asc(
        cls, *, limit: int, offset: int
    ) -> tuple[list[Self], bool]:
        """Окно компаний: при offset 0 первой идёт system, дальше ORDER BY name ASC, company_id ASC. limit < 1, offset < 0 и отсутствие system — ValueError."""
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if offset < 0:
            raise ValueError("offset must be >= 0")
        system = await cls.get(SYSTEM_COMPANY_ID)
        if system is None:
            raise ValueError("system company is required")
        if offset == 0:
            head = [system]
            rest_offset = 0
            rest_limit = limit - 1
        else:
            head = []
            rest_offset = offset - 1
            rest_limit = limit
        rest = await (
            cls.objects.exclude(company_id=SYSTEM_COMPANY_ID)
            .order_by("name", "company_id")
            .limit(rest_limit + 1)
            .offset(rest_offset)
            .all()
        )
        has_more = len(rest) > rest_limit
        return [*head, *rest[:rest_limit]], has_more

    @classmethod
    async def by_subdomain(cls, subdomain: str) -> Self | None:
        if subdomain == "":
            raise ValueError("subdomain is required")
        return await cls.objects.filter(subdomain=subdomain).get_or_none()

    @classmethod
    async def put_member_roles(
        cls,
        company_id: str,
        user_id: str,
        roles: Sequence[str],
    ) -> Self:
        if not company_id.strip():
            raise ValueError("company_id is required")
        if not user_id.strip():
            raise ValueError("user_id is required")
        normalized = [role.strip() for role in roles if role.strip()]
        if not normalized:
            raise ValueError("company membership roles must be non-empty")
        async with atomic(using="shared"):
            company = await cls.objects.filter(company_id=company_id).for_update().get()
            members = dict(company.members)
            members[user_id] = list(normalized)
            company.members = members
            _ = await company.save(update_fields=["members"])
            return company

    @classmethod
    async def add_balance(cls, company_id: str, amount: float) -> Self:
        if company_id == "":
            raise ValueError("company_id is required")
        async with atomic(using="shared"):
            company = await cls.objects.filter(company_id=company_id).for_update().get_or_none()
            if company is None:
                raise ValueError(f"Company {company_id} not found")
            company.balance += amount
            _ = await company.save(update_fields=["balance"])
            return company

    @classmethod
    async def discard_member(cls, company_id: str, user_id: str) -> Self:
        if not company_id.strip():
            raise ValueError("company_id is required")
        if not user_id.strip():
            raise ValueError("user_id is required")
        async with atomic(using="shared"):
            company = await cls.objects.filter(company_id=company_id).for_update().get()
            if user_id not in company.members:
                raise ValueError(f"company member not found: {user_id}")
            members = dict(company.members)
            del members[user_id]
            company.members = members
            _ = await company.save(update_fields=["members"])
            return company
