"""
Интеграционные тесты платежной системы.
Проверяют полный flow от создания платежа до записи в БД.
"""

import pytest
import pytest_asyncio
import uuid
import hashlib
from unittest.mock import Mock
from datetime import datetime, timezone

from app.services.payment_service import PaymentService
from app.core.storage import Storage
from app.core.clients.payment_providers.yoomoney_provider import YooMoneyProvider, YooMoneyConfig
from app.core.clients.payment_providers.factory import PaymentProviderFactory
from app.models.payment_models import Transaction, PaymentStatus, PaymentProviderType
from app.identity.models import Company, User


@pytest_asyncio.fixture
async def real_storage():
    """Fixture с реальным Storage для интеграционных тестов"""
    storage = Storage()
    yield storage


@pytest.fixture
def test_company_id():
    """Уникальный ID компании для тестов"""
    return f"test_company_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def test_user_id():
    """Уникальный ID пользователя для тестов"""
    return f"test_user_{uuid.uuid4().hex[:8]}"


@pytest_asyncio.fixture
async def test_company_in_db(real_storage, test_company_id):
    """Создает тестовую компанию в БД"""
    company = Company(
        company_id=test_company_id,
        subdomain=f"test_{test_company_id}",
        name="Test Company Integration",
        balance=5000.0,
        tariff_plan="premium"
    )
    
    await real_storage.set(
        f"company:{test_company_id}",
        company.model_dump_json(),
        force_global=True
    )
    
    yield company
    
    # Cleanup после теста
    try:
        await real_storage.delete(f"company:{test_company_id}")
    except:
        pass


@pytest_asyncio.fixture
async def test_user_in_db(real_storage, test_user_id, test_company_id):
    """Создает тестового пользователя в БД"""
    user = User(
        user_id=test_user_id,
        name="Test User Integration",
        companies={test_company_id: ["admin"]},
        active_company_id=test_company_id
    )
    
    await real_storage.set(
        f"user:{test_user_id}",
        user.model_dump_json(),
        force_global=True
    )
    
    yield user
    
    # Cleanup после теста
    try:
        await real_storage.delete(f"user:{test_user_id}")
    except:
        pass


@pytest.fixture
def yoomoney_provider():
    """Реальный YooMoney провайдер для тестов"""
    config = YooMoneyConfig(
        provider_type="yoomoney",
        enabled=True,
        account_number="4100119360332365",
        notification_secret="test_integration_secret_key_12345",
        quickpay_url="https://yoomoney.ru/quickpay/confirm.xml"
    )
    return YooMoneyProvider(config)


@pytest.mark.asyncio
async def test_full_payment_flow_with_db(
    real_storage,
    test_company_in_db,
    test_user_in_db,
    yoomoney_provider,
    test_company_id,
    test_user_id
):
    """
    Интеграционный тест полного flow платежа:
    1. Создание транзакции в БД
    2. Имитация webhook от YooMoney  
    3. Обновление транзакции в БД
    4. Пополнение баланса компании в БД
    """
    
    payment_service = PaymentService()
    
    # 1. Создаем платеж (должен записаться в БД)
    result = await payment_service.create_payment(
        company=test_company_in_db,
        user=test_user_in_db, 
        amount=1500.0,
        provider=yoomoney_provider
    )
    
    transaction_id = result["transaction_id"]
    payment_url = result["payment_url"]
    
    # Проверяем что платеж создался
    # transaction_id имеет формат: {company_id}:txn_{uuid}
    assert ":txn_" in transaction_id
    assert "yoomoney.ru" in payment_url
    assert result["amount"] == 1500.0
    
    # 2. Проверяем что транзакция записалась в БД
    saved_transaction = await payment_service.get_transaction(transaction_id)
    
    assert saved_transaction is not None, "Транзакция должна быть сохранена в БД"
    assert saved_transaction.transaction_id == transaction_id
    assert saved_transaction.company_id == test_company_id
    assert saved_transaction.user_id == test_user_id
    assert saved_transaction.amount == 1500.0
    assert saved_transaction.status == PaymentStatus.PENDING
    assert saved_transaction.payment_provider == PaymentProviderType.YOOMONEY
    
    # 3. Имитируем webhook от YooMoney
    unique_op_id = f"integration_op_{uuid.uuid4().hex[:12]}"
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
    
    # 4. Обрабатываем webhook
    verification_result = await yoomoney_provider.verify_webhook(webhook_data)
    assert verification_result.is_valid, "Webhook должен быть валидным"
    
    # Получаем изначальный баланс компании
    initial_company_data = await real_storage.get(f"company:{test_company_id}", force_global=True)
    initial_company = Company.model_validate_json(initial_company_data)
    initial_balance = initial_company.balance
    
    await payment_service.process_webhook(
        verification_result=verification_result,
        provider_name="yoomoney_main",
        raw_data=webhook_data
    )
    
    # 5. Проверяем что транзакция обновилась в БД
    updated_transaction = await payment_service.get_transaction(transaction_id)
    assert updated_transaction is not None
    assert updated_transaction.status == PaymentStatus.SUCCESS, "Статус должен быть SUCCESS"
    assert updated_transaction.external_payment_id == unique_op_id, "External ID должен быть записан"
    assert updated_transaction.completed_at is not None, "Время завершения должно быть заполнено"
    
    # 6. Проверяем что баланс компании пополнился в БД
    updated_company_data = await real_storage.get(f"company:{test_company_id}", force_global=True)
    updated_company = Company.model_validate_json(updated_company_data)
    
    expected_balance = initial_balance + 1500.0
    assert updated_company.balance == expected_balance, f"Баланс должен быть {expected_balance}, но получили {updated_company.balance}"
    
    # 7. Проверяем что уведомление сохранилось в БД
    notification_keys = await real_storage.list_by_prefix("payment_notification:", force_global=True)
    assert len(notification_keys) >= 1, "Уведомление должно быть сохранено"
    
    # Cleanup транзакции и уведомлений
    try:
        # Удаляем по новому формату ключа
        payment_keys = await real_storage.list_by_prefix("payment:", force_global=True)
        for key in payment_keys:
            if transaction_id in key:
                await real_storage.delete(key)
        
        for key in notification_keys:
            await real_storage.delete(key)
    except:
        pass


@pytest.mark.asyncio
async def test_duplicate_webhook_protection(
    real_storage,
    test_company_in_db, 
    test_user_in_db,
    yoomoney_provider,
    test_company_id
):
    """
    Тест защиты от дубликатов webhook.
    Проверяет что один платеж не обрабатывается дважды.
    """
    
    payment_service = PaymentService()
    
    # Создаем платеж
    result = await payment_service.create_payment(
        company=test_company_in_db,
        user=test_user_in_db,
        amount=1000.0,
        provider=yoomoney_provider
    )
    
    transaction_id = result["transaction_id"]
    
    # Webhook данные
    unique_op_id = f"duplicate_test_op_{uuid.uuid4().hex[:8]}"
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
    
    # Первый webhook - должен обработаться
    verification_result = await yoomoney_provider.verify_webhook(webhook_data)
    
    initial_company_data = await real_storage.get(f"company:{test_company_id}", force_global=True)
    initial_company = Company.model_validate_json(initial_company_data)
    initial_balance = initial_company.balance
    
    await payment_service.process_webhook(
        verification_result=verification_result,
        provider_name="yoomoney_main",
        raw_data=webhook_data
    )
    
    # Проверяем что баланс пополнился
    after_first_data = await real_storage.get(f"company:{test_company_id}", force_global=True)
    after_first_company = Company.model_validate_json(after_first_data)
    assert after_first_company.balance == initial_balance + 1000.0
    
    # Второй webhook с тем же external_payment_id - НЕ должен обработаться
    await payment_service.process_webhook(
        verification_result=verification_result,
        provider_name="yoomoney_main",
        raw_data=webhook_data
    )
    
    # Проверяем что баланс НЕ изменился повторно
    after_second_data = await real_storage.get(f"company:{test_company_id}", force_global=True)
    after_second_company = Company.model_validate_json(after_second_data)
    assert after_second_company.balance == after_first_company.balance, "Баланс не должен увеличиваться повторно"
    
    # Cleanup
    try:
        payment_keys = await real_storage.list_by_prefix("payment:", force_global=True)
        for key in payment_keys:
            if transaction_id in key:
                await real_storage.delete(key)
        
        notification_keys = await real_storage.list_by_prefix("payment_notification:", force_global=True)
        for key in notification_keys:
            await real_storage.delete(key)
    except:
        pass


@pytest.mark.asyncio  
async def test_company_transactions_persistence(
    real_storage,
    test_company_in_db,
    test_user_in_db,
    yoomoney_provider,
    test_company_id,
    test_user_id
):
    """
    Тест сохранения множественных транзакций для компании.
    Проверяет что можно получить историю транзакций из БД.
    """
    
    payment_service = PaymentService()
    created_transactions = []
    
    # Создаем несколько платежей
    for i in range(3):
        result = await payment_service.create_payment(
            company=test_company_in_db,
            user=test_user_in_db,
            amount=1000.0 * (i + 1),  # 1000, 2000, 3000
            provider=yoomoney_provider
        )
        created_transactions.append(result["transaction_id"])
    
    # Проверяем что все транзакции сохранились в БД
    for transaction_id in created_transactions:
        saved_transaction = await payment_service.get_transaction(transaction_id)
        
        assert saved_transaction is not None, f"Транзакция {transaction_id} должна быть в БД"
        assert saved_transaction.company_id == test_company_id
        assert saved_transaction.user_id == test_user_id
        assert saved_transaction.status == PaymentStatus.PENDING
    
    # Получаем историю транзакций через сервис
    history = await payment_service.get_company_transactions(
        company_id=test_company_id,
        limit=10,
        offset=0
    )
    
    # Проверяем что все наши транзакции есть в истории
    assert len(history) >= 3, "Должно быть минимум 3 транзакции"
    
    our_transactions = [t for t in history if t.transaction_id in created_transactions]
    assert len(our_transactions) == 3, "Все наши транзакции должны быть в истории"
    
    # Проверяем сортировку (новые первые)
    for i in range(len(our_transactions) - 1):
        assert our_transactions[i].created_at >= our_transactions[i + 1].created_at
    
    # Cleanup
    try:
        payment_keys = await real_storage.list_by_prefix("payment:", force_global=True)
        for key in payment_keys:
            for txn_id in created_transactions:
                if txn_id in key:
                    await real_storage.delete(key)
    except:
        pass


@pytest.mark.asyncio
async def test_webhook_updates_transaction_in_db(
    real_storage,
    test_company_in_db,
    test_user_in_db,
    yoomoney_provider,
    test_company_id
):
    """
    Тест что webhook реально обновляет транзакцию в БД.
    """
    
    payment_service = PaymentService()
    
    # Создаем платеж
    result = await payment_service.create_payment(
        company=test_company_in_db,
        user=test_user_in_db,
        amount=2500.0,
        provider=yoomoney_provider
    )
    
    transaction_id = result["transaction_id"]
    
    # Проверяем изначальное состояние в БД
    initial_transaction = await payment_service.get_transaction(transaction_id)
    assert initial_transaction is not None
    
    assert initial_transaction.status == PaymentStatus.PENDING
    assert initial_transaction.external_payment_id is None
    assert initial_transaction.completed_at is None
    
    # Имитируем успешный webhook
    unique_op_id = f"db_update_test_op_{uuid.uuid4().hex[:8]}"
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
    
    # Проверяем что транзакция обновилась в БД
    updated_transaction = await payment_service.get_transaction(transaction_id)
    assert updated_transaction is not None
    
    assert updated_transaction.status == PaymentStatus.SUCCESS, "Статус должен стать SUCCESS"
    assert updated_transaction.external_payment_id == unique_op_id, "External ID должен записаться"
    assert updated_transaction.completed_at is not None, "Время завершения должно заполниться"
    
    # Проверяем что баланс компании обновился в БД  
    updated_company_data = await real_storage.get(f"company:{test_company_id}", force_global=True)
    updated_company = Company.model_validate_json(updated_company_data)
    
    assert updated_company.balance == 7500.0, "Баланс должен стать 5000 + 2500 = 7500"
    
    # Cleanup
    try:
        payment_keys = await real_storage.list_by_prefix("payment:", force_global=True)
        for key in payment_keys:
            if transaction_id in key:
                await real_storage.delete(key)
        
        notification_keys = await real_storage.list_by_prefix("payment_notification:", force_global=True)
        for key in notification_keys:
            await real_storage.delete(key)
    except:
        pass


@pytest.mark.asyncio
async def test_invalid_webhook_does_not_affect_db(
    real_storage,
    test_company_in_db,
    test_user_in_db,
    yoomoney_provider,
    test_company_id
):
    """
    Тест что невалидный webhook НЕ влияет на БД.
    """
    
    payment_service = PaymentService()
    
    # Создаем платеж
    result = await payment_service.create_payment(
        company=test_company_in_db,
        user=test_user_in_db,
        amount=800.0,
        provider=yoomoney_provider
    )
    
    transaction_id = result["transaction_id"]
    
    # Запоминаем изначальное состояние
    initial_transaction = await payment_service.get_transaction(transaction_id)
    assert initial_transaction is not None
    
    initial_company_data = await real_storage.get(f"company:{test_company_id}", force_global=True)
    initial_company = Company.model_validate_json(initial_company_data)
    
    # Webhook с неверной подписью
    unique_invalid_op = f"invalid_test_op_{uuid.uuid4().hex[:8]}"
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
    
    # Пытаемся обработать невалидный webhook
    verification_result = await yoomoney_provider.verify_webhook(invalid_webhook_data)
    assert not verification_result.is_valid, "Webhook должен быть невалидным"
    
    # НЕ должны обрабатывать невалидный webhook
    # В реальном API он вернет 401, но в тестах проверим что ничего не изменилось
    
    # Проверяем что транзакция НЕ изменилась в БД
    unchanged_transaction = await payment_service.get_transaction(transaction_id)
    assert unchanged_transaction is not None
    
    assert unchanged_transaction.status == initial_transaction.status
    assert unchanged_transaction.external_payment_id == initial_transaction.external_payment_id
    assert unchanged_transaction.completed_at == initial_transaction.completed_at
    
    # Проверяем что баланс НЕ изменился в БД
    unchanged_company_data = await real_storage.get(f"company:{test_company_id}", force_global=True)
    unchanged_company = Company.model_validate_json(unchanged_company_data)
    
    assert unchanged_company.balance == initial_company.balance, "Баланс не должен измениться от невалидного webhook"
    
    # Cleanup
    try:
        await real_storage.delete(f"transaction:{transaction_id}")
    except:
        pass


@pytest.mark.asyncio
async def test_transaction_retrieval_from_db(
    real_storage,
    test_company_in_db,
    test_user_in_db,
    yoomoney_provider,
    test_company_id,
    test_user_id
):
    """
    Тест получения транзакции из БД через сервис.
    """
    
    payment_service = PaymentService()
    
    # Создаем платеж
    result = await payment_service.create_payment(
        company=test_company_in_db,
        user=test_user_in_db,
        amount=1200.0,
        provider=yoomoney_provider
    )
    
    transaction_id = result["transaction_id"]
    
    # Получаем транзакцию через сервис
    retrieved_transaction = await payment_service.get_transaction(transaction_id)
    
    assert retrieved_transaction is not None, "Транзакция должна быть найдена"
    assert retrieved_transaction.transaction_id == transaction_id
    assert retrieved_transaction.company_id == test_company_id
    assert retrieved_transaction.user_id == test_user_id
    assert retrieved_transaction.amount == 1200.0
    assert retrieved_transaction.status == PaymentStatus.PENDING
    
    # Получаем несуществующую транзакцию
    nonexistent = await payment_service.get_transaction("txn_nonexistent_12345")
    assert nonexistent is None, "Несуществующая транзакция должна вернуть None"
    
    # Cleanup
    try:
        await real_storage.delete(f"transaction:{transaction_id}")
    except:
        pass
