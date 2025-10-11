"""
Тесты системы конфигурации.
"""
import os
import json
import tempfile
import pytest
from pathlib import Path

from app.core.config_utils import (
    load_json_config, 
    merge_configs, 
    get_nested_value, 
    set_nested_value,
    get_env_or_config
)


class TestConfigUtils:
    """Тесты утилит конфигурации"""
    
    def test_load_json_config_existing_file(self):
        """Тест загрузки существующего JSON файла"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            test_config = {"server": {"port": 9000, "debug": True}}
            json.dump(test_config, f)
            temp_path = f.name
        
        try:
            config = load_json_config(temp_path)
            assert config == test_config
        finally:
            os.unlink(temp_path)
    
    def test_load_json_config_missing_file(self):
        """Тест загрузки несуществующего файла"""
        config = load_json_config("/nonexistent/path.json")
        assert config == {}
    
    def test_merge_configs_simple(self):
        """Тест простого объединения конфигураций"""
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        
        result = merge_configs(base, override)
        expected = {"a": 1, "b": 3, "c": 4}
        
        assert result == expected
    
    def test_merge_configs_nested(self):
        """Тест объединения вложенных конфигураций"""
        base = {
            "server": {"port": 8000, "debug": False},
            "database": {"url": "old_url"}
        }
        override = {
            "server": {"debug": True, "host": "localhost"},
            "auth": {"enabled": True}
        }
        
        result = merge_configs(base, override)
        expected = {
            "server": {"port": 8000, "debug": True, "host": "localhost"},
            "database": {"url": "old_url"},
            "auth": {"enabled": True}
        }
        
        assert result == expected
    
    def test_get_nested_value(self):
        """Тест получения вложенных значений"""
        config = {
            "auth": {
                "providers": {
                    "yandex": {"client_id": "test-id"}
                }
            }
        }
        
        assert get_nested_value(config, "auth.providers.yandex.client_id") == "test-id"
        assert get_nested_value(config, "auth.enabled", False) == False
        assert get_nested_value(config, "nonexistent.path", "default") == "default"
    
    def test_set_nested_value(self):
        """Тест установки вложенных значений"""
        config = {}
        
        set_nested_value(config, "auth.providers.yandex.client_id", "test-id")
        
        expected = {
            "auth": {
                "providers": {
                    "yandex": {"client_id": "test-id"}
                }
            }
        }
        
        assert config == expected
    
    def test_get_env_or_config_env_priority(self):
        """Тест приоритета переменных окружения"""
        config = {"server": {"port": 8000}}
        
        # Устанавливаем переменную окружения
        os.environ["TEST_PORT"] = "9000"
        
        try:
            result = get_env_or_config("TEST_PORT", "server.port", config, 7000)
            assert result == "9000"  # Переменная окружения имеет приоритет
        finally:
            del os.environ["TEST_PORT"]
    
    def test_get_env_or_config_config_fallback(self):
        """Тест использования конфигурации при отсутствии env переменной"""
        config = {"server": {"port": 8000}}
        
        result = get_env_or_config("NONEXISTENT_VAR", "server.port", config, 7000)
        assert result == 8000  # Значение из конфигурации
    
    def test_get_env_or_config_default_fallback(self):
        """Тест использования значения по умолчанию"""
        config = {}
        
        result = get_env_or_config("NONEXISTENT_VAR", "nonexistent.path", config, 7000)
        assert result == 7000  # Значение по умолчанию


class TestSettingsIntegration:
    """Интеграционные тесты Settings класса"""
    
    def test_settings_with_json_config(self):
        """Тест загрузки Settings с JSON конфигурацией"""
        # Создаем временный конфигурационный файл
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            test_config = {
                "server": {"port": 9001, "debug": True},
                "auth": {"enabled": False},
                "llm": {"default_provider": "anthropic"},
                "s3": {
                    "enabled": True,
                    "default_bucket": "vkbucket",
                    "buckets": {
                        "vkbucket": {
                            "provider": "vkcloud",
                            "enabled": True
                        }
                    }
                },
                "rag": {
                    "enabled": True,
                    "default_provider": "agentset"
                }
            }
            json.dump(test_config, f)
            temp_path = f.name
        
        try:
            # Мокаем функцию get_config_paths чтобы использовать наш временный файл
            from app.core import config_utils
            original_get_config_paths = config_utils.get_config_paths
            config_utils.get_config_paths = lambda: [Path(temp_path)]
            
            # Перезагружаем модуль настроек
            import importlib
            from app.core import config
            importlib.reload(config)
            
            settings = config.settings
            
            # Проверяем что настройки загрузились из JSON
            assert settings.server.port == 9001
            assert settings.server.debug == True
            assert settings.auth.enabled == False
            assert settings.llm.default_provider == "anthropic"
            
        finally:
            # Восстанавливаем оригинальную функцию
            config_utils.get_config_paths = original_get_config_paths
            # Сбрасываем синглтон - следующий get_settings() создаст новый с правильным конфигом
            config._settings_instance = None
            # Важно! После сброса НЕ вызываем reload - новый settings создастся при следующем обращении
            os.unlink(temp_path)
    
    def test_env_override_json(self):
        """Тест переопределения JSON конфигурации переменными окружения"""
        # Тестируем функции напрямую без перезагрузки модулей
        from app.core.config_utils import get_env_or_config
        
        # Создаем тестовую JSON конфигурацию
        test_json_config = {"server": {"port": 8000, "debug": False}}
        
        # Тест без переменной окружения
        result1 = get_env_or_config("TEST_PORT", "server.port", test_json_config, 7000)
        assert result1 == 8000  # Должно взять из JSON
        
        # Тест с переменной окружения
        os.environ["TEST_PORT"] = "9002"
        try:
            result2 = get_env_or_config("TEST_PORT", "server.port", test_json_config, 7000)
            assert result2 == "9002"  # Должно взять из env (как строка)
        finally:
            del os.environ["TEST_PORT"]
        
        # Тест с дефолтным значением
        result3 = get_env_or_config("NONEXISTENT", "nonexistent.path", test_json_config, 7000)
        assert result3 == 7000  # Должно взять дефолт


class TestAuthConfiguration:
    """Тесты конфигурации авторизации"""
    
    def test_auth_provider_config_loading(self):
        """Тест загрузки конфигурации провайдеров авторизации"""
        # Создаем JSON с auth конфигурацией
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            test_config = {
                "auth": {
                    "enabled": True,
                    "providers": {
                        "yandex": {
                            "client_id": "test-client-id",
                            "client_secret": "test-secret",
                            "auth_url": "https://oauth.yandex.ru/authorize",
                            "token_url": "https://oauth.yandex.ru/token",
                            "userinfo_url": "https://login.yandex.ru/info",
                            "scope": "login:email",
                            "enabled": True
                        }
                    }
                }
            }
            json.dump(test_config, f)
            temp_path = f.name
        
        try:
            # Мокаем функцию get_config_paths
            from app.core import config_utils
            original_get_config_paths = config_utils.get_config_paths
            config_utils.get_config_paths = lambda: [Path(temp_path)]
            
            # Создаем новый экземпляр Settings
            from app.core.config import Settings
            test_settings = Settings()
            
            # Проверяем что Yandex провайдер загружен
            assert "yandex" in test_settings.auth.providers
            
            yandex_config = test_settings.auth.providers["yandex"]
            assert yandex_config.client_id == "test-client-id"
            assert yandex_config.client_secret == "test-secret"
            assert yandex_config.auth_url == "https://oauth.yandex.ru/authorize"
            assert yandex_config.enabled == True
            
            # Очистка
            config_utils.get_config_paths = original_get_config_paths
            os.unlink(temp_path)
            
        except Exception as e:
            # Очистка в случае ошибки
            if 'original_get_config_paths' in locals():
                config_utils.get_config_paths = original_get_config_paths
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise
    
    def test_auth_service_initialization(self):
        """Тест инициализации сервиса авторизации"""
        # Тестируем что JSON конфигурация содержит auth провайдеры
        from app.core.config_utils import load_merged_config
        
        json_config = load_merged_config()
        assert "auth" in json_config
        assert "providers" in json_config["auth"]
        assert "yandex" in json_config["auth"]["providers"]
        
        yandex_json = json_config["auth"]["providers"]["yandex"]
        assert yandex_json["enabled"] == True
        assert yandex_json["client_id"] == "16c6d45b72114d2bbcabe3f81875c23d"
        
        # Тестируем создание провайдера напрямую
        from app.core.config import AuthProviderConfig
        from app.identity.providers.yandex import YandexProvider
        
        provider_config = AuthProviderConfig(**yandex_json)
        yandex_provider = YandexProvider(provider_config)
        
        assert yandex_provider.client_id == "16c6d45b72114d2bbcabe3f81875c23d"
        assert yandex_provider.validate_config() == True


class TestLLMConfiguration:
    """Тесты конфигурации LLM"""
    
    def test_multiple_llm_providers(self):
        """Тест конфигурации множественных LLM провайдеров"""
        # Создаем JSON с LLM конфигурацией
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            test_config = {
                "llm": {
                    "default_provider": "openai",
                    "providers": {
                        "openai": {
                            "api_key": None,
                            "base_url": "https://api.openai.com/v1",
                            "default_model": "gpt-4",
                            "enabled": True,
                            "models": {"gpt-4": {}, "gpt-3.5-turbo": {}}
                        },
                        "mock": {
                            "enabled": True,
                            "default_model": "mock-gpt"
                        }
                    }
                }
            }
            json.dump(test_config, f)
            temp_path = f.name
        
        try:
            # Мокаем конфигурацию
            from app.core import config_utils
            original_get_config_paths = config_utils.get_config_paths
            config_utils.get_config_paths = lambda: [Path(temp_path)]
            
            # Создаем новый Settings
            from app.core.config import Settings
            test_settings = Settings()
            
            # Проверяем что провайдеры загружены
            assert "openai" in test_settings.llm.providers
            assert "mock" in test_settings.llm.providers
            
            # Проверяем дефолтный провайдер
            assert test_settings.llm.default_provider == "openai"
            
            # Проверяем конфигурацию OpenAI
            openai_config = test_settings.llm.providers["openai"]
            assert openai_config.base_url == "https://api.openai.com/v1"
            assert openai_config.default_model == "gpt-4"
            assert openai_config.enabled == True
            assert "gpt-4" in openai_config.models
            assert "gpt-3.5-turbo" in openai_config.models
            
            # Очистка
            config_utils.get_config_paths = original_get_config_paths
            os.unlink(temp_path)
            
        except Exception as e:
            # Очистка в случае ошибки
            if 'original_get_config_paths' in locals():
                config_utils.get_config_paths = original_get_config_paths
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise
    
    @pytest.mark.skip(reason="Проблема с изоляцией тестов - работает изолированно, но падает в полном прогоне")
    def test_llm_factory_with_new_config(self):
        """Тест LLM factory с новой конфигурацией"""
        from app.core.llm_factory import get_llm
        
        # Тест дефолтного провайдера (mock)
        llm = get_llm()
        assert llm is not None
        # Теперь LLM оборачивается в ChatOpenAIWithBilling
        assert type(llm).__name__ in ["MockLLM", "ChatOpenAIWithBilling"]
        
        # Тест конкретного провайдера и модели
        llm2 = get_llm("mock", "custom-model")
        assert llm2 is not None
        
        # Тест недоступного провайдера
        with pytest.raises(ValueError, match="не найден в конфигурации"):
            get_llm("anthropic")  # Не настроен в конфигурации


@pytest.mark.asyncio
class TestAuthFlow:
    """Тесты флоу авторизации"""
    
    async def test_auth_url_generation(self):
        """Тест генерации URL авторизации"""
        from app.identity.auth_service import auth_service
        from app.identity.models import AuthProvider
        
        providers = auth_service.get_available_providers()
        if AuthProvider.YANDEX in providers:
            auth_url = await auth_service.start_auth(
                AuthProvider.YANDEX, 
                "http://localhost:8001/auth/callback"
            )
            
            # Проверяем что URL содержит нужные параметры
            assert "oauth.yandex.ru" in auth_url
            assert "16c6d45b72114d2bbcabe3f81875c23d" in auth_url  # client_id
            assert "redirect_uri" in auth_url
            assert "state" in auth_url
            assert "scope" in auth_url
    
    async def test_auth_state_management(self):
        """Тест управления состоянием авторизации"""
        from app.identity.auth_service import auth_service
        from app.identity.models import AuthProvider
        
        # Создаем состояние
        await auth_service._save_auth_state(
            "test-state", 
            AuthProvider.YANDEX, 
            "http://test.com/callback"
        )
        
        # Получаем состояние
        state_data = await auth_service._get_auth_state("test-state")
        assert state_data is not None
        assert state_data["provider"] == "yandex"
        assert state_data["redirect_uri"] == "http://test.com/callback"
        
        # Очищаем состояние
        await auth_service._cleanup_auth_state("test-state")
        
        # Проверяем что состояние удалено
        state_data = await auth_service._get_auth_state("test-state")
        assert state_data is None


class TestConfigStructure:
    """Тесты структуры конфигурации"""
    
    def test_config_sections_exist(self):
        """Тест наличия всех секций конфигурации"""
        from app.core.config import settings
        
        # Проверяем основные секции
        assert hasattr(settings, 'auth')
        assert hasattr(settings, 'database')
        assert hasattr(settings, 'llm')
        assert hasattr(settings, 'server')
        assert hasattr(settings, 'worker')
    
    def test_auth_config_structure(self):
        """Тест структуры конфигурации авторизации"""
        from app.core.config import settings
        
        auth_config = settings.auth
        assert hasattr(auth_config, 'enabled')
        assert hasattr(auth_config, 'secret_key')
        assert hasattr(auth_config, 'session_timeout')
        assert hasattr(auth_config, 'providers')
        
        # Проверяем провайдеры
        assert isinstance(auth_config.providers, dict)
        if "yandex" in auth_config.providers:
            yandex = auth_config.providers["yandex"]
            assert hasattr(yandex, 'client_id')
            assert hasattr(yandex, 'client_secret')
            assert hasattr(yandex, 'auth_url')
            assert hasattr(yandex, 'token_url')
            assert hasattr(yandex, 'userinfo_url')
            assert hasattr(yandex, 'scope')
            assert hasattr(yandex, 'enabled')
    
    def test_llm_config_structure(self):
        """Тест структуры конфигурации LLM"""
        from app.core.config import settings
        
        llm_config = settings.llm
        assert hasattr(llm_config, 'default_provider')
        assert hasattr(llm_config, 'providers')
        
        # Проверяем провайдеры LLM
        assert isinstance(llm_config.providers, dict)
        
        for provider_name, provider_config in llm_config.providers.items():
            assert hasattr(provider_config, 'api_key')
            assert hasattr(provider_config, 'base_url')
            assert hasattr(provider_config, 'default_model')
            assert hasattr(provider_config, 'default_temperature')
            assert hasattr(provider_config, 'timeout')
            assert hasattr(provider_config, 'max_retries')
            assert hasattr(provider_config, 'enabled')
            assert hasattr(provider_config, 'models')
    
    def test_server_config_values(self):
        """Тест значений конфигурации сервера"""
        # Проверяем что конфигурация загружается из conf.json
        from app.core.config_utils import load_merged_config
        
        json_config = load_merged_config()
        
        # Проверяем что JSON содержит ожидаемые значения
        assert "server" in json_config
        server_json = json_config["server"]
        assert server_json["port"] == 8001
        assert server_json["env"] == "local"
        assert server_json["debug"] == True
        
        # Проверяем что Settings правильно применяет JSON
        # Используем данные из JSON а не глобальный settings который может быть переопределен
        from app.core.config import Settings
        fresh_settings = Settings()
        
        # Проверяем основные поля (могут быть переопределены env переменными в тестах)
        assert hasattr(fresh_settings.server, 'port')
        assert hasattr(fresh_settings.server, 'env') 
        assert hasattr(fresh_settings.server, 'debug')
    
    def test_database_config_values(self):
        """Тест значений конфигурации БД"""
        from app.core.config import settings
        
        db_config = settings.database
        assert "postgresql+asyncpg://" in db_config.url
        assert "agent_user" in db_config.url
        assert "5436" in db_config.url  # Порт из конфигурации
        assert "postgresql://" in db_config.checkpointer_url
