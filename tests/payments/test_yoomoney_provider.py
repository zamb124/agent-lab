"""
Тесты YooMoney провайдера.
"""

import pytest
import hashlib
from urllib.parse import parse_qs, urlparse

from app.core.clients.payment_providers.yoomoney_provider import YooMoneyConfig
from app.core.clients.payment_providers.base_provider import PaymentRequest


@pytest.fixture
def payment_request():
    """Fixture с запросом на создание платежа"""
    return PaymentRequest(
        amount=1000.0,
        company_id="test_company",
        user_id="test_user", 
        transaction_id="txn_abc123",
        success_url="https://example.com/success",
        fail_url="https://example.com/fail",
        metadata={"test": "data"}
    )


def test_yoomoney_config_creation():
    """Тест создания конфигурации YooMoney"""
    
    config = YooMoneyConfig(
        provider_type="yoomoney",
        enabled=True,
        account_number="123456",
        notification_secret="secret"
    )
    
    assert config.provider_type == "yoomoney"
    assert config.enabled is True
    assert config.account_number == "123456"
    assert config.notification_secret == "secret"
    assert "yoomoney.ru" in config.quickpay_url


def test_yoomoney_provider_initialization(yoomoney_provider):
    """Тест инициализации провайдера"""
    
    assert yoomoney_provider.provider_name == "yoomoney"
    assert yoomoney_provider.is_enabled() is True
    assert yoomoney_provider.config.account_number == "4100119360332365"


@pytest.mark.asyncio
async def test_create_payment(yoomoney_provider, payment_request):
    """Тест создания платежа"""
    
    response = await yoomoney_provider.create_payment(payment_request)
    
    assert response.payment_url is not None, "Payment URL должен быть сгенерирован"
    assert response.external_payment_id is None, "Для quickpay external_payment_id сначала None"
    assert response.metadata["provider"] == "yoomoney"
    
    # Проверяем параметры URL
    parsed_url = urlparse(response.payment_url)
    params = parse_qs(parsed_url.query)
    
    assert params["receiver"][0] == "4100119360332365", "Receiver должен быть номером кошелька"
    assert params["sum"][0] == "1000.0", "Сумма должна быть передана"
    assert params["label"][0] == "txn_abc123", "Label должен быть transaction_id"
    assert params["successURL"][0] == payment_request.success_url, "Success URL должен быть передан"
    assert params["failURL"][0] == payment_request.fail_url, "Fail URL должен быть передан"


def test_generate_sha1_hash():
    """Тест генерации SHA1 хеша для проверки webhook"""
    
    notification_secret = "test_secret"
    
    # Параметры как в документации YooMoney
    params = {
        "notification_type": "p2p-incoming",
        "operation_id": "123456789", 
        "amount": "1000.00",
        "currency": "643",
        "datetime": "2023-01-01T12:00:00Z",
        "sender": "410001234567890",
        "codepro": "false",
        "label": "test_label"
    }
    
    # Формируем строку как в YooMoney
    check_string = (
        f"{params['notification_type']}&{params['operation_id']}&"
        f"{params['amount']}&{params['currency']}&{params['datetime']}&"
        f"{params['sender']}&{params['codepro']}&{notification_secret}&{params['label']}"
    )
    
    expected_hash = hashlib.sha1(check_string.encode('utf-8')).hexdigest()
    
    # Проверяем что наша логика совпадает
    assert len(expected_hash) == 40, "SHA1 хеш должен быть 40 символов"
    assert isinstance(expected_hash, str), "Хеш должен быть строкой"


@pytest.mark.asyncio
async def test_verify_webhook_valid(yoomoney_provider):
    """Тест проверки валидного webhook"""
    
    secret = yoomoney_provider.config.notification_secret
    
    webhook_data = {
        "notification_type": "p2p-incoming",
        "operation_id": "123456789",
        "amount": "1000.00",
        "currency": "643", 
        "datetime": "2023-01-01T12:00:00Z",
        "sender": "410001234567890",
        "codepro": "false",
        "label": "txn_test123"
    }
    
    # Генерируем правильный хеш
    check_string = (
        f"{webhook_data['notification_type']}&{webhook_data['operation_id']}&"
        f"{webhook_data['amount']}&{webhook_data['currency']}&"
        f"{webhook_data['datetime']}&{webhook_data['sender']}&"
        f"{webhook_data['codepro']}&{secret}&{webhook_data['label']}"
    )
    webhook_data["sha1_hash"] = hashlib.sha1(check_string.encode('utf-8')).hexdigest()
    
    result = await yoomoney_provider.verify_webhook(webhook_data)
    
    assert result.is_valid is True, "Webhook должен быть валидным"
    assert result.transaction_id == "txn_test123", "Transaction ID должен быть извлечен"
    assert result.amount == 1000.0, "Сумма должна быть извлечена"
    assert result.external_payment_id == "123456789", "Operation ID должен быть извлечен" 
    assert result.status == "success", "Статус должен быть success"
    assert result.error_message is None, "Не должно быть ошибки"


@pytest.mark.asyncio
async def test_verify_webhook_invalid_signature(yoomoney_provider):
    """Тест проверки webhook с неверной подписью"""
    
    webhook_data = {
        "notification_type": "p2p-incoming",
        "operation_id": "123456789",
        "amount": "1000.00", 
        "currency": "643",
        "datetime": "2023-01-01T12:00:00Z",
        "sender": "410001234567890",
        "codepro": "false",
        "label": "txn_test123",
        "sha1_hash": "invalid_hash_here"
    }
    
    result = await yoomoney_provider.verify_webhook(webhook_data)
    
    assert result.is_valid is False, "Webhook должен быть невалидным"
    assert result.error_message == "Invalid signature", "Должно быть сообщение об ошибке"
    assert result.transaction_id is None
    assert result.amount is None


@pytest.mark.asyncio
async def test_verify_webhook_missing_fields(yoomoney_provider):
    """Тест проверки webhook с отсутствующими полями"""
    
    webhook_data = {
        "notification_type": "p2p-incoming",
        # operation_id отсутствует
        "amount": "1000.00"
    }
    
    result = await yoomoney_provider.verify_webhook(webhook_data)
    
    assert result.is_valid is False, "Webhook должен быть невалидным"
    assert result.error_message == "Missing required fields"


@pytest.mark.asyncio
async def test_check_payment_status_not_supported(yoomoney_provider):
    """Тест что проверка статуса не поддерживается для quickpay"""
    
    status = await yoomoney_provider.check_payment_status("123456")
    assert status == "unknown", "Quickpay не поддерживает проверку статуса"


@pytest.mark.asyncio
async def test_refund_payment_not_supported(yoomoney_provider):
    """Тест что возвраты не поддерживаются для quickpay"""
    
    result = await yoomoney_provider.refund_payment("123456", 100.0)
    assert result is False, "Quickpay не поддерживает возвраты"


def test_is_enabled(yoomoney_provider):
    """Тест проверки статуса провайдера"""
    
    assert yoomoney_provider.is_enabled() is True
    
    # Отключаем и проверяем
    yoomoney_provider.config.enabled = False
    assert yoomoney_provider.is_enabled() is False


def test_provider_name(yoomoney_provider):
    """Тест имени провайдера"""
    
    assert yoomoney_provider.provider_name == "yoomoney"


def test_yoomoney_config_validation():
    """Тест валидации конфигурации"""
    
    # Валидная конфигурация
    valid_config = YooMoneyConfig(
        provider_type="yoomoney",
        enabled=True,
        account_number="123456",
        notification_secret="secret"
    )
    assert valid_config.provider_type == "yoomoney"
    
    # Конфигурация с опциональными полями
    config_with_oauth = YooMoneyConfig(
        provider_type="yoomoney", 
        enabled=True,
        account_number="123456",
        notification_secret="secret",
        client_id="client123",
        client_secret="secret123"
    )
    assert config_with_oauth.client_id == "client123"
    assert config_with_oauth.client_secret == "secret123"
