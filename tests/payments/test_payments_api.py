"""
Тесты API endpoints для платежей.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI

from app.api.v1.payments import router
from app.models.payment_models import Transaction, PaymentStatus, PaymentProviderType
from app.models import Context
from app.identity.models import Company, User


@pytest.fixture
def app():
    """Fixture с FastAPI приложением для тестов"""
    test_app = FastAPI()
    test_app.include_router(router)
    return test_app


@pytest.fixture 
def client(app):
    """Fixture с тест клиентом"""
    return TestClient(app)


@pytest.fixture
def test_context():
    """Fixture с тестовым контекстом"""
    company = Company(
        company_id="test_company",
        subdomain="test",
        name="Test Company", 
        balance=5000.0,
        payment_provider=None  # Для некоторых тестов не указываем провайдер
    )
    
    user = User(
        user_id="test_user",
        name="Test User",
        companies={"test_company": ["admin"]},
        active_company_id="test_company"
    )
    
    return Context(
        user=user,
        active_company=company,
        user_companies=[company],
        platform="api",
        metadata={"authenticated": True}
    )


@pytest.fixture
def mock_payment_service():
    """Fixture с мок сервисом платежей"""
    service = Mock()
    service.create_payment = AsyncMock(return_value={
        "transaction_id": "txn_test123",
        "payment_url": "https://yoomoney.ru/quickpay/confirm.xml?params",
        "amount": 1000.0
    })
    service.get_transaction = AsyncMock(return_value=Transaction(
        transaction_id="txn_test123",
        company_id="test_company", 
        user_id="test_user",
        amount=1000.0,
        status=PaymentStatus.SUCCESS,
        payment_provider=PaymentProviderType.YOOMONEY
    ))
    service.get_company_transactions = AsyncMock(return_value=[])
    service.process_webhook = AsyncMock()
    return service


@pytest.fixture
def mock_provider_factory():
    """Fixture с мок фабрикой провайдеров"""
    factory = Mock()
    
    mock_provider = Mock()
    mock_provider.provider_name = "yoomoney"
    mock_provider.verify_webhook = AsyncMock(return_value=WebhookVerificationResult(
        is_valid=True,
        transaction_id="txn_test123",
        amount=1000.0,
        external_payment_id="yoomoney_op_123",
        status="success"
    ))
    
    factory.get_available_providers = Mock(return_value={"yoomoney_main": mock_provider})
    factory.get_provider = Mock(return_value=mock_provider)
    
    return factory, mock_provider


@pytest.mark.asyncio
async def test_create_payment_success(app, test_context, mock_payment_service):
    """Тест успешного создания платежа"""
    
    from app.frontend.dependencies import get_request_context
    from app.services.payment_service import PaymentService
    from app.core.clients.payment_providers.factory import PaymentProviderFactory
    
    # Мокируем dependencies через app.dependency_overrides
    app.dependency_overrides[get_request_context] = lambda: test_context
    app.dependency_overrides[PaymentService] = lambda: mock_payment_service
    
    # Мокируем фабрику провайдеров
    mock_provider = Mock()
    mock_provider.provider_name = "yoomoney"  # Важно! Должно быть строкой
    mock_provider.create_payment = AsyncMock(return_value=Mock(
        payment_url="https://yoomoney.ru/quickpay/confirm.xml?params",
        external_payment_id=None,
        metadata={"provider": "yoomoney"}
    ))
    
    def mock_get_provider(name):
        return mock_provider
    
    def mock_get_available():
        return {"yoomoney_main": mock_provider}
    
    PaymentProviderFactory.get_provider = mock_get_provider
    PaymentProviderFactory.get_available_providers = mock_get_available
    
    try:
        with TestClient(app) as client:
            response = client.post("/payments/create", json={
                "amount": 1000.0,
                "provider": "yoomoney_main"
            })
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["transaction_id"].startswith("txn_"), "ID должен начинаться с txn_"
        assert data["payment_url"] == "https://yoomoney.ru/quickpay/confirm.xml?params"
        assert data["provider"] == "yoomoney_main"
        assert data["status"] == "pending"
        assert data["amount"] == 1000.0
    finally:
        # Очистка
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_payment_no_providers(app, test_context):
    """Тест создания платежа когда нет доступных провайдеров"""
    
    from app.frontend.dependencies import get_request_context
    from app.core.clients.payment_providers.factory import PaymentProviderFactory
    
    # Мокируем dependencies
    app.dependency_overrides[get_request_context] = lambda: test_context
    
    # Мокируем отсутствие провайдеров
    original_get_available = PaymentProviderFactory.get_available_providers
    original_get_provider = PaymentProviderFactory.get_provider
    
    PaymentProviderFactory.get_available_providers = lambda: {}
    PaymentProviderFactory.get_provider = lambda name: None
    
    try:
        with TestClient(app) as client:
            response = client.post("/payments/create", json={
                "amount": 1000.0
            })
        
        assert response.status_code == 400
        assert "Нет доступных платежных провайдеров" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()
        PaymentProviderFactory.get_available_providers = original_get_available
        PaymentProviderFactory.get_provider = original_get_provider


@patch('app.frontend.dependencies.get_request_context')
@patch('app.api.v1.payments.PaymentService')
@pytest.mark.asyncio
async def test_get_transaction_success(mock_service_class, mock_context, client, test_context, mock_payment_service):
    """Тест получения информации о транзакции"""
    
    mock_context.return_value = test_context
    mock_service_class.return_value = mock_payment_service
    
    response = client.get("/payments/transaction/txn_test123")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["transaction_id"] == "txn_test123"
    assert data["company_id"] == "test_company"
    assert data["amount"] == 1000.0


@patch('app.frontend.dependencies.get_request_context')
@patch('app.api.v1.payments.PaymentService')
@pytest.mark.asyncio
async def test_get_transaction_not_found(mock_service_class, mock_context, client, test_context):
    """Тест получения несуществующей транзакции"""
    
    mock_context.return_value = test_context
    
    service_mock = Mock()
    service_mock.get_transaction = AsyncMock(return_value=None)
    mock_service_class.return_value = service_mock
    
    response = client.get("/payments/transaction/nonexistent")
    
    assert response.status_code == 404
    assert "Транзакция не найдена" in response.json()["detail"]


@patch('app.frontend.dependencies.get_request_context')  
@patch('app.api.v1.payments.PaymentService')
@pytest.mark.asyncio
async def test_get_transaction_wrong_company(mock_service_class, mock_context, client, test_context):
    """Тест получения транзакции другой компании"""
    
    mock_context.return_value = test_context
    
    # Транзакция принадлежит другой компании
    other_transaction = Transaction(
        transaction_id="txn_other",
        company_id="other_company",  # Другая компания!
        user_id="test_user", 
        amount=1000.0,
        status=PaymentStatus.SUCCESS,
        payment_provider=PaymentProviderType.YOOMONEY
    )
    
    service_mock = Mock()
    service_mock.get_transaction = AsyncMock(return_value=other_transaction)
    mock_service_class.return_value = service_mock
    
    response = client.get("/payments/transaction/txn_other")
    
    assert response.status_code == 403
    assert "Доступ запрещен" in response.json()["detail"]


@patch('app.frontend.dependencies.get_request_context')
@patch('app.api.v1.payments.PaymentService') 
@pytest.mark.asyncio
async def test_get_payment_history(mock_service_class, mock_context, client, test_context, mock_payment_service):
    """Тест получения истории платежей"""
    
    mock_context.return_value = test_context
    mock_service_class.return_value = mock_payment_service
    
    response = client.get("/payments/history?limit=10&offset=0")
    
    assert response.status_code == 200
    data = response.json()
    
    assert "transactions" in data
    assert "total" in data
    assert "limit" in data
    assert "offset" in data


@patch('app.api.v1.payments.PaymentProviderFactory')
@pytest.mark.asyncio
async def test_webhook_success(mock_factory, client):
    """Тест успешной обработки webhook"""
    
    factory_mock, provider_mock = mock_provider_factory()
    mock_factory.get_provider.return_value = provider_mock
    
    with patch('app.api.v1.payments.PaymentService') as mock_service_class:
        service_mock = Mock()
        service_mock.process_webhook = AsyncMock()
        mock_service_class.return_value = service_mock
        
        # Имитируем webhook данные от YooMoney
        webhook_data = {
            "notification_type": "p2p-incoming",
            "operation_id": "123456789",
            "amount": "1000.00",
            "label": "txn_test123",
            "sha1_hash": "valid_hash"
        }
        
        response = client.post(
            "/payments/webhook/yoomoney_main",
            data=webhook_data,
            headers={"content-type": "application/x-www-form-urlencoded"}
        )
        
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        
        # Проверяем что webhook был обработан
        service_mock.process_webhook.assert_called_once()


@patch('app.api.v1.payments.PaymentProviderFactory')
@pytest.mark.asyncio
async def test_webhook_invalid_signature(mock_factory, client):
    """Тест webhook с неверной подписью"""
    
    provider_mock = Mock()
    from app.core.clients.payment_providers.base_provider import WebhookVerificationResult
    
    provider_mock.verify_webhook = AsyncMock(return_value=WebhookVerificationResult(
        is_valid=False,
        error_message="Invalid signature"
    ))
    
    mock_factory.get_provider.return_value = provider_mock
    
    response = client.post(
        "/payments/webhook/yoomoney_main", 
        data={"invalid": "data"},
        headers={"content-type": "application/x-www-form-urlencoded"}
    )
    
    assert response.status_code == 401
    assert "Invalid signature" in response.json()["detail"]


@pytest.mark.asyncio
async def test_webhook_unknown_provider(client):
    """Тест webhook для неизвестного провайдера"""
    
    response = client.post(
        "/payments/webhook/unknown_provider",
        data={"test": "data"},
        headers={"content-type": "application/x-www-form-urlencoded"}
    )
    
    assert response.status_code == 404
    assert "Провайдер unknown_provider не найден" in response.json()["detail"]


def test_get_available_providers(client):
    """Тест получения списка доступных провайдеров"""
    
    with patch('app.api.v1.payments.PaymentProviderFactory') as mock_factory:
        mock_factory.list_providers.return_value = [
            {"name": "yoomoney_main", "type": "yoomoney", "enabled": True}
        ]
        
        response = client.get("/payments/providers")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "providers" in data
        assert len(data["providers"]) == 1
        assert data["providers"][0]["name"] == "yoomoney_main"


def mock_provider_factory():
    """Вспомогательная функция для создания мок фабрики"""
    
    from app.core.clients.payment_providers.base_provider import WebhookVerificationResult
    
    provider_mock = Mock()
    provider_mock.verify_webhook = AsyncMock(return_value=WebhookVerificationResult(
        is_valid=True,
        transaction_id="txn_test123", 
        amount=1000.0,
        external_payment_id="yoomoney_op_123",
        status="success"
    ))
    
    factory_mock = Mock()
    factory_mock.get_provider.return_value = provider_mock
    
    return factory_mock, provider_mock
