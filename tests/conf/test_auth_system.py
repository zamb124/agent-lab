"""
Тесты системы авторизации.
"""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch

from app.identity.models import (
    AuthProvider, User, AuthSession, ProviderUserInfo, 
    AuthRequest, UserStatus
)
from app.identity.base_provider import BaseAuthProvider
from app.identity.providers.yandex import YandexProvider
from app.identity.auth_service import AuthService
from app.core.config import AuthProviderConfig


class TestAuthModels:
    """Тесты моделей авторизации"""
    
    def test_user_model(self):
        """Тест модели пользователя"""
        user = User(
            user_id="test_user_123",
            name="Тест Пользователь"
        )
        
        assert user.user_id == "test_user_123"
        assert user.name == "Тест Пользователь"
        assert user.status == UserStatus.ACTIVE
        assert user.created_at is not None
        assert user.updated_at is not None
        assert user.groups == ["user"]
    
    def test_auth_session_model(self):
        """Тест модели сессии авторизации"""
        session = AuthSession(
            session_id="session_123",
            user_id="user_123",
            provider=AuthProvider.YANDEX,
            access_token="access_token_123",
            refresh_token="refresh_token_123"
        )
        
        assert session.session_id == "session_123"
        assert session.user_id == "user_123"
        assert session.provider == AuthProvider.YANDEX
        assert session.access_token == "access_token_123"
        assert session.created_at is not None
        assert session.last_activity is not None
    
    def test_provider_user_info_model(self):
        """Тест модели информации о пользователе от провайдера"""
        user_info = ProviderUserInfo(
            provider_user_id="yandex_456",
            email="user@yandex.ru",
            name="Имя Пользователя",
            avatar_url="https://avatars.yandex.net/get-yapic/123/islands-200",
            raw_data={"id": "yandex_456", "login": "user"}
        )
        
        assert user_info.provider_user_id == "yandex_456"
        assert user_info.email == "user@yandex.ru"
        assert user_info.name == "Имя Пользователя"
        assert user_info.raw_data["id"] == "yandex_456"
    
    def test_auth_request_model(self):
        """Тест модели запроса авторизации"""
        auth_request = AuthRequest(
            provider=AuthProvider.YANDEX,
            code="auth_code_123",
            state="csrf_state_456",
            redirect_uri="http://localhost:8001/auth/callback"
        )
        
        assert auth_request.provider == AuthProvider.YANDEX
        assert auth_request.code == "auth_code_123"
        assert auth_request.state == "csrf_state_456"
        assert auth_request.redirect_uri == "http://localhost:8001/auth/callback"


class TestYandexProvider:
    """Тесты Yandex провайдера"""
    
    def test_yandex_provider_initialization(self):
        """Тест инициализации Yandex провайдера"""
        config = AuthProviderConfig(
            client_id="test-client-id",
            client_secret="test-secret",
            auth_url="https://oauth.yandex.ru/authorize",
            token_url="https://oauth.yandex.ru/token",
            userinfo_url="https://login.yandex.ru/info",
            scope="login:email login:avatar",
            enabled=True
        )
        
        provider = YandexProvider(config)
        
        assert provider.provider_name == AuthProvider.YANDEX
        assert provider.client_id == "test-client-id"
        assert provider.client_secret == "test-secret"
        assert provider.auth_url == "https://oauth.yandex.ru/authorize"
        assert provider.validate_config()
    
    def test_yandex_authorization_url(self):
        """Тест генерации URL авторизации Yandex"""
        config = AuthProviderConfig(
            client_id="test-client-id",
            client_secret="test-secret",
            auth_url="https://oauth.yandex.ru/authorize",
            token_url="https://oauth.yandex.ru/token",
            userinfo_url="https://login.yandex.ru/info",
            scope="login:email login:avatar",
            enabled=True
        )
        
        provider = YandexProvider(config)
        
        auth_url = provider.get_authorization_url(
            state="test-state",
            redirect_uri="http://localhost:8001/auth/callback"
        )
        
        # Проверяем что URL содержит нужные параметры
        assert "oauth.yandex.ru/authorize" in auth_url
        assert "client_id=test-client-id" in auth_url
        assert "redirect_uri=http%3A%2F%2Flocalhost%3A8001%2Fauth%2Fcallback" in auth_url
        assert "state=test-state" in auth_url
        assert "response_type=code" in auth_url
        assert "force_confirm=yes" in auth_url
    
    @pytest.mark.asyncio
    async def test_yandex_token_exchange_success(self):
        """Тест успешного обмена кода на токен"""
        config = AuthProviderConfig(
            client_id="test-client-id",
            client_secret="test-secret",
            auth_url="https://oauth.yandex.ru/authorize",
            token_url="https://oauth.yandex.ru/token",
            userinfo_url="https://login.yandex.ru/info",
            scope="login:email login:avatar",
            enabled=True
        )
        
        provider = YandexProvider(config)
        
        # Мокаем HTTP ответ от Yandex
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        # json() должен возвращать обычный dict, не awaitable
        def mock_json():
            return {
                "access_token": "test_access_token",
                "refresh_token": "test_refresh_token",
                "token_type": "bearer"
            }
        mock_response.json = mock_json
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
            
            access_token, refresh_token = await provider.exchange_code_for_token(
                code="test_code",
                redirect_uri="http://localhost:8001/auth/callback"
            )
            
            assert access_token == "test_access_token"
            assert refresh_token == "test_refresh_token"
    
    @pytest.mark.asyncio
    async def test_yandex_get_user_info_success(self):
        """Тест получения информации о пользователе от Yandex"""
        config = AuthProviderConfig(
            client_id="test-client-id",
            client_secret="test-secret",
            auth_url="https://oauth.yandex.ru/authorize",
            token_url="https://oauth.yandex.ru/token",
            userinfo_url="https://login.yandex.ru/info",
            scope="login:email login:avatar",
            enabled=True
        )
        
        provider = YandexProvider(config)
        
        # Мокаем ответ от Yandex API
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        # json() должен возвращать обычный dict, не awaitable
        def mock_json():
            return {
                "id": "12345",
                "default_email": "test@yandex.ru",
                "display_name": "Тест Пользователь",
                "first_name": "Тест",
                "last_name": "Пользователь",
                "default_avatar_id": "avatar123"
            }
        mock_response.json = mock_json
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            user_info = await provider.get_user_info("test_access_token")
            
            assert user_info.provider_user_id == "12345"
            assert user_info.email == "test@yandex.ru"
            assert user_info.name == "Тест Пользователь"
            assert user_info.avatar_url == "https://avatars.yandex.net/get-yapic/avatar123/islands-200"
            assert user_info.raw_data["id"] == "12345"


@pytest.mark.asyncio
class TestAuthService:
    """Тесты сервиса авторизации"""
    
    async def test_auth_service_initialization_with_config(self):
        """Тест инициализации AuthService"""
        # Создаем тестовую конфигурацию
        from app.core.config import AuthConfig, AuthProviderConfig
        
        test_auth_config = AuthConfig(
            enabled=True,
            secret_key="test-secret",
            session_timeout=3600,
            providers={
                "yandex": AuthProviderConfig(
                    client_id="test-client-id",
                    client_secret="test-secret",
                    auth_url="https://oauth.yandex.ru/authorize",
                    token_url="https://oauth.yandex.ru/token",
                    userinfo_url="https://login.yandex.ru/info",
                    scope="login:email",
                    enabled=True
                )
            }
        )
        
        # Создаем AuthService с тестовой конфигурацией
        # Мокаем settings
        with patch('app.identity.auth_service.settings') as mock_settings:
            mock_settings.auth = test_auth_config
            
            auth_service = AuthService()
            
            # Проверяем инициализацию
            providers = auth_service.get_available_providers()
            assert AuthProvider.YANDEX in providers
            
            yandex_provider = auth_service.get_provider(AuthProvider.YANDEX)
            assert yandex_provider is not None
            assert yandex_provider.client_id == "test-client-id"
    
    async def test_start_auth_flow(self):
        """Тест начала процесса авторизации"""
        # Создаем тестовый AuthService
        from app.core.config import AuthConfig, AuthProviderConfig
        
        test_auth_config = AuthConfig(
            enabled=True,
            providers={
                "yandex": AuthProviderConfig(
                    client_id="test-client-id",
                    client_secret="test-secret",
                    auth_url="https://oauth.yandex.ru/authorize",
                    token_url="https://oauth.yandex.ru/token",
                    userinfo_url="https://login.yandex.ru/info",
                    scope="login:email",
                    enabled=True
                )
            }
        )
        
        with patch('app.identity.auth_service.settings') as mock_settings:
            mock_settings.auth = test_auth_config
            
            auth_service = AuthService()
            
            # Мокаем Storage
            auth_service.storage = AsyncMock()
            auth_service.storage.set = AsyncMock()
            
            # Тестируем создание URL авторизации
            auth_url = await auth_service.start_auth(
                AuthProvider.YANDEX,
                "http://localhost:8001/auth/callback"
            )
            
            # Проверяем URL
            assert "oauth.yandex.ru/authorize" in auth_url
            assert "client_id=test-client-id" in auth_url
            assert "redirect_uri" in auth_url
            assert "state=" in auth_url
            
            # Проверяем что state сохранен
            auth_service.storage.set.assert_called_once()
    
    async def test_complete_auth_flow_success(self):
        """Тест успешного завершения авторизации"""
        from app.core.config import AuthConfig, AuthProviderConfig
        
        test_auth_config = AuthConfig(
            enabled=True,
            session_timeout=3600,
            providers={
                "yandex": AuthProviderConfig(
                    client_id="test-client-id",
                    client_secret="test-secret",
                    auth_url="https://oauth.yandex.ru/authorize",
                    token_url="https://oauth.yandex.ru/token",
                    userinfo_url="https://login.yandex.ru/info",
                    scope="login:email",
                    enabled=True
                )
            }
        )
        
        with patch('app.identity.auth_service.settings') as mock_settings:
            mock_settings.auth = test_auth_config
            
            auth_service = AuthService()
            
            # Мокаем Storage
            auth_service.storage = AsyncMock()
            auth_service.storage.set = AsyncMock(return_value=True)
            auth_service.storage.delete = AsyncMock(return_value=True)
            
            # Настраиваем последовательность вызовов get()
            auth_service.storage.get.side_effect = [
                # 1. Проверка кеша OAuth кода (первый запрос - кеша нет)
                None,
                # 2. Получение auth state
                json.dumps({
                    "provider": "yandex",
                    "redirect_uri": "http://localhost:8001/auth/callback",
                    "created_at": "2025-09-12T10:00:00Z"
                }),
            ]
            
            # Мокаем методы работы с пользователями
            from app.identity.models import User, AuthSession
            from datetime import datetime, timezone
            
            test_user = User(
                user_id="user_123",
                name="Тест Пользователь",
                companies={},
                active_company_id=""
            )
            
            test_session = AuthSession(
                session_id="session_123",
                user_id="user_123",
                provider=AuthProvider.YANDEX,
                access_token="access_token",
                refresh_token="refresh_token",
                expires_at=datetime.now(timezone.utc).isoformat()
            )
            
            auth_service._get_or_create_user = AsyncMock(return_value=test_user)
            auth_service._create_session = AsyncMock(return_value=test_session)
            auth_service._get_auth_state = AsyncMock(return_value={
                "provider": "yandex",
                "redirect_uri": "http://localhost:8001/auth/callback"
            })
            auth_service._cleanup_auth_state = AsyncMock()
            
            # Мокаем провайдер
            mock_provider = AsyncMock()
            mock_provider.exchange_code_for_token.return_value = ("access_token", "refresh_token")
            mock_provider.get_user_info.return_value = ProviderUserInfo(
                provider_user_id="yandex_123",
                email="test@yandex.ru",
                name="Тест Пользователь",
                avatar_url="https://example.com/avatar.jpg"
            )
            
            auth_service._providers = {AuthProvider.YANDEX: mock_provider}
            
            # Тестируем завершение авторизации
            auth_request = AuthRequest(
                provider=AuthProvider.YANDEX,
                code="test_code",
                state="test_state",
                redirect_uri="http://localhost:8001/auth/callback"
            )
            
            result = await auth_service.complete_auth(auth_request)
            
            # Проверяем результат
            assert result.success
            assert result.user is not None
            assert result.user.user_id == "user_123"
            assert result.user.name == "Тест Пользователь"
            assert result.session is not None
            assert result.session.session_id == "session_123"
            assert result.session.provider == AuthProvider.YANDEX
            assert result.session.access_token == "access_token"
    
    async def test_complete_auth_invalid_state(self):
        """Тест завершения авторизации с недействительным state"""
        from app.core.config import AuthConfig, AuthProviderConfig
        
        test_auth_config = AuthConfig(
            enabled=True,
            providers={
                "yandex": AuthProviderConfig(
                    client_id="test-client-id",
                    client_secret="test-secret",
                    auth_url="https://oauth.yandex.ru/authorize",
                    token_url="https://oauth.yandex.ru/token",
                    userinfo_url="https://login.yandex.ru/info",
                    scope="login:email",
                    enabled=True
                )
            }
        )
        
        with patch('app.identity.auth_service.settings') as mock_settings:
            mock_settings.auth = test_auth_config
            
            auth_service = AuthService()
            
            # Мокаем Storage - возвращаем None для недействительного state
            auth_service.storage = AsyncMock()
            auth_service.storage.get.return_value = None
            
            # Тестируем завершение авторизации с недействительным state
            auth_request = AuthRequest(
                provider=AuthProvider.YANDEX,
                code="test_code",
                state="invalid_state"
            )
            
            result = await auth_service.complete_auth(auth_request)
            
            # Проверяем что авторизация не удалась
            assert not result.success
            assert "Недействительный state" in result.error_message
            assert result.user is None
            assert result.session is None
    
    async def test_get_user_by_session(self):
        """Тест получения пользователя по сессии"""
        auth_service = AuthService()
        
        # Мокаем Storage
        auth_service.storage = AsyncMock()
        
        # Мокаем данные сессии
        test_session = AuthSession(
            session_id="test_session",
            user_id="test_user",
            provider=AuthProvider.YANDEX,
            access_token="token"
        )
        
        # Мокаем данные пользователя
        test_user = User(
            user_id="test_user",
            name="Тест Пользователь"
        )
        
        # Мокаем _get_session и _get_user напрямую
        auth_service._get_session = AsyncMock(return_value=test_session)
        auth_service._get_user = AsyncMock(return_value=test_user)
        
        # Тестируем получение пользователя
        user = await auth_service.get_user_by_session("test_session")
        
        assert user is not None
        assert user.user_id == "test_user"
        assert user.name == "Тест Пользователь"
    
    async def test_logout(self):
        """Тест завершения сессии"""
        auth_service = AuthService()
        
        # Мокаем Storage
        auth_service.storage = AsyncMock()
        auth_service.storage.delete = AsyncMock()
        
        # Тестируем logout
        result = await auth_service.logout("test_session")
        
        assert result
        auth_service.storage.delete.assert_called_once_with("auth_session:test_session")


class TestBaseProvider:
    """Тесты базового провайдера"""
    
    def test_base_provider_config_validation(self):
        """Тест валидации конфигурации провайдера"""
        # Корректная конфигурация
        valid_config = AuthProviderConfig(
            client_id="test-id",
            client_secret="test-secret",
            auth_url="https://example.com/auth",
            token_url="https://example.com/token",
            userinfo_url="https://example.com/userinfo",
            enabled=True
        )
        
        # Создаем тестовый провайдер
        class TestProvider(BaseAuthProvider):
            def get_authorization_url(self, state, redirect_uri):
                return "test_url"
            
            async def exchange_code_for_token(self, code, redirect_uri):
                return "token", None
            
            async def get_user_info(self, access_token):
                return ProviderUserInfo(
                    provider_user_id="123",
                    email="test@example.com",
                    name="Test User"
                )
        
        provider = TestProvider(AuthProvider.YANDEX, valid_config)
        assert provider.validate_config()
        
        # Некорректная конфигурация (отключена)
        invalid_config = AuthProviderConfig(
            client_id="test-id",
            client_secret="test-secret",
            auth_url="https://example.com/auth",
            token_url="https://example.com/token",
            userinfo_url="https://example.com/userinfo",
            enabled=False
        )
        
        provider_disabled = TestProvider(AuthProvider.YANDEX, invalid_config)
        assert not provider_disabled.validate_config()
        
        # Некорректная конфигурация (отсутствует client_id)
        incomplete_config = AuthProviderConfig(
            client_id=None,
            client_secret="test-secret",
            auth_url="https://example.com/auth",
            token_url="https://example.com/token",
            userinfo_url="https://example.com/userinfo",
            enabled=True
        )
        
        provider_incomplete = TestProvider(AuthProvider.YANDEX, incomplete_config)
        assert not provider_incomplete.validate_config()
    
    def test_build_auth_params(self):
        """Тест построения параметров авторизации"""
        config = AuthProviderConfig(
            client_id="test-client-id",
            client_secret="test-secret",
            auth_url="https://example.com/auth",
            token_url="https://example.com/token",
            userinfo_url="https://example.com/userinfo",
            scope="email profile",
            enabled=True
        )
        
        class TestProvider(BaseAuthProvider):
            def get_authorization_url(self, state, redirect_uri):
                return "test_url"
            
            async def exchange_code_for_token(self, code, redirect_uri):
                return "token", None
            
            async def get_user_info(self, access_token):
                return ProviderUserInfo(
                    provider_user_id="123",
                    email="test@example.com",
                    name="Test User"
                )
        
        provider = TestProvider(AuthProvider.YANDEX, config)
        
        params = provider._build_auth_params("test_state", "http://localhost/callback")
        
        assert params["client_id"] == "test-client-id"
        assert params["redirect_uri"] == "http://localhost/callback"
        assert params["scope"] == "email profile"
        assert params["state"] == "test_state"
        assert params["response_type"] == "code"
