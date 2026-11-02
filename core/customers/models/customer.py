"""Customer — глобальный покупатель платформы, привязанный к номеру телефона.

Покупатель не является `User`/`member` компании: один и тот же номер
авторизуется у разных tenant'ов, а `scope_company_id` живёт в его
сессии/challenge, не в строке `Customer`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import ClassVar, Self

from oxyde import Field as DbField
from pydantic import ConfigDict

from core.customers.enums import CustomerStatus
from core.models.platform_model import PlatformModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Customer(PlatformModel):
    """Единственная строка на `phone_e164` (shared DB, `__global_model__`)."""

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True
    model_config: ClassVar[ConfigDict] = ConfigDict(
        json_schema_extra={"storage_prefix": "customer"}
    )

    customer_id: str = DbField(db_pk=True, max_length=64)
    phone_e164: str = DbField(max_length=32, db_index=True)
    name: str | None = DbField(default=None, max_length=200)
    status: CustomerStatus = DbField(default=CustomerStatus.ACTIVE)
    created_at: datetime = DbField(default_factory=_now)
    updated_at: datetime = DbField(default_factory=_now)
    last_login_at: datetime | None = DbField(default=None)

    class Meta:
        is_table: bool = True
        table_name: str = "customers"

    @classmethod
    async def get_by_phone(cls, phone_e164: str) -> Self | None:
        """Точная строка по каноничному E.164."""
        return await cls.objects.filter(phone_e164=phone_e164).get_or_none()

    @classmethod
    async def touch_login(cls, customer_id: str) -> None:
        _ = await cls.objects.filter(customer_id=customer_id).update(
            last_login_at=_now(), updated_at=_now()
        )
