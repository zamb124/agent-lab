"""Эмулятор провайдеров customer-auth для dev/test (`emulator_enabled`).

- `EmulatorCodeSender` — «отправляет» любой код (реальный — тот, что в
  challenge); `send` никуда не ходит, фиксирует доставку в `meta`.
- `EmulatorDirectVerifier` — direct-подтверждение без внешнего аккаунта:
  `fetch_phones` возвращает номер из `proof.contact_phone` — UI показывает
  кнопку «Подтвердить (эмулятор)», что и закрывает поток на тестовом стенде.
"""

from __future__ import annotations

from typing import ClassVar

from core.customers.contracts import (
    CodeDelivery,
    DirectVerificationRequest,
    ProviderPhone,
)
from core.customers.enums import (
    CustomerIdentityProvider,
    DirectAuthorizationKind,
    PhoneVerificationChannel,
    PhoneVerificationErrorCode,
    PhoneVerificationMethod,
)
from core.customers.errors import ProviderError
from core.customers.phone import normalize_phone_e164


class EmulatorCodeSender:
    provider: ClassVar[CustomerIdentityProvider] = CustomerIdentityProvider.EMULATOR
    channel: ClassVar[PhoneVerificationChannel] = PhoneVerificationChannel.SMS

    def __init__(self, *, enabled: bool) -> None:
        self._enabled: bool = enabled

    def available(self) -> bool:
        return self._enabled

    async def send(self, phone_e164: str, *, code: str) -> CodeDelivery:
        if not self._enabled:
            raise ProviderError(PhoneVerificationErrorCode.PROVIDER_NOT_CONFIGURED)
        return CodeDelivery(
            channel=self.channel,
            provider=self.provider,
            status="delivered",
            provider_message_id=f"emu-{code}",
            meta={"emulated": "1", "to": phone_e164},
        )


class EmulatorDirectVerifier:
    provider: ClassVar[CustomerIdentityProvider] = CustomerIdentityProvider.EMULATOR
    method: ClassVar[PhoneVerificationMethod] = PhoneVerificationMethod.EMULATOR
    direct_kind: ClassVar[DirectAuthorizationKind] = DirectAuthorizationKind.CONTACT_SHARE

    def __init__(self, *, enabled: bool) -> None:
        self._enabled: bool = enabled

    def available(self) -> bool:
        return self._enabled

    async def fetch_phones(
        self, proof: DirectVerificationRequest
    ) -> list[ProviderPhone]:
        if not self._enabled:
            raise ProviderError(PhoneVerificationErrorCode.PROVIDER_NOT_CONFIGURED)
        phone = normalize_phone_e164(proof.contact_phone or "")
        if phone is None:
            raise ProviderError(PhoneVerificationErrorCode.INVALID_PHONE)
        return [ProviderPhone(phone_e164=phone, verified=True, default=True)]
