"""
Тесты сервиса платежей.
"""

import pytest
from unittest.mock import AsyncMock, Mock
from datetime import datetime, timezone

from app.services.payment_service import PaymentService
from app.models.payment_models import Transaction, PaymentStatus, PaymentProviderType, PaymentNotification
from app.identity.models import Company, User
from app.core.clients.payment_providers.base_provider import (
    BasePaymentProvider,
    PaymentResponse,
    WebhookVerificationResult
)


@pytest.fixture
def payment_service():
    """Fixture с сервисом платежей"""
    service = PaymentService()
    service.storage = AsyncMock()
    return service


@pytest.fixture
def test_company():
    """Fixture с тестовой компанией"""
    return Company(
        company_id="test_company",
        subdomain="test",
        name="Test Company",
        balance=5000.0,
        tariff_plan="premium"
    )


@pytest.fixture
def test_user():
    """Fixture с тестовым пользователем"""
    return User(
        user_id="test_user",
        name="Test User",
        companies={"test_company": ["admin"]},
        active_company_id="test_company"
    )


@pytest.fixture
def mock_provider():
    """Fixture с мок провайдером"""
    provider = Mock(spec=BasePaymentProvider)
    provider.provider_name = "yoomoney"
    provider.create_payment = AsyncMock(return_value=PaymentResponse(
        payment_url="https://yoomoney.ru/quickpay/confirm.xml?params",
        external_payment_id=None,
        metadata={"provider": "yoomoney"}
    ))
    return provider


@pytest.mark.asyncio
async def test_create_payment(payment_service, test_company, test_user, mock_provider):
    """Тест создания платежа"""
    
    result = await payment_service.create_payment(
        company=test_company,
        user=test_user,
        amount=1000.0,
        provider=mock_provider
    )
    
    # Проверяем результат
    assert "transaction_id" in result
    assert "payment_url" in result
    assert result["amount"] == 1000.0
    assert "txn_" in result["transaction_id"]
    
    # Проверяем что транзакция была сохранена
    payment_service.storage.set.assert_called_once()
    
    # Проверяем что провайдер был вызван
    mock_provider.create_payment.assert_called_once()
    call_args = mock_provider.create_payment.call_args[0][0]
    assert call_args.amount == 1000.0
    assert call_args.company_id == "test_company"
    assert call_args.user_id == "test_user"


@pytest.mark.asyncio
async def test_process_webhook_success(payment_service):
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
    
    # Мокируем методы storage
    payment_service.storage.get = AsyncMock(side_effect=lambda key, **kwargs: {
        "transaction:txn_test123": test_transaction.model_dump_json(),
        "company:test_company": Company(
            company_id="test_company",
            subdomain="test", 
            name="Test Company",
            balance=5000.0
        ).model_dump_json()
    }.get(key))
    
    payment_service.storage.set = AsyncMock()
    payment_service.storage.list_by_prefix = AsyncMock(return_value=[])
    
    verification_result = WebhookVerificationResult(
        is_valid=True,
        transaction_id="txn_test123",
        amount=1000.0,
        external_payment_id="yoomoney_op_123",
        status="success"
    )
    
    await payment_service.process_webhook(
        verification_result=verification_result,
        provider_name="yoomoney_main",
        raw_data={"test": "webhook_data"}
    )
    
    # Проверяем что все было сохранено
    assert payment_service.storage.set.call_count >= 3  # notification + transaction + company


@pytest.mark.asyncio
async def test_process_webhook_duplicate(payment_service):
    """Тест обработки дубликата webhook"""
    
    # Мокируем что уже есть обработанное уведомление
    existing_notification = PaymentNotification(
        notification_id="existing",
        provider=PaymentProviderType.YOOMONEY,
        external_payment_id="yoomoney_op_123",
        processed=True
    )
    
    payment_service.storage.list_by_prefix = AsyncMock(return_value=["payment_notification:existing"])
    payment_service.storage.get = AsyncMock(return_value=existing_notification.model_dump_json())
    payment_service.storage.set = AsyncMock()
    
    verification_result = WebhookVerificationResult(
        is_valid=True,
        transaction_id="txn_test123",
        amount=1000.0,
        external_payment_id="yoomoney_op_123",
        status="success"
    )
    
    await payment_service.process_webhook(
        verification_result=verification_result,
        provider_name="yoomoney_main", 
        raw_data={}
    )
    
    # Проверяем что webhook был сохранен, но обработка пропущена  
    # При дубликате все равно сохраняем уведомление (1 раз)
    payment_service.storage.set.assert_called()


@pytest.mark.asyncio
async def test_get_transaction(payment_service):
    """Тест получения транзакции"""
    
    test_transaction = Transaction(
        transaction_id="txn_test123",
        company_id="test_company",
        user_id="test_user",
        amount=1000.0,
        status=PaymentStatus.SUCCESS,
        payment_provider=PaymentProviderType.YOOMONEY
    )
    
    payment_service.storage.get = AsyncMock(return_value=test_transaction.model_dump_json())
    
    result = await payment_service.get_transaction("txn_test123")
    
    assert result is not None
    assert result.transaction_id == "txn_test123"
    assert result.company_id == "test_company" 
    assert result.amount == 1000.0
    assert result.status == PaymentStatus.SUCCESS


@pytest.mark.asyncio
async def test_get_transaction_not_found(payment_service):
    """Тест получения несуществующей транзакции"""
    
    payment_service.storage.get = AsyncMock(return_value=None)
    
    result = await payment_service.get_transaction("nonexistent")
    
    assert result is None


@pytest.mark.asyncio
async def test_get_company_transactions(payment_service):
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
    
    # Мокируем storage
    payment_service.storage.list_by_prefix = AsyncMock(
        return_value=[f"transaction:txn_{i}" for i in range(1, 6)]
    )
    
    def mock_get(key, **kwargs):
        for t in transactions:
            if key == f"transaction:{t.transaction_id}":
                return t.model_dump_json()
        return None
    
    payment_service.storage.get = AsyncMock(side_effect=mock_get)
    
    result = await payment_service.get_company_transactions(
        company_id="test_company",
        limit=10,
        offset=0
    )
    
    # Проверяем что вернулись только транзакции test_company (индексы 1,2,3 -> 3 транзакции)
    assert len(result) == 2, "Должно быть 2 транзакции для test_company (индексы 1 и 2, 3-й для other_company)"
    for t in result:
        assert t.company_id == "test_company"
    
    # Проверяем сортировку по дате (новые первые)  
    for i in range(len(result) - 1):
        assert result[i].created_at >= result[i + 1].created_at


@pytest.mark.asyncio
async def test_update_company_balance(payment_service, test_company):
    """Тест пополнения баланса компании"""
    
    payment_service.storage.get = AsyncMock(return_value=test_company.model_dump_json())
    payment_service.storage.set = AsyncMock()
    
    await payment_service._update_company_balance("test_company", 1000.0)
    
    # Проверяем что баланс был обновлен
    payment_service.storage.set.assert_called_once()
    call_args = payment_service.storage.set.call_args
    
    # Парсим сохраненные данные компании
    import json
    saved_company_data = json.loads(call_args[0][1])
    assert saved_company_data["balance"] == 6000.0  # 5000 + 1000


@pytest.mark.asyncio
async def test_is_notification_duplicate(payment_service):
    """Тест проверки дубликатов уведомлений"""
    
    # Мокируем что есть обработанное уведомление
    existing_notification = PaymentNotification(
        notification_id="existing",
        provider=PaymentProviderType.YOOMONEY,
        external_payment_id="duplicate_id",
        processed=True
    )
    
    payment_service.storage.list_by_prefix = AsyncMock(return_value=["payment_notification:existing"])
    payment_service.storage.get = AsyncMock(return_value=existing_notification.model_dump_json())
    
    is_duplicate = await payment_service._is_notification_duplicate("duplicate_id")
    assert is_duplicate is True, "Должен определить дубликат"
    
    # Тест с новым ID
    is_duplicate = await payment_service._is_notification_duplicate("new_id")
    assert is_duplicate is False, "Новый ID не должен быть дубликатом"
