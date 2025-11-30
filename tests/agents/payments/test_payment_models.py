"""
Тесты моделей для платежей.
"""

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from core.models.payment_models import (
    Transaction,
    PaymentNotification,
    PaymentStatus,
    PaymentProviderType,
    CreatePaymentRequest,
    CreatePaymentResponse,
    TransactionResponse
)


def test_transaction_model():
    """Тест модели Transaction"""
    
    transaction = Transaction(
        transaction_id="txn_test123",
        company_id="test_company",
        user_id="test_user",
        amount=1500.50,
        status=PaymentStatus.PENDING,
        payment_provider=PaymentProviderType.YOOMONEY
    )
    
    assert transaction.transaction_id == "txn_test123"
    assert transaction.amount == 1500.50
    assert transaction.status == PaymentStatus.PENDING
    assert transaction.payment_provider == PaymentProviderType.YOOMONEY
    assert isinstance(transaction.created_at, datetime)
    assert transaction.completed_at is None
    assert transaction.metadata == {}


def test_transaction_model_with_completion():
    """Тест модели Transaction с завершением"""
    
    completion_time = datetime.now(timezone.utc)
    
    transaction = Transaction(
        transaction_id="txn_completed",
        company_id="test_company",
        user_id="test_user",
        amount=1000.0,
        status=PaymentStatus.SUCCESS,
        payment_provider=PaymentProviderType.YOOMONEY,
        external_payment_id="yoomoney_op_123",
        completed_at=completion_time,
        metadata={"provider_data": "test"}
    )
    
    assert transaction.status == PaymentStatus.SUCCESS
    assert transaction.external_payment_id == "yoomoney_op_123"
    assert transaction.completed_at == completion_time
    assert transaction.metadata["provider_data"] == "test"


def test_transaction_amount_validation():
    """Тест валидации суммы в Transaction"""
    
    # Валидная сумма
    transaction = Transaction(
        transaction_id="txn_valid",
        company_id="test_company",
        user_id="test_user",
        amount=100.0,
        status=PaymentStatus.PENDING,
        payment_provider=PaymentProviderType.YOOMONEY
    )
    assert transaction.amount == 100.0
    
    # Невалидная сумма (отрицательная) - pydantic должен ругаться
    with pytest.raises(ValidationError):
        Transaction(
            transaction_id="txn_invalid",
            company_id="test_company",
            user_id="test_user",
            amount=-100.0,  # Отрицательная сумма
            status=PaymentStatus.PENDING,
            payment_provider=PaymentProviderType.YOOMONEY
        )


def test_payment_notification_model():
    """Тест модели PaymentNotification"""
    
    notification = PaymentNotification(
        notification_id="notif_123",
        provider=PaymentProviderType.YOOMONEY,
        transaction_id="txn_test123",
        external_payment_id="yoomoney_op_123",
        raw_data={"operation_id": "123", "amount": "1000.00"},
        processed=True
    )
    
    assert notification.notification_id == "notif_123"
    assert notification.provider == PaymentProviderType.YOOMONEY
    assert notification.transaction_id == "txn_test123"
    assert notification.processed is True
    assert notification.raw_data["amount"] == "1000.00"
    assert isinstance(notification.created_at, datetime)


def test_create_payment_request_model():
    """Тест модели CreatePaymentRequest"""
    
    request = CreatePaymentRequest(
        amount=1000.0,
        provider="yoomoney_main"
    )
    
    assert request.amount == 1000.0
    assert request.provider == "yoomoney_main"
    
    # Тест без провайдера
    request_no_provider = CreatePaymentRequest(amount=500.0)
    assert request_no_provider.amount == 500.0
    assert request_no_provider.provider is None


def test_create_payment_request_validation():
    """Тест валидации CreatePaymentRequest"""
    
    # Сумма меньше минимума
    with pytest.raises(ValidationError):
        CreatePaymentRequest(amount=50.0)  # Минимум 100₽
    
    # Сумма больше максимума
    with pytest.raises(ValidationError):
        CreatePaymentRequest(amount=2000000.0)  # Максимум 1,000,000₽
    
    # Валидная сумма
    request = CreatePaymentRequest(amount=500.0)
    assert request.amount == 500.0


def test_create_payment_response_model():
    """Тест модели CreatePaymentResponse"""
    
    response = CreatePaymentResponse(
        transaction_id="txn_test123",
        payment_url="https://yoomoney.ru/pay",
        provider="yoomoney_main",
        status="pending",
        amount=1000.0
    )
    
    assert response.transaction_id == "txn_test123"
    assert response.payment_url == "https://yoomoney.ru/pay"
    assert response.provider == "yoomoney_main"
    assert response.status == "pending"
    assert response.amount == 1000.0


def test_transaction_response_model():
    """Тест модели TransactionResponse"""
    
    created_time = datetime.now(timezone.utc)
    completed_time = datetime.now(timezone.utc)
    
    response = TransactionResponse(
        transaction_id="txn_test123",
        company_id="test_company",
        amount=1000.0,
        status=PaymentStatus.SUCCESS,
        payment_provider=PaymentProviderType.YOOMONEY,
        external_payment_id="yoomoney_op_123",
        created_at=created_time,
        completed_at=completed_time
    )
    
    assert response.transaction_id == "txn_test123"
    assert response.company_id == "test_company"
    assert response.amount == 1000.0
    assert response.status == PaymentStatus.SUCCESS
    assert response.payment_provider == PaymentProviderType.YOOMONEY
    assert response.external_payment_id == "yoomoney_op_123"
    assert response.created_at == created_time
    assert response.completed_at == completed_time


def test_payment_status_enum():
    """Тест enum PaymentStatus"""
    
    assert PaymentStatus.PENDING == "pending"
    assert PaymentStatus.SUCCESS == "success" 
    assert PaymentStatus.FAILED == "failed"
    assert PaymentStatus.CANCELLED == "cancelled"
    assert PaymentStatus.REFUNDED == "refunded"


def test_payment_provider_type_enum():
    """Тест enum PaymentProviderType"""
    
    assert PaymentProviderType.YOOMONEY == "yoomoney"
    assert PaymentProviderType.YUKASSA == "yukassa"


def test_models_serialization():
    """Тест сериализации/десериализации моделей"""
    
    # Transaction
    transaction = Transaction(
        transaction_id="txn_serial_test",
        company_id="test_company",
        user_id="test_user", 
        amount=750.25,
        status=PaymentStatus.SUCCESS,
        payment_provider=PaymentProviderType.YOOMONEY,
        external_payment_id="op_123",
        metadata={"key": "value"}
    )
    
    # Сериализация
    json_data = transaction.model_dump_json()
    assert isinstance(json_data, str)
    
    # Десериализация
    restored = Transaction.model_validate_json(json_data)
    assert restored.transaction_id == transaction.transaction_id
    assert restored.amount == transaction.amount
    assert restored.metadata == transaction.metadata
    
    # PaymentNotification
    notification = PaymentNotification(
        notification_id="notif_serial",
        provider=PaymentProviderType.YOOMONEY,
        raw_data={"test": "data"}
    )
    
    json_data = notification.model_dump_json()
    restored_notif = PaymentNotification.model_validate_json(json_data)
    assert restored_notif.notification_id == notification.notification_id
    assert restored_notif.raw_data == notification.raw_data
