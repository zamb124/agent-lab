"""
Тесты для единой системы токенов
"""
import pytest
from datetime import datetime, timezone, timedelta

from core.utils.tokens import TokenService, TokenData, TokenType, get_token_service


class TestTokenService:
    """Тесты для TokenService"""
    
    @pytest.fixture
    def token_service(self):
        """Фикстура для TokenService"""
        return TokenService()
    
    def test_create_token(self, token_service):
        """Тест создания JWT токена"""
        user_id = "test_user_123"
        company_id = "test_company_456"
        session_id = "test_session_789"
        roles = ["admin", "user"]
        
        token = token_service.create_token(
            user_id=user_id,
            company_id=company_id,
            roles=roles,
            session_id=session_id,
            expires_in=3600,
            metadata={"test": "data"}
        )
        
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 50
        
        token_data = token_service.validate_token(token)
        assert token_data is not None
        assert token_data.user_id == user_id
        assert token_data.company_id == company_id
        assert token_data.roles == roles
        assert token_data.session_id == session_id
        assert token_data.metadata["test"] == "data"
        assert token_data.token_type == TokenType.SESSION
    
    def test_create_token_minimal(self, token_service):
        """Тест создания токена с минимальными параметрами"""
        user_id = "test_user_123"
        
        token = token_service.create_token(user_id=user_id)
        
        assert token is not None
        
        token_data = token_service.validate_token(token)
        assert token_data is not None
        assert token_data.user_id == user_id
        assert token_data.company_id == ""
        assert token_data.roles == []
        assert token_data.session_id is None
    
    def test_create_api_token(self, token_service):
        """Тест создания API токена"""
        token = token_service.create_api_token(
            user_id="api_user",
            company_id="api_company",
            roles=["api_access"]
        )
        
        token_data = token_service.validate_token(token)
        assert token_data is not None
        assert token_data.token_type == TokenType.API
        assert token_data.roles == ["api_access"]
    
    def test_validate_token_success(self, token_service):
        """Тест успешной валидации токена"""
        user_id = "test_user_123"
        token = token_service.create_token(user_id=user_id)
        
        token_data = token_service.validate_token(token)
        
        assert token_data is not None
        assert token_data.user_id == user_id
        assert isinstance(token_data.iat, datetime)
        assert isinstance(token_data.exp, datetime)
        assert token_data.exp > token_data.iat
    
    def test_validate_token_expired(self, token_service):
        """Тест валидации истекшего токена"""
        user_id = "test_user_123"
        
        token = token_service.create_token(
            user_id=user_id,
            expires_in=1
        )
        
        import time
        time.sleep(2)
        
        token_data = token_service.validate_token(token)
        assert token_data is None
    
    def test_validate_token_invalid(self, token_service):
        """Тест валидации недействительного токена"""
        invalid_token = "invalid.token.here"
        
        token_data = token_service.validate_token(invalid_token)
        assert token_data is None
    
    def test_validate_token_empty(self, token_service):
        """Тест валидации пустого токена"""
        token_data = token_service.validate_token("")
        assert token_data is None
        
        token_data = token_service.validate_token(None)
        assert token_data is None
    
    def test_token_expiration_time(self, token_service):
        """Тест времени истечения токена"""
        user_id = "test_user_123"
        expires_in = 3600
        
        token = token_service.create_token(
            user_id=user_id,
            expires_in=expires_in
        )
        
        token_data = token_service.validate_token(token)
        
        expected_exp = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        time_diff = abs((token_data.exp - expected_exp).total_seconds())
        assert time_diff < 5
    
    def test_token_metadata(self, token_service):
        """Тест метаданных токена"""
        user_id = "test_user_123"
        metadata = {
            "provider": "google",
            "user_name": "Test User",
            "custom_field": "custom_value"
        }
        
        token = token_service.create_token(
            user_id=user_id,
            metadata=metadata
        )
        
        token_data = token_service.validate_token(token)
        
        assert token_data.metadata == metadata
        assert token_data.metadata["provider"] == "google"
    
    def test_default_expiration(self, token_service):
        """Тест времени истечения по умолчанию (7 дней)"""
        user_id = "test_user_123"
        
        token = token_service.create_token(user_id=user_id)
        
        token_data = token_service.validate_token(token)
        
        expected_exp = datetime.now(timezone.utc) + timedelta(days=7)
        time_diff = abs((token_data.exp - expected_exp).total_seconds())
        assert time_diff < 60


class TestTokenData:
    """Тесты для модели TokenData"""
    
    def test_token_data_creation(self):
        """Тест создания TokenData"""
        now = datetime.now(timezone.utc)
        exp = now + timedelta(hours=1)
        
        token_data = TokenData(
            user_id="test_user",
            company_id="test_company",
            roles=["admin"],
            session_id="test_session",
            iat=now,
            exp=exp,
            metadata={"test": "data"}
        )
        
        assert token_data.user_id == "test_user"
        assert token_data.company_id == "test_company"
        assert token_data.roles == ["admin"]
        assert token_data.session_id == "test_session"
        assert token_data.iat == now
        assert token_data.exp == exp
        assert token_data.metadata == {"test": "data"}
        assert token_data.token_type == TokenType.SESSION
    
    def test_token_data_minimal(self):
        """Тест создания TokenData с минимальными параметрами"""
        exp = datetime.now(timezone.utc) + timedelta(hours=1)
        
        token_data = TokenData(
            user_id="test_user",
            company_id="",
            exp=exp
        )
        
        assert token_data.user_id == "test_user"
        assert token_data.company_id == ""
        assert token_data.roles == []
        assert token_data.session_id is None
        assert token_data.exp == exp
        assert token_data.metadata == {}


class TestGetTokenService:
    """Тесты для функции get_token_service"""
    
    def test_get_token_service_singleton(self):
        """Тест что get_token_service возвращает синглтон"""
        service1 = get_token_service()
        service2 = get_token_service()
        
        assert service1 is service2
        assert isinstance(service1, TokenService)
    
    def test_get_token_service_initialization(self):
        """Тест инициализации сервиса"""
        service = get_token_service()
        
        assert service.secret_key is not None
        assert service.algorithm == "HS256"


class TestTokenIntegration:
    """Интеграционные тесты для системы токенов"""
    
    @pytest.fixture
    def token_service(self):
        return get_token_service()
    
    def test_token_roundtrip(self, token_service):
        """Тест полного цикла создания и валидации токена"""
        user_id = "integration_test_user"
        company_id = "integration_test_company"
        session_id = "integration_test_session"
        roles = ["admin", "user"]
        metadata = {
            "test_type": "integration",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        token = token_service.create_token(
            user_id=user_id,
            company_id=company_id,
            roles=roles,
            session_id=session_id,
            expires_in=7200,
            metadata=metadata
        )
        
        token_data = token_service.validate_token(token)
        
        assert token_data is not None
        assert token_data.user_id == user_id
        assert token_data.company_id == company_id
        assert token_data.roles == roles
        assert token_data.session_id == session_id
        assert token_data.metadata == metadata
        
        assert isinstance(token_data.iat, datetime)
        assert isinstance(token_data.exp, datetime)
        assert token_data.exp > token_data.iat
    
    def test_multiple_tokens_different_users(self, token_service):
        """Тест создания токенов для разных пользователей"""
        users = [
            {"user_id": "user1", "company_id": "company1", "roles": ["admin"]},
            {"user_id": "user2", "company_id": "company2", "roles": ["user"]},
            {"user_id": "user3", "company_id": "company1", "roles": ["user"]},
        ]
        
        tokens = []
        for user_data in users:
            token = token_service.create_token(**user_data)
            tokens.append(token)
        
        assert len(set(tokens)) == len(tokens)
        
        for i, user_data in enumerate(users):
            token_data = token_service.validate_token(tokens[i])
            assert token_data is not None
            assert token_data.user_id == user_data["user_id"]
            assert token_data.company_id == user_data["company_id"]
            assert token_data.roles == user_data["roles"]
    
    def test_token_with_special_characters(self, token_service):
        """Тест токена с специальными символами в метаданных"""
        user_id = "user_with_special_chars"
        metadata = {
            "unicode": "тест с кириллицей",
            "special_chars": "!@#$%^&*()",
            "emoji": "🚀🎉✨",
            "json_like": '{"nested": {"value": 123}}'
        }
        
        token = token_service.create_token(
            user_id=user_id,
            metadata=metadata
        )
        
        token_data = token_service.validate_token(token)
        
        assert token_data is not None
        assert token_data.user_id == user_id
        assert token_data.metadata == metadata
