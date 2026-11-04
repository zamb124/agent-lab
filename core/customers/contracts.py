"""Контракты customer-auth (→ `.cursor/rules/customers.mdc`).

Лёгкий модуль: импортируется `core.models.context_models`, поэтому
здесь — только Pydantic-типы без `PlatformModel` и сервисов.
"""

from __future__ import annotations

import time
from typing import Literal
from uuid import uuid4

from pydantic import Field

from core.customers.enums import (
    ClientKind,
    CustomerIdentityProvider,
    DirectAuthorizationKind,
    PhoneChallengeKind,
    PhoneChallengeStatus,
    PhoneVerificationChannel,
    PhoneVerificationMethod,
)
from core.customers.ref import CustomerRef
from core.models.base import StrictBaseModel


class CustomerMe(CustomerRef):
    """Профиль покупателя для API `/public/customer/me`."""

    name: str | None = None


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:24]}"


def now_ts() -> int:
    return int(time.time())


class MethodOption(StrictBaseModel):
    """Один пункт выбора способа подтверждения в `methods` из start."""

    kind: PhoneVerificationMethod
    ui: Literal["deep_link", "oauth", "contact_share", "code_input", "auto"]
    priority: int = 0
    provider: CustomerIdentityProvider | None = None
    deep_link: str | None = None
    provider_data: dict[str, str] | None = None


class CodeDelivery(StrictBaseModel):
    """Результат отправки короткого кода провайдером."""

    channel: PhoneVerificationChannel
    provider: CustomerIdentityProvider
    status: Literal["sent", "delivered", "already_sent"] = "sent"
    provider_message_id: str | None = None
    price: float | None = None
    currency: str | None = None
    meta: dict[str, str] | None = None


class ProviderPhone(StrictBaseModel):
    """Телефон, аттестованный внешним провайдером (OAuth/контакт)."""

    phone_e164: str
    verified: bool = True
    default: bool = False


class DirectVerificationRequest(StrictBaseModel):
    """Доказательство direct-подтверждения — приходит от webhook/callback/client."""

    kind: DirectAuthorizationKind
    provider: CustomerIdentityProvider
    contact_phone: str | None = None  # для contact_share — номер из contact
    provider_user_id: str | None = None  # sender id (Telegram/MAX)
    contact_user_id: str | None = None  # owner id контакта (Telegram/MAX)
    oauth_code: str | None = None
    oauth_state: str | None = None
    oauth_code_verifier: str | None = None  # PKCE verifier (VK ID требует)
    oauth_device_id: str | None = None  # device_id из redirect (VK ID требует)
    redirect_uri: str | None = None
    meta: dict[str, str] | None = None


class AuthStartPayload(StrictBaseModel):
    """Тело `POST .../customer-auth/start`."""

    company_id: str  # компания-владелец витрины/продукта
    phone: str | None = None
    flow_hint: Literal["checkout"] = "checkout"
    client: ClientKind = ClientKind.MOBILE_WEB


class MethodChosenPayload(StrictBaseModel):
    """Тело `POST .../customer-auth/method`."""

    challenge_id: str
    company_id: str
    method: PhoneVerificationMethod
    return_url: str | None = None  # куда вернуть после OAuth


class AuthVerifyPayload(StrictBaseModel):
    """Тело `POST .../customer-auth/verify`."""

    challenge_id: str
    company_id: str
    code: str | None = None
    direct: DirectVerificationRequest | None = None


class MethodChallengedView(StrictBaseModel):
    """Ответ на `method_chosen`: отправлен код / ждём direct-подтверждение."""

    status: Literal["challenge_sent", "awaiting_contact", "awaiting_oauth"]
    challenge_id: str
    kind: PhoneChallengeKind
    method: PhoneVerificationMethod
    channel: PhoneVerificationChannel | None = None
    expires_in: int
    resend_after: int = 0
    deep_link: str | None = None
    oauth_url: str | None = None


class AuthStartView(StrictBaseModel):
    """Ответ `auth/start`: challenge + доступные методы."""

    status: Literal["challenge_pending"] = "challenge_pending"
    challenge_id: str
    phone_masked: str | None = None
    methods: list[MethodOption] = Field(default_factory=list)


class AuthStatusView(StrictBaseModel):
    """Ответ `auth/status` для polling direct/OAuth потоков."""

    status: PhoneChallengeStatus
    challenge_id: str
    method: PhoneVerificationMethod | None = None
    customer: "CustomerMe | None" = None


class AuthVerifyView(StrictBaseModel):
    """Ответ `auth/verify`."""

    status: Literal["confirmed", "pending"]
    customer: CustomerMe | None = None


class OAuthStartView(StrictBaseModel):
    """Куда отправить пользователя за OAuth-подтверждением."""

    url: str


class CustomerAddressView(StrictBaseModel):
    """Сохранённый адрес покупателя (чипы в чекауте)."""

    customer_address_id: str
    label: str = ""
    address: str
    lat: float | None = None
    lng: float | None = None


class AddressCreatePayload(StrictBaseModel):
    """Тело `POST .../customer-auth/addresses`."""

    address: str = Field(min_length=3, max_length=500)
    label: str = Field(default="", max_length=64)


class AddressListView(StrictBaseModel):
    """Ответ `GET .../customer-auth/addresses`."""

    addresses: list[CustomerAddressView] = Field(default_factory=list)


class TelegramWebhookUpdate(StrictBaseModel):
    """Минимально нужная форма Telegram update для contact share."""

    update_id: int
    message: dict[str, object] | None = None


__all__ = [
    "AuthStartPayload",
    "AuthStartView",
    "AuthStatusView",
    "AuthVerifyPayload",
    "AuthVerifyView",
    "AddressCreatePayload",
    "AddressListView",
    "CodeDelivery",
    "CustomerAddressView",
    "CustomerMe",
    "CustomerRef",
    "DirectVerificationRequest",
    "MethodChosenPayload",
    "MethodChallengedView",
    "MethodOption",
    "OAuthStartView",
    "ProviderPhone",
    "TelegramWebhookUpdate",
    "new_id",
    "now_ts",
]
