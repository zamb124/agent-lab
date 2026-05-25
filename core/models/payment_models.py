"""
Модели для системы платежей и пополнения баланса.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from core.types import JsonObject


class PaymentStatus(str, Enum):
    """Статус транзакции пополнения"""

    PENDING = "pending"  # Ожидает оплаты
    SUCCESS = "success"  # Успешно оплачено
    FAILED = "failed"  # Ошибка оплаты
    CANCELLED = "cancelled"  # Отменено пользователем
    REFUNDED = "refunded"  # Возвращено


class PaymentProviderType(str, Enum):
    """Типы источника пополнения: платёжные провайдеры или начисление гранта из админки platform."""

    YOOMONEY = "yoomoney"
    YUKASSA = "yukassa"
    GRANT = "grant"


class Transaction(BaseModel):
    """
    Транзакция пополнения баланса компании.
    Хранится в Storage с ключом: transaction:{transaction_id}
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        json_schema_extra={"storage_prefix": "transaction"}
    )

    transaction_id: str = Field(
        title="ID транзакции",
        description="Уникальный ID транзакции в нашей системе",
        json_schema_extra={"readonly": True},
    )
    company_id: str = Field(title="ID компании", description="Компания, которая пополняет баланс")
    user_id: str = Field(
        title="ID пользователя", description="Пользователь, который инициировал пополнение"
    )
    amount: float = Field(title="Сумма", description="Сумма пополнения в рублях", ge=0.01)
    status: PaymentStatus = Field(
        default=PaymentStatus.PENDING, title="Статус", description="Текущий статус транзакции"
    )
    payment_provider: PaymentProviderType = Field(
        title="Платежный провайдер", description="Через какой провайдер производится оплата"
    )
    external_payment_id: str | None = Field(
        default=None,
        title="ID платежа у провайдера",
        description="ID операции в системе платежного провайдера",
    )
    payment_url: str | None = Field(
        default=None, title="URL для оплаты", description="Ссылка для перехода на страницу оплаты"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Создано",
        description="Время создания транзакции",
        json_schema_extra={"readonly": True},
    )
    completed_at: datetime | None = Field(
        default=None,
        title="Завершено",
        description="Время завершения транзакции",
        json_schema_extra={"readonly": True},
    )
    metadata: JsonObject = Field(
        default_factory=dict, title="Метаданные", description="Дополнительные данные о транзакции"
    )
    balance_applied: bool = Field(
        default=False,
        title="Баланс начислен",
        description=(
            "Идемпотентный маркер: True если средства транзакции уже были "
            "зачислены на баланс компании. Защита от двойного начисления "
            "при повторных webhook/sync. Меняется только методом "
            "PaymentService.finalize_successful_payment."
        ),
        json_schema_extra={"readonly": True},
    )


class ExternalPaymentClaim(BaseModel):
    """Идемпотентная привязка внешней операции провайдера к транзакции платформы."""

    transaction_id: str


class PaymentSyncCandidate(BaseModel):
    """Pending-транзакция, которую можно сверить с платёжным провайдером."""

    transaction_id: str
    amount: float
    created_at: datetime


class PaymentSyncOperation(BaseModel):
    """Найденная у провайдера операция по pending-транзакции."""

    transaction_id: str
    status: PaymentStatus
    operation_id: str | None = None
    amount: float | None = None


class PaymentProviderSyncStats(BaseModel):
    """Статистика сверки по одному платёжному провайдеру."""

    checked: int = 0
    found: int = 0


class PaymentSyncStats(BaseModel):
    """Статистика сверки pending-транзакций одной компании."""

    total_pending: int = 0
    checked: int = 0
    found: int = 0
    updated: int = 0
    by_provider: dict[PaymentProviderType, PaymentProviderSyncStats] = Field(default_factory=dict)


class PaymentSyncAllCompaniesStats(BaseModel):
    """Статистика сверки pending-транзакций по всем компаниям."""

    companies_checked: int = 0
    total_pending: int = 0
    total_found: int = 0
    total_updated: int = 0


class PaymentNotification(BaseModel):
    """
    Уведомление от платежного провайдера (webhook).
    Сохраняется для истории и защиты от дублирования.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        json_schema_extra={"storage_prefix": "payment_notification"}
    )

    notification_id: str = Field(title="ID уведомления", description="Уникальный ID уведомления")
    provider: PaymentProviderType = Field(
        title="Провайдер", description="От какого провайдера пришло уведомление"
    )
    transaction_id: str | None = Field(
        default=None, title="ID транзакции", description="ID транзакции в нашей системе"
    )
    external_payment_id: str | None = Field(default=None, title="ID платежа у провайдера")
    raw_data: JsonObject = Field(
        default_factory=dict, title="Сырые данные", description="Полные данные webhook для отладки"
    )
    processed: bool = Field(
        default=False, title="Обработано", description="Было ли обработано это уведомление"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Получено",
        json_schema_extra={"readonly": True},
    )


class CreatePaymentRequest(BaseModel):
    """Запрос на создание платежа"""

    amount: float = Field(
        ge=100.0, le=1000000.0, description="Сумма пополнения (мин. 100₽, макс. 1,000,000₽)"
    )
    provider: str | None = Field(
        default=None, description="Платежный провайдер (если None - используется дефолтный)"
    )


class CreatePaymentResponse(BaseModel):
    """Ответ при создании платежа"""

    transaction_id: str = Field(description="ID транзакции")
    payment_url: str = Field(description="URL для оплаты")
    provider: str = Field(description="Использованный провайдер")
    status: str = Field(description="Статус транзакции")
    amount: float = Field(description="Сумма пополнения")


class BalanceGrantResult(BaseModel):
    """Результат начисления баланса без внешнего платёжного провайдера."""

    transaction_id: str
    company_id: str
    amount: float
    balance: float


class TransactionResponse(BaseModel):
    """Информация о транзакции"""

    transaction_id: str
    company_id: str
    amount: float
    status: PaymentStatus
    payment_provider: PaymentProviderType
    external_payment_id: str | None
    created_at: datetime
    completed_at: datetime | None
    metadata: JsonObject = Field(
        default_factory=dict,
        description="Аудит и комментарии (для гранта: granted_by_user_id, note)",
    )
