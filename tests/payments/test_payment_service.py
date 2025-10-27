"""
Тесты сервиса платежей.
"""

import pytest
from unittest.mock import AsyncMock, Mock
from datetime import datetime, timezone

from app.models.payment_models import Transaction, PaymentStatus, PaymentProviderType, PaymentNotification
from app.identity.models import Company, User
from app.core.clients.payment_providers.base_provider import (
    BasePaymentProvider,
    PaymentResponse,
    WebhookVerificationResult
)




@pytest.mark.asyncio
async def test_create_payment(payment_service_with_mock, test_company, test_user, mock_provider):
    """Тест создания платежа"""
    
    result = await payment_service_with_mock.create_payment(
        company=test_company,
        user=test_user,
        amount=1000.0,
        provider=mock_provider
    )
    
    assert "transaction_id" in result
    assert "payment_url" in result
    assert result["amount"] == 1000.0
    assert "txn_" in result["transaction_id"]
    
    payment_service_with_mock.storage.set.assert_called_once()
    
    mock_provider.create_payment.assert_called_once()
    call_args = mock_provider.create_payment.call_args[0][0]
    assert call_args.amount == 1000.0
    assert call_args.company_id == "test_company"
    assert call_args.user_id == "test_user"


@pytest.mark.asyncio
async def test_process_webhook_success(payment_service_with_mock):
    """Тест обработки успешного webhook"""
    
    # Создаем тестовую транзакцию
    test_transaction = Transaction(
        transaction_id="txn_test123",
        company_id="test_company",
        user_id="test_user",
        amount=1000.0,
        status=PaymentStatus.PENDING,
        payment_provider=PaymentProviderType.YOOMONEY
    )
    
    payment_service_with_mock.storage.list_by_prefix = AsyncMock(side_effect=lambda prefix, **kwargs: {
        "payment:": ["payment:test_company:yoomoney:txn_test123"],
        "payment_notification:": []
    }.get(prefix, []))
    
    payment_service_with_mock.storage.get = AsyncMock(side_effect=lambda key, **kwargs: {
        "payment:test_company:yoomoney:txn_test123": test_transaction.model_dump_json(),
        "company:test_company": Company(
            company_id="test_company",
            subdomain="test", 
            name="Test Company",
            balance=5000.0
        ).model_dump_json()
    }.get(key))
    
    payment_service_with_mock.storage.set = AsyncMock()
    
    verification_result = WebhookVerificationResult(
        is_valid=True,
        transaction_id="txn_test123",
        amount=1000.0,
        external_payment_id="yoomoney_op_123",
        status="success"
    )
    
    await payment_service_with_mock.process_webhook(
        verification_result=verification_result,
        provider_name="yoomoney_main",
        raw_data={"test": "webhook_data"}
    )
    
    assert payment_service_with_mock.storage.set.call_count >= 3


@pytest.mark.asyncio
async def test_process_webhook_duplicate(payment_service_with_mock):
    """Тест обработки дубликата webhook"""
    
    # Мокируем что уже есть обработанное уведомление
    existing_notification = PaymentNotification(
        notification_id="existing",
        provider=PaymentProviderType.YOOMONEY,
        external_payment_id="yoomoney_op_123",
        processed=True
    )
    
    payment_service_with_mock.storage.list_by_prefix = AsyncMock(return_value=["payment_notification:existing"])
    payment_service_with_mock.storage.get = AsyncMock(return_value=existing_notification.model_dump_json())
    payment_service_with_mock.storage.set = AsyncMock()
    
    verification_result = WebhookVerificationResult(
        is_valid=True,
        transaction_id="txn_test123",
        amount=1000.0,
        external_payment_id="yoomoney_op_123",
        status="success"
    )
    
    await payment_service_with_mock.process_webhook(
        verification_result=verification_result,
        provider_name="yoomoney_main", 
        raw_data={}
    )


@pytest.mark.asyncio
async def test_get_transaction(payment_service_with_mock):
    """Тест получения транзакции"""
    
    test_transaction = Transaction(
        transaction_id="txn_test123",
        company_id="test_company",
        user_id="test_user",
        amount=1000.0,
        status=PaymentStatus.SUCCESS,
        payment_provider=PaymentProviderType.YOOMONEY
    )
    
    payment_service_with_mock.storage.list_by_prefix = AsyncMock(return_value=[
        "payment:test_company:yoomoney:txn_test123"
    ])
    payment_service_with_mock.storage.get = AsyncMock(return_value=test_transaction.model_dump_json())
    
    result = await payment_service_with_mock.get_transaction("txn_test123")
    
    assert result is not None
    assert result.transaction_id == "txn_test123"
    assert result.company_id == "test_company" 
    assert result.amount == 1000.0
    assert result.status == PaymentStatus.SUCCESS


@pytest.mark.asyncio
async def test_get_transaction_not_found(payment_service_with_mock):
    """Тест получения несуществующей транзакции"""
    
    payment_service_with_mock.storage.get = AsyncMock(return_value=None)
    
    result = await payment_service_with_mock.get_transaction("nonexistent")
    
    assert result is None


@pytest.mark.asyncio
async def test_get_company_transactions(payment_service_with_mock):
    """Тест получения транзакций компании"""
    
    # Создаем тестовые транзакции
    transactions = [
        Transaction(
            transaction_id=f"txn_{i}",
            company_id="test_company" if i < 3 else "other_company",
            user_id="test_user",
            amount=1000.0 * i,
            status=PaymentStatus.SUCCESS,
            payment_provider=PaymentProviderType.YOOMONEY,
            created_at=datetime.now(timezone.utc)
        )
        for i in range(1, 6)
    ]
    
    payment_service_with_mock.storage.list_by_prefix = AsyncMock(
        return_value=[
            "payment:test_company:yoomoney:txn_1",
            "payment:test_company:yoomoney:txn_2"
        ]
    )
    
    def mock_get(key, **kwargs):
        for t in transactions:
            if t.transaction_id in key and t.company_id == "test_company":
                return t.model_dump_json()
        return None
    
    payment_service_with_mock.storage.get = AsyncMock(side_effect=mock_get)
    
    result = await payment_service_with_mock.get_company_transactions(
        company_id="test_company",
        limit=10,
        offset=0
    )
    
    assert len(result) == 2, "Должно быть 2 транзакции для test_company (индексы 1 и 2, 3-й для other_company)"
    for t in result:
        assert t.company_id == "test_company"
    
    for i in range(len(result) - 1):
        assert result[i].created_at >= result[i + 1].created_at


@pytest.mark.asyncio
async def test_update_company_balance(payment_service_with_mock, test_company):
    """Тест пополнения баланса компании"""
    initial_balance = test_company.balance
    
    payment_service_with_mock.storage.get = AsyncMock(return_value=test_company.model_dump_json())
    payment_service_with_mock.storage.set = AsyncMock()
    
    await payment_service_with_mock._update_company_balance("test_company", 1000.0)
    
    payment_service_with_mock.storage.set.assert_called_once()
    call_args = payment_service_with_mock.storage.set.call_args
    
    import json
    saved_company_data = json.loads(call_args[0][1])
    assert saved_company_data["balance"] == initial_balance + 1000.0


@pytest.mark.asyncio
async def test_is_notification_duplicate(payment_service_with_mock):
    """Тест проверки дубликатов уведомлений"""
    
    # Мокируем что есть обработанное уведомление
    existing_notification = PaymentNotification(
        notification_id="existing",
        provider=PaymentProviderType.YOOMONEY,
        external_payment_id="duplicate_id",
        processed=True
    )
    
    payment_service_with_mock.storage.list_by_prefix = AsyncMock(return_value=["payment_notification:existing"])
    payment_service_with_mock.storage.get = AsyncMock(return_value=existing_notification.model_dump_json())
    
    is_duplicate = await payment_service_with_mock._is_notification_duplicate("duplicate_id")
    assert is_duplicate is True, "Должен определить дубликат"
    
    is_duplicate = await payment_service_with_mock._is_notification_duplicate("new_id")
    assert is_duplicate is False, "Новый ID не должен быть дубликатом"
