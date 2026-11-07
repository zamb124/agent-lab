"""CustomerAddressService — сохранённые адреса покупателя + геокодинг."""

from __future__ import annotations

from typing import ClassVar

from core.clients.geocoding.base import Geocoder
from core.customers.contracts import new_id
from core.customers.models import CustomerAddress


class CustomerAddressService:
    """CRUD сохранённых адресов; геокодит при сохранении (best effort)."""

    MAX_ADDRESSES: ClassVar[int] = 10

    def __init__(self, geocoder: Geocoder) -> None:
        self._geocoder: Geocoder = geocoder

    async def list_for_customer(self, customer_id: str) -> list[CustomerAddress]:
        return await CustomerAddress.list_for_customer(customer_id)

    async def add(
        self,
        customer_id: str,
        *,
        address: str,
        label: str = "",
        lat: float | None = None,
        lng: float | None = None,
    ) -> CustomerAddress:
        """Сохранить адрес покупателю.

        Явная точка ``lat``/``lng`` (выбор в чекауте) авторитетнее — геокод
        строки не делается; без точки — геокодер best effort.
        """
        address = address.strip()
        existing = await CustomerAddress.list_for_customer(customer_id)
        for row in existing:
            if row.address.strip().lower() == address.lower():
                await CustomerAddress.touch_used(row.customer_address_id)
                return row
        if len(existing) >= self.MAX_ADDRESSES:
            # самый старый по last_used уходит — чипов больше лимита не бывает
            oldest = existing[-1]
            _ = await CustomerAddress.delete_for_customer(
                customer_id, oldest.customer_address_id
            )
        if lat is None or lng is None:
            geo = None
            try:
                geo = await self._geocoder.geocode(address)
            except Exception:
                geo = None
            if geo is not None:
                lat, lng = geo.lat, geo.lng
        row = CustomerAddress(
            customer_address_id=new_id("caddr"),
            customer_id=customer_id,
            label=label[:64],
            address=address[:500],
            lat=lat,
            lng=lng,
        )
        return await CustomerAddress.objects.create(instance=row)

    async def delete(self, customer_id: str, customer_address_id: str) -> bool:
        return await CustomerAddress.delete_for_customer(
            customer_id, customer_address_id
        )

    async def touch(self, customer_address_id: str) -> None:
        await CustomerAddress.touch_used(customer_address_id)
