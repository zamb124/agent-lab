"""CustomerService — покупатели и их привязанные аккаунты.

Только запись/чтение `Customer`/`CustomerIdentity`; сценарии подтверждения —
`CustomerAuthService` (`core.customers.auth_service`).
"""

from __future__ import annotations

from core.customers.contracts import CustomerMe, new_id
from core.customers.enums import (
    CustomerIdentityProvider,
    CustomerStatus,
    PhoneVerificationMethod,
)
from core.customers.models import Customer, CustomerIdentity
from core.customers.ref import CustomerRef


class CustomerService:
    """CRUD-сценарии покупателя и identity-линков (shared DB)."""

    async def get_or_create_by_phone(
        self, phone_e164: str, *, name: str | None = None
    ) -> Customer:
        """Идемпотентный поиск по каноничному E.164."""
        found = await Customer.get_by_phone(phone_e164)
        if found is not None:
            return found
        customer = Customer(customer_id=new_id("cust"), phone_e164=phone_e164, name=name)
        return await Customer.objects.create(instance=customer)

    async def get(self, customer_id: str) -> Customer | None:
        return await Customer.get(customer_id)

    async def link_identity(
        self,
        customer_id: str,
        *,
        provider: CustomerIdentityProvider,
        provider_user_id: str,
        verified_phone_e164: str,
        verification_method: PhoneVerificationMethod,
        scope_company_id: str,
    ) -> CustomerIdentity:
        """Привязать подтверждённый аккаунт; повтор — вернуть существующую."""
        existing = await CustomerIdentity.get_by_provider_user(provider, provider_user_id)
        if existing is not None:
            return existing
        identity = CustomerIdentity(
            identity_id=new_id("custid"),
            customer_id=customer_id,
            provider=provider,
            provider_user_id=provider_user_id,
            verified_phone_e164=verified_phone_e164,
            verification_method=verification_method,
            scope_company_id=scope_company_id,
        )
        return await CustomerIdentity.objects.create(instance=identity)

    async def set_name(self, customer_id: str, name: str) -> Customer | None:
        """Имя профиля кабинета покупателя (`POST /customer-auth/me`)."""
        customer = await Customer.get(customer_id)
        if customer is None:
            return None
        await Customer.set_name(customer_id, name)
        customer.name = name.strip()[:200]
        return customer

    async def to_me(self, ref: CustomerRef) -> CustomerMe | None:
        customer = await Customer.get(ref.customer_id)
        if customer is None or customer.status != CustomerStatus.ACTIVE:
            return None
        return CustomerMe(
            customer_id=customer.customer_id,
            phone_e164=customer.phone_e164,
            scope_company_id=ref.scope_company_id,
            scope_company_ids=ref.scope_company_ids or (ref.scope_company_id,),
            name=customer.name,
        )
