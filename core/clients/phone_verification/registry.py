"""Реестр провайдеров customer-auth на бренд.

`PhoneVerificationRegistry.build(settings, apex)` собирает каналы из
`customer_auth.brands[apex]` + эмулятор. Все провайдеры платформенные
(BYOK у мерчанта нет). SMS — только фолбек: попадает в `code_senders`
всегда после прочих каналов.
"""

from __future__ import annotations

from core.clients.phone_verification.base import (
    CodeSender,
    ContactShareVerifier,
    DirectVerifier,
    OAuthVerifier,
)
from core.clients.phone_verification.max_bot import MaxContactProvider
from core.clients.phone_verification.mock import EmulatorCodeSender, EmulatorDirectVerifier
from core.clients.phone_verification.oauth_id import (
    SberIdProvider,
    VkIdProvider,
    YandexIdProvider,
)
from core.clients.phone_verification.smsru import SmsruCodeSender
from core.clients.phone_verification.telegram_bot import TelegramContactProvider
from core.config.models import CustomerAuthConfig
from core.customers.enums import (
    CustomerIdentityProvider,
    PhoneVerificationMethod,
)


class PhoneVerificationRegistry:
    """Каналы, доступные на конкретном apex-бренде."""

    def __init__(
        self,
        *,
        code_senders: list[CodeSender],
        direct_verifiers: list[DirectVerifier],
        contact_share: dict[PhoneVerificationMethod, ContactShareVerifier],
        oauth: dict[PhoneVerificationMethod, OAuthVerifier],
    ) -> None:
        self.code_senders: list[CodeSender] = code_senders
        self.direct_verifiers: list[DirectVerifier] = direct_verifiers
        self.contact_share: dict[PhoneVerificationMethod, ContactShareVerifier] = contact_share
        self.oauth: dict[PhoneVerificationMethod, OAuthVerifier] = oauth

    @classmethod
    def build(cls, cfg: CustomerAuthConfig, apex: str) -> "PhoneVerificationRegistry":
        brand = cfg.brand(apex)
        telegram = TelegramContactProvider(brand.telegram if brand else None)
        max_bot = MaxContactProvider(brand.max if brand else None)
        yandex = YandexIdProvider(brand.yandex if brand else None)
        vk = VkIdProvider(brand.vk if brand else None)
        sber = SberIdProvider(brand.sber if brand else None)
        smsru = SmsruCodeSender(brand.smsru if brand else None)
        emulator_code = EmulatorCodeSender(enabled=cfg.emulator_enabled)
        emulator_direct = EmulatorDirectVerifier(enabled=cfg.emulator_enabled)

        code_senders: list[CodeSender] = [smsru, emulator_code]
        direct: list[DirectVerifier] = [telegram, max_bot, yandex, vk, sber, emulator_direct]
        contact_share: dict[PhoneVerificationMethod, ContactShareVerifier] = {
            PhoneVerificationMethod.TELEGRAM_CONTACT: telegram,
            PhoneVerificationMethod.MAX_CONTACT: max_bot,
        }
        oauth: dict[PhoneVerificationMethod, OAuthVerifier] = {
            PhoneVerificationMethod.YANDEX_ID: yandex,
            PhoneVerificationMethod.VK_ID: vk,
            PhoneVerificationMethod.SBER_ID: sber,
        }
        return cls(
            code_senders=code_senders,
            direct_verifiers=direct,
            contact_share=contact_share,
            oauth=oauth,
        )

    def direct_for(self, provider: CustomerIdentityProvider) -> DirectVerifier | None:
        for verifier in self.direct_verifiers:
            if verifier.provider == provider:
                return verifier
        return None

    def contact_share_for(self, provider: CustomerIdentityProvider) -> ContactShareVerifier | None:
        for verifier in self.contact_share.values():
            if verifier.provider == provider:
                return verifier
        return None
