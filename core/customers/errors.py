"""Ошибки customer-auth — единый контракт провайдеров и сервиса.

Внутри домена ошибки поднимаются как `CustomerAuthError(code)`, на
границе `op_*`/REST мапятся в `PlatformBoundaryError`/`WsCommandError`
с `error_code` из `PhoneVerificationErrorCode` (i18n-ключи platform.json).
"""

from __future__ import annotations

from core.customers.enums import PhoneVerificationErrorCode


class CustomerAuthError(Exception):
    """Доменная ошибка customer-auth с нормализованным кодом."""

    def __init__(self, code: PhoneVerificationErrorCode, detail: str = "") -> None:
        super().__init__(detail or code.value)
        self.code: PhoneVerificationErrorCode = code
        self.detail: str = detail


class ProviderError(CustomerAuthError):
    """Ошибка конкретного провайдера (на границе `provider_send`/`fetch_phones`)."""

    def __init__(
        self,
        code: PhoneVerificationErrorCode,
        detail: str = "",
        *,
        retryable: bool = False,
    ) -> None:
        super().__init__(code, detail)
        self.retryable: bool = retryable
