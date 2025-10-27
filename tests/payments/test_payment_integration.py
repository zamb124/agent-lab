"""
Интеграционные тесты платежной системы.
Проверяют полный flow от создания платежа до записи в БД.
"""

import pytest
import hashlib

from app.models.payment_models import PaymentStatus, PaymentProviderType
from app.identity.models import Company


@pytest.mark.asyncio
async def test_full_payment_flow_with_db(
    storage,
    save_test_company,
    test_company,
    test_user,
    yoomoney_provider,
    payment_service,
    unique_id
):
    """
    Интеграционный тест полного flow платежа:
    1. Создание транзакции в БД
    2. Имитация webhook от YooMoney  
    3. Обновление транзакции в БД
    4. Пополнение баланса компании в БД
    """
    test_company.balance = 5000.0
    test_company.tariff_plan = "premium"
    
    result = await payment_service.create_payment(
        company=test_company,
        user=test_user, 
        amount=1500.0,
        provider=yoomoney_provider
    )
    
    transaction_id = result["transaction_id"]
    payment_url = result["payment_url"]
    
    assert ":txn_" in transaction_id
    assert "yoomoney.ru" in payment_url
    assert result["amount"] == 1500.0
    
    saved_transaction = await payment_service.get_transaction(transaction_id)
    
    assert saved_transaction is not None, "Транзакция должна быть сохранена в БД"
    assert saved_transaction.transaction_id == transaction_id
    assert saved_transaction.company_id == test_company.company_id
    assert saved_transaction.user_id == test_user.user_id
    assert saved_transaction.amount == 1500.0
    assert saved_transaction.status == PaymentStatus.PENDING
    assert saved_transaction.payment_provider == PaymentProviderType.YOOMONEY
    
    unique_op_id = unique_id("integration_op")
    webhook_data = {
        "notification_type": "p2p-incoming",
        "operation_id": unique_op_id,
        "amount": "1500.00",
        "currency": "643",
        "datetime": "2023-12-01T12:00:00Z",
        "sender": "410001111111111",
        "codepro": "false",
        "label": transaction_id
    }
    
    # Генерируем правильную подпись
    secret = yoomoney_provider.config.notification_secret
    check_string = (
        f"{webhook_data['notification_type']}&{webhook_data['operation_id']}&"
        f"{webhook_data['amount']}&{webhook_data['currency']}&"
        f"{webhook_data['datetime']}&{webhook_data['sender']}&"
        f"{webhook_data['codepro']}&{secret}&{webhook_data['label']}"
    )
    webhook_data["sha1_hash"] = hashlib.sha1(check_string.encode('utf-8')).hexdigest()
    
    verification_result = await yoomoney_provider.verify_webhook(webhook_data)
    assert verification_result.is_valid, "Webhook должен быть валидным"
    
    initial_company_data = await storage.get(f"company:{test_company.company_id}", force_global=True)
    initial_company = Company.model_validate_json(initial_company_data)
    initial_balance = initial_company.balance
    
    await payment_service.process_webhook(
        verification_result=verification_result,
        provider_name="yoomoney_main",
        raw_data=webhook_data
    )
    
    updated_transaction = await payment_service.get_transaction(transaction_id)
    assert updated_transaction is not None
    assert updated_transaction.status == PaymentStatus.SUCCESS, "Статус должен быть SUCCESS"
    assert updated_transaction.external_payment_id == unique_op_id, "External ID должен быть записан"
    assert updated_transaction.completed_at is not None, "Время завершения должно быть заполнено"
    
    updated_company_data = await storage.get(f"company:{test_company.company_id}", force_global=True)
    updated_company = Company.model_validate_json(updated_company_data)
    
    expected_balance = initial_balance + 1500.0
    assert updated_company.balance == expected_balance, f"Баланс должен быть {expected_balance}, но получили {updated_company.balance}"
    
    notification_keys = await storage.list_by_prefix("payment_notification:", force_global=True)
    assert len(notification_keys) >= 1, "Уведомление должно быть сохранено"


@pytest.mark.asyncio
async def test_duplicate_webhook_protection(
    storage,
    save_test_company,
    test_company, 
    test_user,
    yoomoney_provider,
    payment_service,
    unique_id
):
    """
    Тест защиты от дубликатов webhook.
    Проверяет что один платеж не обрабатывается дважды.
    """
    test_company.balance = 5000.0
    
    result = await payment_service.create_payment(
        company=test_company,
        user=test_user,
        amount=1000.0,
        provider=yoomoney_provider
    )
    
    transaction_id = result["transaction_id"]
    
    unique_op_id = unique_id("duplicate_test_op")
    webhook_data = {
        "notification_type": "p2p-incoming",
        "operation_id": unique_op_id,
        "amount": "1000.00",
        "currency": "643",
        "datetime": "2023-12-01T15:00:00Z",
        "sender": "410002222222222",
        "codepro": "false",
        "label": transaction_id
    }
    
    # Генерируем подпись
    secret = yoomoney_provider.config.notification_secret
    check_string = (
        f"{webhook_data['notification_type']}&{webhook_data['operation_id']}&"
        f"{webhook_data['amount']}&{webhook_data['currency']}&"
        f"{webhook_data['datetime']}&{webhook_data['sender']}&"
        f"{webhook_data['codepro']}&{secret}&{webhook_data['label']}"
    )
    webhook_data["sha1_hash"] = hashlib.sha1(check_string.encode('utf-8')).hexdigest()
    
    verification_result = await yoomoney_provider.verify_webhook(webhook_data)
    
    initial_company_data = await storage.get(f"company:{test_company.company_id}", force_global=True)
    initial_company = Company.model_validate_json(initial_company_data)
    initial_balance = initial_company.balance
    
    await payment_service.process_webhook(
        verification_result=verification_result,
        provider_name="yoomoney_main",
        raw_data=webhook_data
    )
    
    after_first_data = await storage.get(f"company:{test_company.company_id}", force_global=True)
    after_first_company = Company.model_validate_json(after_first_data)
    assert after_first_company.balance == initial_balance + 1000.0
    
    await payment_service.process_webhook(
        verification_result=verification_result,
        provider_name="yoomoney_main",
        raw_data=webhook_data
    )
    
    after_second_data = await storage.get(f"company:{test_company.company_id}", force_global=True)
    after_second_company = Company.model_validate_json(after_second_data)
    assert after_second_company.balance == after_first_company.balance, "Баланс не должен увеличиваться повторно"


@pytest.mark.asyncio
async def test_company_transactions_persistence(
    storage,
    save_test_company,
    test_company,
    test_user,
    yoomoney_provider,
    payment_service,
    unique_id
):
    """
    Тест сохранения множественных транзакций для компании.
    Проверяет что можно получить историю транзакций из БД.
    """
    test_company_id = unique_id("test_txn_company")
    test_company.company_id = test_company_id
    test_company.balance = 5000.0
    
    await storage.set(f"company:{test_company_id}", test_company.model_dump_json(), force_global=True)
    
    created_transactions = []
    
    for i in range(3):
        result = await payment_service.create_payment(
            company=test_company,
            user=test_user,
            amount=1000.0 * (i + 1),
            provider=yoomoney_provider
        )
        created_transactions.append(result["transaction_id"])
    
    import asyncio
    await asyncio.sleep(0.1)
    
    for transaction_id in created_transactions:
        saved_transaction = await payment_service.get_transaction(transaction_id)
        
        assert saved_transaction is not None, f"Транзакция {transaction_id} должна быть в БД"
        assert saved_transaction.company_id == test_company.company_id
        assert saved_transaction.user_id == test_user.user_id
        assert saved_transaction.status == PaymentStatus.PENDING
    
    history = await payment_service.get_company_transactions(
        company_id=test_company.company_id,
        limit=10,
        offset=0
    )
    
    assert len(history) >= 3, f"Должно быть минимум 3 транзакции, получили {len(history)}"
    
    our_transactions = [t for t in history if t.transaction_id in created_transactions]
    assert len(our_transactions) == 3, (
        f"Все наши транзакции должны быть в истории. "
        f"Создали: {len(created_transactions)}, Нашли: {len(our_transactions)}"
    )
    
    for i in range(len(our_transactions) - 1):
        assert our_transactions[i].created_at >= our_transactions[i + 1].created_at


@pytest.mark.asyncio
async def test_webhook_updates_transaction_in_db(
    storage,
    test_user,
    yoomoney_provider,
    payment_service,
    unique_id
):
    """
    Тест что webhook реально обновляет транзакцию в БД.
    """
    webhook_test_company = Company(
        company_id=unique_id("webhook_test_company"),
        subdomain=unique_id("webhook_test"),
        name="Webhook Test Company",
        tariff_plan="premium",
        balance=5000.0,
        monthly_budget=50000.0,
        current_month_spent=0.0,
        status="active"
    )
    
    await storage.set(
        f"company:{webhook_test_company.company_id}",
        webhook_test_company.model_dump_json(),
        force_global=True
    )
    
    result = await payment_service.create_payment(
        company=webhook_test_company,
        user=test_user,
        amount=2500.0,
        provider=yoomoney_provider
    )
    
    transaction_id = result["transaction_id"]
    
    initial_transaction = await payment_service.get_transaction(transaction_id)
    assert initial_transaction is not None
    
    assert initial_transaction.status == PaymentStatus.PENDING
    assert initial_transaction.external_payment_id is None
    assert initial_transaction.completed_at is None
    
    unique_op_id = unique_id("db_update_test_op")
    webhook_data = {
        "notification_type": "p2p-incoming", 
        "operation_id": unique_op_id,
        "amount": "2500.00",
        "currency": "643",
        "datetime": "2023-12-01T18:00:00Z",
        "sender": "410003333333333",
        "codepro": "false", 
        "label": transaction_id
    }
    
    # Генерируем подпись
    secret = yoomoney_provider.config.notification_secret
    check_string = (
        f"{webhook_data['notification_type']}&{webhook_data['operation_id']}&"
        f"{webhook_data['amount']}&{webhook_data['currency']}&"
        f"{webhook_data['datetime']}&{webhook_data['sender']}&"
        f"{webhook_data['codepro']}&{secret}&{webhook_data['label']}"
    )
    webhook_data["sha1_hash"] = hashlib.sha1(check_string.encode('utf-8')).hexdigest()
    
    # Обрабатываем webhook
    verification_result = await yoomoney_provider.verify_webhook(webhook_data)
    
    await payment_service.process_webhook(
        verification_result=verification_result,
        provider_name="yoomoney_main",
        raw_data=webhook_data
    )
    
    updated_transaction = await payment_service.get_transaction(transaction_id)
    assert updated_transaction is not None
    
    assert updated_transaction.status == PaymentStatus.SUCCESS, "Статус должен стать SUCCESS"
    assert updated_transaction.external_payment_id == unique_op_id, "External ID должен записаться"
    assert updated_transaction.completed_at is not None, "Время завершения должно заполниться"
    
    updated_company_data = await storage.get(f"company:{webhook_test_company.company_id}", force_global=True)
    updated_company = Company.model_validate_json(updated_company_data)
    
    assert updated_company.balance == 7500.0, "Баланс должен стать 5000 + 2500 = 7500"


@pytest.mark.asyncio
async def test_invalid_webhook_does_not_affect_db(
    storage,
    save_test_company,
    test_company,
    test_user,
    yoomoney_provider,
    payment_service,
    unique_id
):
    """
    Тест что невалидный webhook НЕ влияет на БД.
    """
    test_company.balance = 5000.0
    
    
    result = await payment_service.create_payment(
        company=test_company,
        user=test_user,
        amount=800.0,
        provider=yoomoney_provider
    )
    
    transaction_id = result["transaction_id"]
    
    initial_transaction = await payment_service.get_transaction(transaction_id)
    assert initial_transaction is not None
    
    initial_company_data = await storage.get(f"company:{test_company.company_id}", force_global=True)
    initial_company = Company.model_validate_json(initial_company_data)
    
    unique_invalid_op = unique_id("invalid_test_op")
    invalid_webhook_data = {
        "notification_type": "p2p-incoming",
        "operation_id": unique_invalid_op,
        "amount": "800.00",
        "currency": "643",
        "datetime": "2023-12-01T20:00:00Z", 
        "sender": "410004444444444",
        "codepro": "false",
        "label": transaction_id,
        "sha1_hash": "invalid_signature_here"
    }
    
    verification_result = await yoomoney_provider.verify_webhook(invalid_webhook_data)
    assert not verification_result.is_valid, "Webhook должен быть невалидным"
    
    unchanged_transaction = await payment_service.get_transaction(transaction_id)
    assert unchanged_transaction is not None
    
    assert unchanged_transaction.status == initial_transaction.status
    assert unchanged_transaction.external_payment_id == initial_transaction.external_payment_id
    assert unchanged_transaction.completed_at == initial_transaction.completed_at
    
    unchanged_company_data = await storage.get(f"company:{test_company.company_id}", force_global=True)
    unchanged_company = Company.model_validate_json(unchanged_company_data)
    
    assert unchanged_company.balance == initial_company.balance, "Баланс не должен измениться от невалидного webhook"


@pytest.mark.asyncio
async def test_transaction_retrieval_from_db(
    storage,
    save_test_company,
    test_company,
    test_user,
    yoomoney_provider,
    payment_service
):
    """
    Тест получения транзакции из БД через сервис.
    """
    test_company.balance = 5000.0
    
    
    result = await payment_service.create_payment(
        company=test_company,
        user=test_user,
        amount=1200.0,
        provider=yoomoney_provider
    )
    
    transaction_id = result["transaction_id"]
    
    retrieved_transaction = await payment_service.get_transaction(transaction_id)
    
    assert retrieved_transaction is not None, "Транзакция должна быть найдена"
    assert retrieved_transaction.transaction_id == transaction_id
    assert retrieved_transaction.company_id == test_company.company_id
    assert retrieved_transaction.user_id == test_user.user_id
    assert retrieved_transaction.amount == 1200.0
    assert retrieved_transaction.status == PaymentStatus.PENDING
    
    nonexistent = await payment_service.get_transaction("txn_nonexistent_12345")
    assert nonexistent is None, "Несуществующая транзакция должна вернуть None"
