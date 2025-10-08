"""
Модели для системы платежей и пополнения баланса.
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class PaymentStatus(str, Enum):
    """Статус транзакции пополнения"""
    PENDING = "pending"      # Ожидает оплаты
    SUCCESS = "success"      # Успешно оплачено
    FAILED = "failed"        # Ошибка оплаты
    CANCELLED = "cancelled"  # Отменено пользователем
    REFUNDED = "refunded"    # Возвращено


class PaymentProviderType(str, Enum):
    """Типы платежных провайдеров"""
    YOOMONEY = "yoomoney"
    YUKASSA = "yukassa"


class Transaction(BaseModel):
    """
    Транзакция пополнения баланса компании.
    Хранится в Storage с ключом: transaction:{transaction_id}
    """
    
    class Config:
        storage_prefix = "transaction"
    
    transaction_id: str = Field(
        title="ID транзакции",
        description="Уникальный ID транзакции в нашей системе",
        readonly=True
    )
    company_id: str = Field(
        title="ID компании",
        description="Компания, которая пополняет баланс"
    )
    user_id: str = Field(
        title="ID пользователя",
        description="Пользователь, который инициировал пополнение"
    )
    amount: float = Field(
        title="Сумма",
        description="Сумма пополнения в рублях",
        ge=0.01
    )
    status: PaymentStatus = Field(
        default=PaymentStatus.PENDING,
        title="Статус",
        description="Текущий статус транзакции"
    )
    payment_provider: PaymentProviderType = Field(
        title="Платежный провайдер",
        description="Через какой провайдер производится оплата"
    )
    external_payment_id: Optional[str] = Field(
        default=None,
        title="ID платежа у провайдера",
        description="ID операции в системе платежного провайдера"
    )
    payment_url: Optional[str] = Field(
        default=None,
        title="URL для оплаты",
        description="Ссылка для перехода на страницу оплаты"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Создано",
        description="Время создания транзакции",
        readonly=True
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        title="Завершено",
        description="Время завершения транзакции",
        readonly=True
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        title="Метаданные",
        description="Дополнительные данные о транзакции"
    )


class PaymentNotification(BaseModel):
    """
    Уведомление от платежного провайдера (webhook).
    Сохраняется для истории и защиты от дублирования.
    """
    
    class Config:
        storage_prefix = "payment_notification"
    
    notification_id: str = Field(
        title="ID уведомления",
        description="Уникальный ID уведомления"
    )
    provider: PaymentProviderType = Field(
        title="Провайдер",
        description="От какого провайдера пришло уведомление"
    )
    transaction_id: Optional[str] = Field(
        default=None,
        title="ID транзакции",
        description="ID транзакции в нашей системе"
    )
    external_payment_id: Optional[str] = Field(
        default=None,
        title="ID платежа у провайдера"
    )
    raw_data: Dict[str, Any] = Field(
        default_factory=dict,
        title="Сырые данные",
        description="Полные данные webhook для отладки"
    )
    processed: bool = Field(
        default=False,
        title="Обработано",
        description="Было ли обработано это уведомление"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Получено",
        readonly=True
    )


class CreatePaymentRequest(BaseModel):
    """Запрос на создание платежа"""
    amount: float = Field(
        ge=100.0,
        le=1000000.0,
        description="Сумма пополнения (мин. 100₽, макс. 1,000,000₽)"
    )
    provider: Optional[str] = Field(
        default=None,
        description="Платежный провайдер (если None - используется дефолтный)"
    )


class CreatePaymentResponse(BaseModel):
    """Ответ при создании платежа"""
    transaction_id: str = Field(description="ID транзакции")
    payment_url: str = Field(description="URL для оплаты")
    provider: str = Field(description="Использованный провайдер")
    status: str = Field(description="Статус транзакции")
    amount: float = Field(description="Сумма пополнения")


class TransactionResponse(BaseModel):
    """Информация о транзакции"""
    transaction_id: str
    company_id: str
    amount: float
    status: PaymentStatus
    payment_provider: PaymentProviderType
    external_payment_id: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]
