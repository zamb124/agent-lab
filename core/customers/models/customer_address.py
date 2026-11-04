"""Сохранённый адрес покупателя платформы (shared DB, как `Customer`).

Адрес привязан к `Customer` (глобальный покупатель по телефону), не к
компании: один покупатель заказывает у разных tenant'ов. Координаты —
нормализованный результат геокодинга; текст `address` — то, что видит юзер.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import ClassVar, Self

from oxyde import Field as DbField
from pydantic import ConfigDict

from core.models.platform_model import PlatformModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


class CustomerAddress(PlatformModel):
    """Один сохранённый адрес `Customer` (макс. несколько штук, чипы в чекауте)."""

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True
    model_config: ClassVar[ConfigDict] = ConfigDict(
        json_schema_extra={"storage_prefix": "customer"}
    )

    customer_address_id: str = DbField(db_pk=True, max_length=64)
    customer_id: str = DbField(max_length=64, db_index=True)
    label: str = DbField(default="", max_length=64)
    address: str = DbField(default="", max_length=500)
    lat: float | None = DbField(default=None)
    lng: float | None = DbField(default=None)
    created_at: datetime = DbField(default_factory=_now)
    last_used_at: datetime = DbField(default_factory=_now)

    class Meta:
        is_table: bool = True
        table_name: str = "customer_addresses"

    @classmethod
    async def list_for_customer(cls, customer_id: str) -> list[Self]:
        """Адреса покупателя по недавности использования."""
        rows = await cls.objects.filter(customer_id=customer_id).all()
        return sorted(rows, key=lambda r: r.last_used_at, reverse=True)

    @classmethod
    async def get_for_customer(
        cls, customer_id: str, customer_address_id: str
    ) -> Self | None:
        """Адрес, только если он принадлежит этому покупателю."""
        return await cls.objects.filter(
            customer_id=customer_id, customer_address_id=customer_address_id
        ).get_or_none()

    @classmethod
    async def touch_used(cls, customer_address_id: str) -> None:
        _ = await cls.objects.filter(
            customer_address_id=customer_address_id
        ).update(last_used_at=_now())

    @classmethod
    async def delete_for_customer(
        cls, customer_id: str, customer_address_id: str
    ) -> bool:
        deleted = await cls.objects.filter(
            customer_id=customer_id, customer_address_id=customer_address_id
        ).delete()
        return bool(deleted)
