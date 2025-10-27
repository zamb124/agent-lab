"""
Тесты фабрики платежных провайдеров.
"""

import pytest
from pydantic import BaseModel

from app.core.clients.payment_providers.factory import PaymentProviderFactory
from app.core.clients.payment_providers.yoomoney_provider import YooMoneyProvider, YooMoneyConfig
from app.core.clients.payment_providers.yukassa_provider import YuKassaConfig


class MockSettings(BaseModel):
    """Мок настроек для тестов"""
    
    class PaymentProviders(BaseModel):
        default_provider: str = "yoomoney_main"
        providers: dict = {
            "yoomoney_main": {
                "provider_type": "yoomoney",
                "enabled": True,
                "account_number": "4100119360332365",
                "notification_secret": "test_secret",
                "quickpay_url": "https://yoomoney.ru/quickpay/confirm.xml"
            },
            "yukassa_disabled": {
                "provider_type": "yukassa", 
                "enabled": False,
                "shop_id": "123456",
                "secret_key": "test_key"
            }
        }
    
    payment_providers: PaymentProviders = PaymentProviders()


@pytest.fixture
def mock_settings():
    """Fixture с тестовыми настройками"""
    return MockSettings()


@pytest.fixture(autouse=True)
def clear_factory():
    """Очистка фабрики перед каждым тестом"""
    PaymentProviderFactory._providers.clear()
    PaymentProviderFactory._configs.clear()
    yield
    PaymentProviderFactory._providers.clear()
    PaymentProviderFactory._configs.clear()


def test_factory_initialization(mock_settings):
    """Тест инициализации фабрики"""
    
    PaymentProviderFactory.initialize(mock_settings)
    
    providers = PaymentProviderFactory.get_available_providers()
    
    assert len(providers) == 1, "Должен быть инициализирован 1 активный провайдер"
    assert "yoomoney_main" in providers, "yoomoney_main должен быть инициализирован"
    assert isinstance(providers["yoomoney_main"], YooMoneyProvider), "Должен быть YooMoneyProvider"


def test_factory_get_provider(mock_settings):
    """Тест получения провайдера по имени"""
    
    PaymentProviderFactory.initialize(mock_settings)
    
    provider = PaymentProviderFactory.get_provider("yoomoney_main")
    assert provider is not None, "Провайдер должен быть найден"
    assert provider.provider_name == "yoomoney", "Тип провайдера должен быть yoomoney"
    
    nonexistent = PaymentProviderFactory.get_provider("nonexistent")
    assert nonexistent is None, "Несуществующий провайдер должен вернуть None"


def test_factory_disabled_provider(mock_settings):
    """Тест что отключенные провайдеры не инициализируются"""
    
    PaymentProviderFactory.initialize(mock_settings)
    
    providers = PaymentProviderFactory.get_available_providers()
    
    assert "yukassa_disabled" not in providers, "Отключенный провайдер не должен быть инициализирован"


def test_factory_default_provider(mock_settings):
    """Тест выбора дефолтного провайдера"""
    
    PaymentProviderFactory.initialize(mock_settings)
    
    default = PaymentProviderFactory._get_default_provider()
    assert default == "yoomoney_main", "Должен вернуть дефолтный провайдер из конфига"


def test_factory_create_config_objects():
    """Тест создания объектов конфигурации"""
    
    yoomoney_dict = {
        "provider_type": "yoomoney",
        "enabled": True,
        "account_number": "123",
        "notification_secret": "secret"
    }
    
    config = PaymentProviderFactory._create_config_object(yoomoney_dict)
    assert isinstance(config, YooMoneyConfig), "Должен создать YooMoneyConfig"
    assert config.provider_type == "yoomoney"
    assert config.account_number == "123"
    
    yukassa_dict = {
        "provider_type": "yukassa",
        "enabled": True,
        "shop_id": "123",
        "secret_key": "key"
    }
    
    config = PaymentProviderFactory._create_config_object(yukassa_dict)
    assert isinstance(config, YuKassaConfig), "Должен создать YuKassaConfig"


def test_factory_unknown_provider_type():
    """Тест обработки неизвестного типа провайдера"""
    
    unknown_dict = {
        "provider_type": "unknown",
        "enabled": True
    }
    
    with pytest.raises(ValueError, match="Неизвестный тип провайдера"):
        PaymentProviderFactory._create_config_object(unknown_dict)


def test_factory_list_providers(mock_settings):
    """Тест получения списка провайдеров"""
    
    PaymentProviderFactory.initialize(mock_settings)
    
    providers_list = PaymentProviderFactory.list_providers()
    
    assert len(providers_list) == 1, "Должен быть 1 провайдер"
    assert providers_list[0]["name"] == "yoomoney_main"
    assert providers_list[0]["type"] == "yoomoney"
    assert providers_list[0]["enabled"] is True


def test_factory_get_provider_for_company():
    """Тест получения провайдера для компании"""
    
    # Мок компании без указанного провайдера
    class MockCompany:
        company_id = "test_company"
        payment_provider = None
    
    # Без инициализированных провайдеров
    provider = PaymentProviderFactory.get_provider_for_company(MockCompany())
    assert provider is None, "Без провайдеров должен вернуть None"
    
    # С инициализированными провайдерами
    PaymentProviderFactory.initialize(MockSettings())
    provider = PaymentProviderFactory.get_provider_for_company(MockCompany())
    assert provider is not None, "Должен вернуть дефолтный провайдер"
    assert provider.provider_name == "yoomoney"
    
    # Компания с указанным провайдером
    MockCompany.payment_provider = "yoomoney_main"
    provider = PaymentProviderFactory.get_provider_for_company(MockCompany())
    assert provider.provider_name == "yoomoney"
