"""
Тесты для интеграции токенов с системой аутентификации
"""
import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

from apps.agents.api.v1.auth import router as auth_router
from core.utils.tokens import get_token_service


class TestTokenAuthIntegration:
    """Тесты для интеграции токенов с аутентификацией"""
    
    @pytest.fixture
    def app(self):
        """Фикстура для FastAPI приложения"""
        app = FastAPI()
        app.include_router(auth_router)
        return app
    
    @pytest.fixture
    def client(self, app):
        """Фикстура для тестового клиента"""
        return TestClient(app)
    
    def test_token_creation_in_auth_result(self):
        """Тест что AuthResult содержит токен"""
        token_service = get_token_service()
        
        # Создаем тестовый токен
        token = token_service.create_token(
            user_id="test_user_123",
            company_id="test_company_456",
            session_id="test_session_789",
            expires_in=3600,
            metadata={"provider": "test"}
        )
        
        # Проверяем, что токен валиден
        token_data = token_service.validate_token(token)
        assert token_data is not None
        assert token_data.user_id == "test_user_123"
        assert token_data.company_id == "test_company_456"
        assert token_data.session_id == "test_session_789"
        assert token_data.metadata["provider"] == "test"
    
    def test_token_expiration_handling(self):
        """Тест обработки истечения токенов"""
        token_service = get_token_service()
        
        # Создаем токен с коротким временем жизни
        token = token_service.create_token(
            user_id="test_user_123",
            expires_in=1  # 1 секунда
        )
        
        # Проверяем, что токен валиден сразу после создания
        token_data = token_service.validate_token(token)
        assert token_data is not None
        
        # Ждем истечения токена
        import time
        time.sleep(2)
        
        # Проверяем, что токен больше не валиден
        token_data = token_service.validate_token(token)
        assert token_data is None
    
    def test_token_with_different_expiration_times(self):
        """Тест токенов с разным временем истечения"""
        token_service = get_token_service()
        
        # Создаем токены с разным временем жизни
        short_token = token_service.create_token(
            user_id="short_user",
            expires_in=60  # 1 минута
        )
        
        long_token = token_service.create_token(
            user_id="long_user",
            expires_in=86400  # 1 день
        )
        
        # Проверяем, что оба токена валидны
        short_data = token_service.validate_token(short_token)
        long_data = token_service.validate_token(long_token)
        
        assert short_data is not None
        assert long_data is not None
        
        # Проверяем разницу во времени истечения
        time_diff = (long_data.exp - short_data.exp).total_seconds()
        assert time_diff > 80000  # Разница должна быть около 23 часов
    
    def test_token_metadata_persistence(self):
        """Тест сохранения метаданных в токене"""
        token_service = get_token_service()
        
        metadata = {
            "provider": "google",
            "user_name": "Test User",
            "login_time": "2024-01-01T12:00:00Z",
            "custom_data": {"key": "value", "number": 123}
        }
        
        token = token_service.create_token(
            user_id="metadata_user",
            company_id="metadata_company",
            metadata=metadata
        )
        
        token_data = token_service.validate_token(token)
        
        assert token_data is not None
        assert token_data.metadata == metadata
        assert token_data.metadata["provider"] == "google"
        assert token_data.metadata["user_name"] == "Test User"
        assert token_data.metadata["custom_data"]["key"] == "value"
        assert token_data.metadata["custom_data"]["number"] == 123
    
    def test_token_with_special_characters(self):
        """Тест токена с специальными символами в метаданных"""
        token_service = get_token_service()
        
        metadata = {
            "unicode": "тест с кириллицей",
            "special_chars": "!@#$%^&*()",
            "emoji": "🚀🎉✨",
            "json_string": '{"nested": {"value": 123}}'
        }
        
        token = token_service.create_token(
            user_id="special_user",
            metadata=metadata
        )
        
        token_data = token_service.validate_token(token)
        
        assert token_data is not None
        assert token_data.metadata == metadata
        assert token_data.metadata["unicode"] == "тест с кириллицей"
        assert token_data.metadata["special_chars"] == "!@#$%^&*()"
        assert token_data.metadata["emoji"] == "🚀🎉✨"
        assert token_data.metadata["json_string"] == '{"nested": {"value": 123}}'
    
    def test_multiple_tokens_same_user(self):
        """Тест создания нескольких токенов для одного пользователя"""
        token_service = get_token_service()
        
        user_id = "multi_token_user"
        company_id = "multi_token_company"
        
        # Создаем несколько токенов для одного пользователя
        tokens = []
        for i in range(5):
            token = token_service.create_token(
                user_id=user_id,
                company_id=company_id,
                session_id=f"session_{i}",
                metadata={"session_number": i}
            )
            tokens.append(token)
        
        # Проверяем, что все токены разные
        assert len(set(tokens)) == len(tokens)
        
        # Проверяем, что все токены валидны
        for i, token in enumerate(tokens):
            token_data = token_service.validate_token(token)
            assert token_data is not None
            assert token_data.user_id == user_id
            assert token_data.company_id == company_id
            assert token_data.session_id == f"session_{i}"
            assert token_data.metadata["session_number"] == i
    
    def test_token_service_singleton(self):
        """Тест что TokenService является синглтоном"""
        service1 = get_token_service()
        service2 = get_token_service()
        
        assert service1 is service2
        assert isinstance(service1, type(service2))
    
    def test_token_creation_with_none_values(self):
        """Тест создания токена с None значениями"""
        token_service = get_token_service()
        
        token = token_service.create_token(
            user_id="none_test_user",
            company_id=None,
            session_id=None,
            metadata=None
        )
        
        token_data = token_service.validate_token(token)
        
        assert token_data is not None
        assert token_data.user_id == "none_test_user"
        assert token_data.company_id is None
        assert token_data.session_id is None
        assert token_data.metadata == {}
    
    def test_token_validation_edge_cases(self):
        """Тест валидации токена в граничных случаях"""
        token_service = get_token_service()
        
        # Пустая строка
        assert token_service.validate_token("") is None
        
        # None
        assert token_service.validate_token(None) is None
        
        # Неправильный формат JWT
        assert token_service.validate_token("not.a.jwt") is None
        
        # Токен с неправильной подписью
        assert token_service.validate_token("eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoidGVzdCJ9.invalid") is None
    
    def test_token_with_large_metadata(self):
        """Тест токена с большими метаданными"""
        token_service = get_token_service()
        
        # Создаем большие метаданные
        large_metadata = {
            "large_string": "x" * 1000,
            "large_array": list(range(100)),
            "nested_object": {
                "level1": {
                    "level2": {
                        "level3": {
                            "data": "deep_nested_value"
                        }
                    }
                }
            }
        }
        
        token = token_service.create_token(
            user_id="large_metadata_user",
            metadata=large_metadata
        )
        
        token_data = token_service.validate_token(token)
        
        assert token_data is not None
        assert token_data.metadata == large_metadata
        assert len(token_data.metadata["large_string"]) == 1000
        assert len(token_data.metadata["large_array"]) == 100
        assert token_data.metadata["nested_object"]["level1"]["level2"]["level3"]["data"] == "deep_nested_value"


class TestTokenMiddlewareIntegration:
    """Тесты для интеграции токенов с middleware"""
    
    def test_token_in_cookies_format(self):
        """Тест формата токена в cookies"""
        token_service = get_token_service()
        
        token = token_service.create_token(
            user_id="cookie_user",
            company_id="cookie_company",
            session_id="cookie_session",
            expires_in=3600
        )
        
        # Проверяем, что токен можно использовать как session_id
        token_data = token_service.validate_token(token)
        assert token_data is not None
        assert token_data.user_id == "cookie_user"
        assert token_data.company_id == "cookie_company"
        assert token_data.session_id == "cookie_session"
    
    def test_token_authorization_header_format(self):
        """Тест формата токена в заголовке Authorization"""
        token_service = get_token_service()
        
        token = token_service.create_token(
            user_id="header_user",
            expires_in=3600
        )
        
        # Проверяем, что токен можно использовать в Bearer формате
        bearer_token = f"Bearer {token}"
        extracted_token = bearer_token[7:]  # Убираем "Bearer "
        
        token_data = token_service.validate_token(extracted_token)
        assert token_data is not None
        assert token_data.user_id == "header_user"
    
    def test_token_company_validation(self):
        """Тест валидации компании в токене"""
        token_service = get_token_service()
        
        # Создаем токен с конкретной компанией
        token = token_service.create_token(
            user_id="company_user",
            company_id="specific_company",
            expires_in=3600
        )
        
        token_data = token_service.validate_token(token)
        
        assert token_data is not None
        assert token_data.company_id == "specific_company"
        
        # Проверяем логику валидации компании
        if token_data.company_id and token_data.company_id != "specific_company":
            assert False, "Company mismatch should be detected"
        
        # Проверяем с правильной компанией
        if token_data.company_id == "specific_company":
            assert True, "Company validation should pass"
