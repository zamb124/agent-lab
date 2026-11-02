"""Контракты провайдеров подтверждения телефона (customers.mdc).

Два семейства:
- `CodeSender` — отправка короткого кода (SMS/звонок/мессенджер);
- `DirectVerifier` — провайдер аттестует номер сам (contact share, OAuth ID).

Провайдер конструируется под конкретный бренд (`CustomerAuthBrandConfig`):
креды принадлежат платформе, `available()` отражает конфиг бренда.
"""

from __future__ import annotations

from typing import ClassVar, Protocol

from core.customers.contracts import (
    CodeDelivery,
    DirectVerificationRequest,
    ProviderPhone,
)
from core.customers.enums import (
    CustomerIdentityProvider,
    DirectAuthorizationKind,
    PhoneVerificationChannel,
    PhoneVerificationMethod,
)
from core.types import JsonObject

# Плейсхолдеры conf.json (gate scripts/gates/repo/conf_secrets.py) —
# значение задано формально, креденшла нет: провайдер unavailable.
_PLACEHOLDER_PREFIXES: tuple[str, ...] = ("YOUR_", "ВСТАВИТЬ_", "@var:")


def credential_configured(value: str) -> bool:
    """Креденшл задан реальным значением, а не плейсхолдером conf.json."""
    return bool(value) and not value.startswith(_PLACEHOLDER_PREFIXES)


class CodeSender(Protocol):
    """Канал отправки короткого кода."""

    provider: ClassVar[CustomerIdentityProvider]
    channel: ClassVar[PhoneVerificationChannel]

    def available(self) -> bool: ...

    async def send(self, phone_e164: str, *, code: str) -> CodeDelivery: ...


class DirectVerifier(Protocol):
    """Провайдер, сам аттестующий номер (contact share / OAuth)."""

    provider: ClassVar[CustomerIdentityProvider]
    method: ClassVar[PhoneVerificationMethod]
    direct_kind: ClassVar[DirectAuthorizationKind]

    def available(self) -> bool: ...

    async def fetch_phones(
        self, proof: DirectVerificationRequest
    ) -> list[ProviderPhone]: ...


class ContactShareVerifier(DirectVerifier, Protocol):
    """Direct-метод через «поделиться контактом» в мессенджере (TG/MAX)."""

    def contact_link(self, token: str) -> str:
        """Deep link в бота с одноразовым токеном challenge."""
        ...

    def verify_secret(self, header_token: str | None) -> None:
        """Сверка webhook secret-заголовка с конфигом бренда."""
        ...

    def parse_start(self, payload: JsonObject) -> tuple[str, str] | None:
        """`/start <token>` → (chat_id, token); иначе None."""
        ...

    async def send_contact_request(self, chat_id: str) -> None:
        """Кнопка «Поделиться номером» (request_contact) в ответ на /start."""
        ...

    def parse_update(self, payload: JsonObject) -> DirectVerificationRequest | None:
        """Webhook update → доказательство; None — не contact-сообщение."""
        ...


class OAuthVerifier(DirectVerifier, Protocol):
    """Direct-метод через OAuth2/OIDC (Yandex/VK/Sber ID)."""

    def authorization_url(
        self,
        *,
        state: str,
        redirect_uri: str,
        code_challenge: str | None = None,
    ) -> str: ...
