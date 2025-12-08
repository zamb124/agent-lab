"""
Тесты сервиса платежей.
"""

import pytest
from datetime import datetime, timezone

from core.models.payment_models import Transaction, PaymentStatus, PaymentProviderType, PaymentNotification
from core.models import Company
from core.clients.payment.base_provider import (
    WebhookVerificationResult
)
from core.payments import PaymentService




@pytest.mark.asyncio
async def test_create_payment(company_repo, test_company, test_user, mock_provider):
    """Тест создания платежа"""
    
    payment_service = PaymentService(company_repository=company_repo)
    
    result = await payment_service.create_payment(
        company=test_company,
        user=test_user,
        amount=1000.0,
        provider=mock_provider
    )
    
    assert "transaction_id" in result
    assert "payment_url" in result
    assert result["amount"] == 1000.0
    assert "txn_" in result["transaction_id"]
    
    mock_provider.create_payment.assert_called_once()
    call_args = mock_provider.create_payment.call_args[0][0]
    assert call_args.amount == 1000.0
    assert call_args.company_id == test_company.company_id
    assert call_args.user_id == test_user.user_id
    
    saved_transaction = await payment_service.get_transaction(result["transaction_id"])
    assert saved_transaction is not None
    assert saved_transaction.amount == 1000.0
    assert saved_transaction.status == PaymentStatus.PENDING


@pytest.mark.asyncio
async def test_process_webhook_success(company_repo, save_test_company, test_company, storage):
    """Тест обработки успешного webhook"""
    import uuid
    
    unique_id = uuid.uuid4().hex[:8]
    transaction_id = f"{test_company.company_id}:txn_{unique_id}"
    external_payment_id = f"yoomoney_op_{unique_id}"
    
    payment_service = PaymentService(company_repository=company_repo)
    
    test_transaction = Transaction(
        transaction_id=transaction_id,
        company_id=test_company.company_id,
        user_id="test_user",
        amount=1000.0,
        status=PaymentStatus.PENDING,
        payment_provider=PaymentProviderType.YOOMONEY
    )
    
    await payment_service._save_transaction(test_transaction)
    
    company_before = await company_repo.get(test_company.company_id)
    initial_balance = company_before.balance
    
    verification_result = WebhookVerificationResult(
        is_valid=True,
        transaction_id=transaction_id,
        amount=1000.0,
        external_payment_id=external_payment_id,
        status="success"
    )
    
    await payment_service.process_webhook(
        verification_result=verification_result,
        provider_name="yoomoney_main",
        raw_data={"test": "webhook_data"}
    )
    
    updated_company = await company_repo.get(test_company.company_id)
    assert updated_company.balance == initial_balance + 1000.0
    
    updated_transaction = await payment_service.get_transaction(transaction_id)
    assert updated_transaction.status == PaymentStatus.SUCCESS
    assert updated_transaction.external_payment_id == external_payment_id


@pytest.mark.asyncio
async def test_process_webhook_duplicate(company_repo, unique_id):
    """Тест обработки дубликата webhook"""
    from core.models.billing_models import TariffPlan
    
    company_id = unique_id("dup_webhook_company")
    test_company = Company(
        company_id=company_id,
        subdomain=company_id,
        name="Test Duplicate Webhook Company",
        tariff_plan=TariffPlan.ENTERPRISE,
        balance=100000.0,
        status="active"
    )
    await company_repo.set(test_company)
    
    payment_service = PaymentService(company_repository=company_repo)
    
    ext_payment_id = unique_id("yoomoney_op")
    existing_notification = PaymentNotification(
        notification_id=unique_id("notif"),
        provider=PaymentProviderType.YOOMONEY,
        external_payment_id=ext_payment_id,
        processed=True
    )
    
    await payment_service._save_notification(existing_notification)
    
    verification_result = WebhookVerificationResult(
        is_valid=True,
        transaction_id=f"{company_id}:txn_{unique_id('txn')}",
        amount=1000.0,
        external_payment_id=ext_payment_id,
        status="success"
    )
    
    company_before = await company_repo.get(company_id)
    initial_balance = company_before.balance
    
    await payment_service.process_webhook(
        verification_result=verification_result,
        provider_name="yoomoney_main", 
        raw_data={}
    )
    
    company_after = await company_repo.get(company_id)
    assert company_after.balance == initial_balance, f"Баланс изменился с {initial_balance} на {company_after.balance}"


@pytest.mark.asyncio
async def test_get_transaction(company_repo, test_company):
    """Тест получения транзакции"""
    
    payment_service = PaymentService(company_repository=company_repo)
    
    transaction_id = f"{test_company.company_id}:txn_test123"
    test_transaction = Transaction(
        transaction_id=transaction_id,
        company_id=test_company.company_id,
        user_id="test_user",
        amount=1000.0,
        status=PaymentStatus.SUCCESS,
        payment_provider=PaymentProviderType.YOOMONEY
    )
    
    await payment_service._save_transaction(test_transaction)
    
    result = await payment_service.get_transaction(transaction_id)
    
    assert result is not None
    assert result.transaction_id == transaction_id
    assert result.company_id == test_company.company_id
    assert result.amount == 1000.0
    assert result.status == PaymentStatus.SUCCESS


@pytest.mark.asyncio
async def test_get_transaction_not_found(company_repo):
    """Тест получения несуществующей транзакции"""
    
    payment_service = PaymentService(company_repository=company_repo)
    
    result = await payment_service.get_transaction("nonexistent:txn_123")
    
    assert result is None


@pytest.mark.asyncio
async def test_get_company_transactions(company_repo, test_company):
    """Тест получения транзакций компании"""
    import uuid
    
    unique_company_id = f"test_company_{uuid.uuid4().hex[:8]}"
    unique_company = Company(
        company_id=unique_company_id,
        subdomain="test",
        name="Test Company",
        balance=100000.0,
        status="active"
    )
    await company_repo.set(unique_company)
    
    payment_service = PaymentService(company_repository=company_repo)
    
    transactions = []
    for i in range(1, 4):
        transaction_id = f"{unique_company_id}:txn_{i}"
        transaction = Transaction(
            transaction_id=transaction_id,
            company_id=unique_company_id,
            user_id="test_user",
            amount=1000.0 * i,
            status=PaymentStatus.SUCCESS,
            payment_provider=PaymentProviderType.YOOMONEY,
            created_at=datetime.now(timezone.utc)
        )
        await payment_service._save_transaction(transaction)
        transactions.append(transaction)
    
    result = await payment_service.get_company_transactions(
        company_id=unique_company_id,
        limit=10,
        offset=0
    )
    
    assert len(result) == 3
    for t in result:
        assert t.company_id == unique_company_id
    
    for i in range(len(result) - 1):
        assert result[i].created_at >= result[i + 1].created_at


@pytest.mark.asyncio
async def test_update_company_balance(company_repo, save_test_company, test_company):
    """Тест пополнения баланса компании"""
    payment_service = PaymentService(company_repository=company_repo)
    
    initial_balance = test_company.balance
    
    await payment_service._update_company_balance(test_company.company_id, 1000.0)
    
    updated_company = await company_repo.get(test_company.company_id)
    assert updated_company.balance == initial_balance + 1000.0


@pytest.mark.asyncio
async def test_is_notification_duplicate(company_repo):
    """Тест проверки дубликатов уведомлений"""
    
    payment_service = PaymentService(company_repository=company_repo)
    
    existing_notification = PaymentNotification(
        notification_id="existing",
        provider=PaymentProviderType.YOOMONEY,
        external_payment_id="duplicate_id",
        processed=True
    )
    
    await payment_service._save_notification(existing_notification)
    
    is_duplicate = await payment_service._is_notification_duplicate("duplicate_id")
    assert is_duplicate is True
    
    is_duplicate = await payment_service._is_notification_duplicate("new_id")
    assert is_duplicate is False
