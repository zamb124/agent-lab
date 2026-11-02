"""Enum'ы домена customer-auth (→ `.cursor/rules/customers.mdc`)."""

from __future__ import annotations

from enum import StrEnum


class ClientKind(StrEnum):
    """Класс клиентского устройства — влияет на приоритет OAuth-провайдеров."""

    WEB_DESKTOP = "web_desktop"
    MOBILE_WEB = "mobile_web"
    TELEGRAM_MINI_APP = "telegram_mini_app"


class CustomerStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class CustomerIdentityProvider(StrEnum):
    """Внешний аккаунт, подтвердивший телефон покупателя."""

    TELEGRAM = "telegram"
    MAX = "max"
    YANDEX = "yandex"
    VK = "vk"
    SBER = "sber"
    PHONE = "phone"  # каналы с кодом: владелец — сам номер
    EMULATOR = "emulator"


class PhoneVerificationMethod(StrEnum):
    """Способ доставки/подтверждения — то, что видит пользователь."""

    TELEGRAM_CONTACT = "telegram_contact"
    MAX_CONTACT = "max_contact"
    YANDEX_ID = "yandex_id"
    VK_ID = "vk_id"
    SBER_ID = "sber_id"
    SMS_CODE = "sms_code"
    EMULATOR = "emulator"


class PhoneVerificationChannel(StrEnum):
    """Канал отправки короткого кода (значение provider_send Channels)."""

    SMS = "sms"
    CALL = "call"
    TELEGRAM = "telegram"
    MAX = "max"


class PhoneChallengeKind(StrEnum):
    DIRECT = "direct"  # аккаунтное подтверждение (contact share, OAuth)
    CODE = "code"  # короткий код из SMS/звонка/мессенджера


class PhoneChallengeStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"  # попытки исчерпаны
    EXPIRED = "expired"
    CANCELLED = "cancelled"  # клиент выбрал другой метод/номер


class DirectAuthorizationKind(StrEnum):
    """Тип direct-метода для UI и state-машины challenge."""

    CONTACT_SHARE = "contact_share"
    OAUTH = "oauth"


class PhoneVerificationErrorCode(StrEnum):
    """Нормализованные ошибки провайдеров → i18n-ключи platform.json."""

    PROVIDER_UNAVAILABLE = "provider_unavailable"
    RATE_LIMITED = "rate_limited"
    INVALID_PHONE = "invalid_phone"
    NOT_DELIVERABLE = "not_deliverable"
    CODE_INVALID = "code_invalid"
    CODE_EXPIRED = "code_expired"
    PROVIDER_MISMATCH = "provider_mismatch"
    CHALLENGE_EXPIRED = "challenge_expired"
    ATTEMPTS_EXCEEDED = "attempts_exceeded"
    PROVIDER_NOT_CONFIGURED = "provider_not_configured"
    INTERNAL_ERROR = "internal_error"
    SESSION_REQUIRED = "session_required"
    SESSION_INVALID = "session_invalid"
    FORBIDDEN_SCOPE = "forbidden_scope"


_PROVIDER_METHOD: dict[CustomerIdentityProvider, PhoneVerificationMethod] = {
    CustomerIdentityProvider.TELEGRAM: PhoneVerificationMethod.TELEGRAM_CONTACT,
    CustomerIdentityProvider.MAX: PhoneVerificationMethod.MAX_CONTACT,
    CustomerIdentityProvider.YANDEX: PhoneVerificationMethod.YANDEX_ID,
    CustomerIdentityProvider.VK: PhoneVerificationMethod.VK_ID,
    CustomerIdentityProvider.SBER: PhoneVerificationMethod.SBER_ID,
    CustomerIdentityProvider.PHONE: PhoneVerificationMethod.SMS_CODE,
    CustomerIdentityProvider.EMULATOR: PhoneVerificationMethod.EMULATOR,
}


def provider_method(provider: CustomerIdentityProvider) -> PhoneVerificationMethod:
    """Метод, которым была получена identity этого провайдера."""
    return _PROVIDER_METHOD[provider]
