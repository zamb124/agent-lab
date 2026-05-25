"""
Базовый абстрактный класс для всех платежных провайдеров.
"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

from core.db.storage import Storage
from core.models.payment_models import (
    PaymentSyncCandidate,
    PaymentSyncOperation,
    YooMoneyWebhookPayload,
)
from core.types import JsonObject

ProviderTypeT = TypeVar("ProviderTypeT", bound=str, covariant=True)
ProviderConfigT = TypeVar(
    "ProviderConfigT",
    bound="PaymentProviderConfig[str]",
    covariant=True,
)


class PaymentProviderConfig(BaseModel, Generic[ProviderTypeT]):
    """Базовая конфигурация провайдера"""

    provider_type: ProviderTypeT = Field(description="Тип провайдера")
    enabled: bool = Field(default=True, description="Включен ли провайдер")


class PaymentRequest(BaseModel):
    """Запрос на создание платежа"""
    amount: float = Field(ge=0.01, description="Сумма платежа")
    company_id: str = Field(description="ID компании")
    user_id: str = Field(description="ID пользователя")
    transaction_id: str = Field(description="ID транзакции в нашей системе")
    success_url: str = Field(description="URL успешного платежа")
    fail_url: str = Field(description="URL неудачного платежа")
    metadata: JsonObject = Field(default_factory=dict, description="Дополнительные данные")


class PaymentResponse(BaseModel):
    """Ответ при создании платежа"""

    payment_url: str = Field(description="URL для оплаты")
    external_payment_id: str | None = Field(default=None, description="ID платежа у провайдера")
    metadata: JsonObject = Field(default_factory=dict, description="Дополнительные данные")


class WebhookVerificationResult(BaseModel):
    """Результат проверки webhook"""

    is_valid: bool = Field(description="Валидна ли подпись")
    transaction_id: str | None = Field(default=None, description="ID транзакции")
    amount: float | None = Field(default=None, description="Сумма платежа")
    external_payment_id: str | None = Field(default=None, description="ID платежа у провайдера")
    status: str | None = Field(default=None, description="Статус платежа")
    error_message: str | None = Field(default=None, description="Сообщение об ошибке")


class BasePaymentProvider(ABC, Generic[ProviderConfigT]):
    """
    Базовый класс для всех платежных провайдеров.
    Единый интерфейс для разных платежных систем.
    """

    def __init__(self, config: ProviderConfigT):
        self.config: ProviderConfigT = config
        self.provider_name: str = config.provider_type

    @abstractmethod
    async def create_payment(self, request: PaymentRequest) -> PaymentResponse:
        """Создает платеж и возвращает URL для оплаты"""
        pass

    @abstractmethod
    async def verify_webhook(self, webhook_data: YooMoneyWebhookPayload) -> WebhookVerificationResult:
        """Проверяет подпись webhook и извлекает данные"""
        pass

    @abstractmethod
    async def check_payment_status(self, external_payment_id: str) -> str:
        """Проверяет статус платежа напрямую через API провайдера"""
        pass

    async def refund_payment(self, external_payment_id: str, amount: float) -> bool:
        """Возврат платежа (опционально)"""
        _ = external_payment_id, amount
        return False

    async def sync_pending_transactions(
        self,
        pending_transactions: list[PaymentSyncCandidate],
        storage: Storage | None = None,
    ) -> list[PaymentSyncOperation]:
        """Сверяет pending-транзакции у провайдера, если провайдер поддерживает такую операцию."""
        _ = pending_transactions, storage
        return []

    def is_enabled(self) -> bool:
        """Проверка что провайдер включен"""
        return self.config.enabled
