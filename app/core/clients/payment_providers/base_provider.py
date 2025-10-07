"""
Базовый абстрактный класс для всех платежных провайдеров.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class PaymentProviderConfig(BaseModel):
    """Базовая конфигурация провайдера"""
    provider_type: str = Field(description="Тип провайдера")
    enabled: bool = Field(default=True, description="Включен ли провайдер")


class PaymentRequest(BaseModel):
    """Запрос на создание платежа"""
    amount: float = Field(ge=0.01, description="Сумма платежа")
    company_id: str = Field(description="ID компании")
    user_id: str = Field(description="ID пользователя")
    transaction_id: str = Field(description="ID транзакции в нашей системе")
    success_url: str = Field(description="URL успешного платежа")
    fail_url: str = Field(description="URL неудачного платежа")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Дополнительные данные")


class PaymentResponse(BaseModel):
    """Ответ при создании платежа"""
    payment_url: str = Field(description="URL для оплаты")
    external_payment_id: Optional[str] = Field(default=None, description="ID платежа у провайдера")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Дополнительные данные")


class WebhookVerificationResult(BaseModel):
    """Результат проверки webhook"""
    is_valid: bool = Field(description="Валидна ли подпись")
    transaction_id: Optional[str] = Field(default=None, description="ID транзакции")
    amount: Optional[float] = Field(default=None, description="Сумма платежа")
    external_payment_id: Optional[str] = Field(default=None, description="ID платежа у провайдера")
    status: Optional[str] = Field(default=None, description="Статус платежа")
    error_message: Optional[str] = Field(default=None, description="Сообщение об ошибке")


class BasePaymentProvider(ABC):
    """
    Базовый класс для всех платежных провайдеров.
    Аналогично LLM провайдерам - единый интерфейс для разных систем.
    """
    
    def __init__(self, config: PaymentProviderConfig):
        self.config = config
        self.provider_name = config.provider_type
    
    @abstractmethod
    async def create_payment(self, request: PaymentRequest) -> PaymentResponse:
        """Создает платеж и возвращает URL для оплаты"""
        pass
    
    @abstractmethod
    async def verify_webhook(self, webhook_data: Dict[str, Any]) -> WebhookVerificationResult:
        """Проверяет подпись webhook и извлекает данные"""
        pass
    
    @abstractmethod
    async def check_payment_status(self, external_payment_id: str) -> str:
        """Проверяет статус платежа напрямую через API провайдера"""
        pass
    
    async def refund_payment(self, external_payment_id: str, amount: float) -> bool:
        """Возврат платежа (опционально, не все провайдеры поддерживают)"""
        return False
    
    def is_enabled(self) -> bool:
        """Проверка что провайдер включен"""
        return self.config.enabled
