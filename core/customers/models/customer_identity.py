"""CustomerIdentity — привязка внешнего аккаунта к покупателю.

`(provider, provider_user_id)` уникален: один TG/VK-аккаунт — один customer.
`provider_user_id="phone:<e164>"` — каноничная identity от code-каналов.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index
from pydantic import ConfigDict

from core.customers.enums import CustomerIdentityProvider, PhoneVerificationMethod
from core.models.platform_model import PlatformModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


class CustomerIdentity(PlatformModel):
    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True
    model_config: ClassVar[ConfigDict] = ConfigDict(
        json_schema_extra={"storage_prefix": "custid"}
    )

    identity_id: str = DbField(db_pk=True, max_length=64)
    customer_id: str = DbField(max_length=64, db_index=True)
    provider: CustomerIdentityProvider = DbField()
    provider_user_id: str = DbField(max_length=128)
    verified_phone_e164: str = DbField(max_length=32, db_index=True)
    verification_method: PhoneVerificationMethod = DbField()
    scope_company_id: str = DbField(max_length=64)  # витрина первого подтверждения
    last_used_at: datetime | None = DbField(default=None)
    created_at: datetime = DbField(default_factory=_now)
    updated_at: datetime = DbField(default_factory=_now)

    class Meta:
        is_table: bool = True
        table_name: str = "customer_identities"
        indexes: list[Index] = [
            Index(["provider", "provider_user_id"], unique=True),
        ]

    @classmethod
    async def get_by_provider_user(
        cls, provider: CustomerIdentityProvider, provider_user_id: str
    ) -> Self | None:
        return await cls.objects.filter(
            provider=provider, provider_user_id=provider_user_id
        ).get_or_none()

    @classmethod
    async def list_for_customer(cls, customer_id: str) -> list[Self]:
        return await cls.objects.filter(customer_id=customer_id).all()

    @classmethod
    async def mark_used(cls, identity_id: str) -> None:
        _ = await cls.objects.filter(identity_id=identity_id).update(
            last_used_at=_now(), updated_at=_now()
        )
