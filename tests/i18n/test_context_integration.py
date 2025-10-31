"""
Тесты интеграции системы переводов с Context и AuthMiddleware
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi import Request

from app.models.context_models import Context
from app.models.i18n_models import Language
from app.identity.models import User, Company, AuthProvider, UserStatus
from app.middleware.auth import AuthMiddleware


class TestContextLanguageIntegration:
    """Тесты интеграции языка в Context"""
    
    def test_context_with_default_language(self):
        """Проверяем создание Context с языком по умолчанию"""
        user = User(
            user_id="test_user",
            provider=AuthProvider.YANDEX,
            provider_user_id="123",
            email="test@example.com",
            name="Test User",
            status=UserStatus.ACTIVE,
            groups=["user"],
            companies={}
        )
        
        company = Company(
            company_id="test_company",
            name="Test Company",
            subdomain="test",
            status="active"
        )
        
        context = Context(
            user=user,
            platform="test",
            active_company=company,
            user_companies=[company]
        )
        
        # По умолчанию должен быть русский
        assert context.language == Language.RU
    
    def test_context_with_custom_language(self):
        """Проверяем создание Context с заданным языком"""
        user = User(
            user_id="test_user",
            provider=AuthProvider.YANDEX,
            provider_user_id="123",
            email="test@example.com",
            name="Test User",
            status=UserStatus.ACTIVE,
            groups=["user"],
            companies={}
        )
        
        company = Company(
            company_id="test_company",
            name="Test Company",
            subdomain="test",
            status="active"
        )
        
        context = Context(
            user=user,
            platform="test",
            active_company=company,
            user_companies=[company],
            language=Language.EN
        )
        
        assert context.language == Language.EN
    
    def test_context_serialization_with_language(self):
        """Проверяем сериализацию Context с языком"""
        user = User(
            user_id="test_user",
            provider=AuthProvider.YANDEX,
            provider_user_id="123",
            email="test@example.com",
            name="Test User",
            status=UserStatus.ACTIVE,
            groups=["user"],
            companies={}
        )
        
        company = Company(
            company_id="test_company",
            name="Test Company", 
            subdomain="test",
            status="active"
        )
        
        context = Context(
            user=user,
            platform="test",
            active_company=company,
            user_companies=[company],
            language=Language.EN
        )
        
        # Проверяем сериализацию/десериализацию
        context_dict = context.model_dump()
        restored_context = Context.model_validate(context_dict)
        
        assert restored_context.language == Language.EN


class TestAuthMiddlewareLanguageDetection:
    """Тесты определения языка в AuthMiddleware"""
    
    def setup_method(self):
        """Подготовка к каждому тесту"""
        # Создаем экземпляр middleware без инициализации app
        self.middleware = AuthMiddleware(app=Mock())
        self.middleware.storage = Mock()
    
    def test_detect_user_language_from_accept_language_header(self):
        """Проверяем определение языка из заголовка Accept-Language (HTMX)"""
        # Мокаем request с заголовком Accept-Language
        request = Mock(spec=Request)
        request.headers.get.side_effect = lambda key, default='': {
            'Accept-Language': 'en',
            'accept-language': '',
            'language': ''
        }.get(key, default)
        request.cookies.get.return_value = None
        
        language = self.middleware._detect_user_language(request)
        assert language == Language.EN
    
    def test_detect_user_language_from_cookie(self):
        """Проверяем определение языка из cookie"""
        request = Mock(spec=Request)
        request.headers.get.side_effect = lambda key, default='': {
            'Accept-Language': '',
            'accept-language': ''
        }.get(key, default)
        request.cookies.get.side_effect = lambda key, default=None: {
            'language': 'en'
        }.get(key, default)
        
        language = self.middleware._detect_user_language(request)
        assert language == Language.EN
    
    def test_detect_user_language_from_browser_accept_language(self):
        """Проверяем определение языка из браузерного заголовка accept-language"""
        request = Mock(spec=Request)
        request.headers.get.side_effect = lambda key, default='': {
            'Accept-Language': '',
            'accept-language': 'en-US,en;q=0.9,ru;q=0.8'
        }.get(key, default)
        request.cookies.get.return_value = None
        
        language = self.middleware._detect_user_language(request)
        assert language == Language.EN
    
    def test_detect_user_language_browser_russian_priority(self):
        """Проверяем приоритет русского языка в браузерном заголовке"""
        request = Mock(spec=Request)
        request.headers.get.side_effect = lambda key, default='': {
            'Accept-Language': '',
            'accept-language': 'ru-RU,ru;q=0.9,en;q=0.8'
        }.get(key, default)
        request.cookies.get.return_value = None
        
        language = self.middleware._detect_user_language(request)
        assert language == Language.RU
    
    def test_detect_user_language_fallback_to_default(self):
        """Проверяем fallback на язык по умолчанию"""
        request = Mock(spec=Request)
        request.headers.get.side_effect = lambda key, default='': {
            'Accept-Language': '',
            'accept-language': 'fr-FR,fr;q=0.9'  # Неподдерживаемый язык
        }.get(key, default)
        request.cookies.get.return_value = None
        
        language = self.middleware._detect_user_language(request)
        assert language == Language.RU
    
    def test_detect_user_language_invalid_cookie(self):
        """Проверяем обработку некорректного cookie"""
        request = Mock(spec=Request)
        request.headers.get.side_effect = lambda key, default='': {
            'Accept-Language': '',
            'accept-language': ''
        }.get(key, default)
        request.cookies.get.side_effect = lambda key, default=None: {
            'language': 'invalid_lang'
        }.get(key, default)
        
        language = self.middleware._detect_user_language(request)
        assert language == Language.RU
    
    def test_detect_user_language_priority_order(self):
        """Проверяем порядок приоритетов при определении языка"""
        # HTMX заголовок имеет наивысший приоритет
        request = Mock(spec=Request)
        request.headers.get.side_effect = lambda key, default='': {
            'Accept-Language': 'en',  # Высший приоритет
            'accept-language': 'es-ES,es;q=0.9'
        }.get(key, default)
        request.cookies.get.side_effect = lambda key, default=None: {
            'language': 'en'
        }.get(key, default)
        
        language = self.middleware._detect_user_language(request)
        assert language == Language.EN  # HTMX заголовок побеждает


class TestAuthMiddlewareContextCreation:
    """Тесты создания Context с языком в AuthMiddleware"""
    
    def setup_method(self):
        """Подготовка к каждому тесту"""
        self.middleware = AuthMiddleware(app=Mock())
        self.middleware.storage = Mock()
        
        # Общие моки для тестов
        self.test_company = Company(
            company_id="test_company",
            name="Test Company",
            subdomain="test", 
            status="active"
        )
    
    @patch.object(AuthMiddleware, '_detect_user_language')
    @pytest.mark.asyncio
    async def test_create_telegram_context_with_language(self, mock_detect_lang):
        """Проверяем создание Telegram контекста с языком"""
        mock_detect_lang.return_value = Language.EN
        
        # Мокаем request с Telegram данными
        request = Mock(spec=Request)
        request.body = AsyncMock(return_value=b'{"message": {"from": {"id": 123, "username": "testuser", "first_name": "Test", "last_name": "User"}}}')
        
        context = await self.middleware._create_telegram_context(request, self.test_company)
        
        assert context.language == Language.EN
        assert context.platform == "telegram"
        mock_detect_lang.assert_called_once_with(request)
    
    @patch.object(AuthMiddleware, '_detect_user_language')  
    @patch.object(AuthMiddleware, '_get_user_companies')
    @pytest.mark.asyncio
    async def test_create_api_context_with_language(self, mock_get_companies, mock_detect_lang, migrated_db):
        """Проверяем создание API контекста с языком"""
        mock_detect_lang.return_value = Language.EN
        mock_get_companies.return_value = [self.test_company]
        
        # Мокаем пользователя
        test_user = User(
            user_id="test_user",
            provider=AuthProvider.YANDEX,
            provider_user_id="123",
            email="test@example.com",
            name="Test User",
            status=UserStatus.ACTIVE,
            groups=["user"],
            companies={"test_company": ["user"]},
            active_company_id="test_company"
        )
        
        # Мокаем request с JWT токеном
        request = Mock(spec=Request)
        request.cookies.get.side_effect = lambda key, default=None: {
            "auth_token": "valid.jwt.token.here"
        }.get(key, default)
        request.headers.get.return_value = ""

        with patch('app.middleware.auth.get_token_service') as mock_token_service:
            # Мокаем валидацию токена
            mock_token = Mock()
            mock_token.user_id = "test_user"
            mock_token.session_id = "api_session_456"
            mock_token.company_id = "test_company"  # Должен совпадать с requested_company
            mock_token_service.return_value.validate_token.return_value = mock_token

            with patch.object(self.middleware, '_get_user_by_id', new_callable=AsyncMock) as mock_get_user:
                mock_get_user.return_value = test_user

                with patch.object(self.middleware, '_get_user_companies', new_callable=AsyncMock) as mock_get_companies:
                    mock_get_companies.return_value = [self.test_company]

                    with patch.object(self.middleware, '_update_user_active_company', new_callable=AsyncMock):
                        context = await self.middleware._create_api_context(request, self.test_company)
        
        assert context.language == Language.EN
        assert context.platform == "api"
        mock_detect_lang.assert_called_once_with(request)
    
    @patch.object(AuthMiddleware, '_detect_user_language')
    @pytest.mark.asyncio
    async def test_create_anonymous_context_with_language(self, mock_detect_lang):
        """Проверяем создание анонимного контекста с языком"""
        mock_detect_lang.return_value = Language.EN
        
        request = Mock(spec=Request)
        
        context = await self.middleware._create_anonymous_context(request, self.test_company)
        
        assert context.language == Language.EN
        assert context.platform == "api"
        assert context.user.user_id == "anonymous"
        mock_detect_lang.assert_called_once_with(request)
    
    @patch.object(AuthMiddleware, '_detect_user_language')
    @patch.object(AuthMiddleware, '_get_user_companies')
    @pytest.mark.asyncio
    async def test_create_frontend_context_with_language(self, mock_get_companies, mock_detect_lang, migrated_db):
        """Проверяем создание frontend контекста с языком"""
        mock_detect_lang.return_value = Language.RU
        mock_get_companies.return_value = [self.test_company]
        
        # Мокаем пользователя
        test_user = User(
            user_id="frontend_user",
            provider=AuthProvider.YANDEX,
            provider_user_id="456",
            email="frontend@example.com", 
            name="Frontend User",
            status=UserStatus.ACTIVE,
            groups=["user"],
            companies={"test_company": ["user"]},
            active_company_id="test_company"
        )
        
        # Мокаем request с JWT токеном
        request = Mock(spec=Request)
        request.cookies.get.side_effect = lambda key, default=None: {
            "auth_token": "valid.jwt.token.here"
        }.get(key, default)
        request.cookies.keys.return_value = ["auth_token"]

        with patch('app.middleware.auth.get_token_service') as mock_token_service:
            # Мокаем валидацию токена
            mock_token = Mock()
            mock_token.user_id = "frontend_user"
            mock_token.session_id = "frontend_session_123"
            mock_token_service.return_value.validate_token.return_value = mock_token

            with patch.object(self.middleware, '_get_user_by_id', new_callable=AsyncMock) as mock_get_user:
                mock_get_user.return_value = test_user

                with patch.object(self.middleware, '_get_user_companies', new_callable=AsyncMock) as mock_get_companies:
                    mock_get_companies.return_value = [self.test_company]

                    with patch.object(self.middleware, '_update_user_active_company', new_callable=AsyncMock):
                        context = await self.middleware._create_frontend_context(request, self.test_company, has_subdomain=True)
        
        assert context.language == Language.RU
        assert context.platform == "frontend"
        mock_detect_lang.assert_called_once_with(request)


class TestLanguageDetectionEdgeCases:
    """Тесты граничных случаев определения языка"""
    
    def setup_method(self):
        """Подготовка к каждому тесту"""
        self.middleware = AuthMiddleware(app=Mock())
        self.middleware.storage = Mock()
    
    def test_detect_language_empty_headers(self):
        """Проверяем обработку пустых заголовков"""
        request = Mock(spec=Request)
        request.headers.get.return_value = ''
        request.cookies.get.return_value = None
        
        language = self.middleware._detect_user_language(request)
        assert language == Language.RU
    
    def test_detect_language_malformed_accept_language(self):
        """Проверяем обработку некорректного заголовка accept-language"""
        request = Mock(spec=Request)
        request.headers.get.side_effect = lambda key, default='': {
            'Accept-Language': '',
            'accept-language': 'malformed;header;without;proper;format'
        }.get(key, default)
        request.cookies.get.return_value = None
        
        language = self.middleware._detect_user_language(request)
        assert language == Language.RU
    
    def test_detect_language_case_insensitive(self):
        """Проверяем нечувствительность к регистру"""
        request = Mock(spec=Request)
        request.headers.get.side_effect = lambda key, default='': {
            'Accept-Language': 'EN',  # Верхний регистр
            'accept-language': ''
        }.get(key, default)
        request.cookies.get.return_value = None
        
        language = self.middleware._detect_user_language(request)
        assert language == Language.EN
    
    def test_detect_language_cookie_case_insensitive(self):
        """Проверяем нечувствительность к регистру в cookies"""
        request = Mock(spec=Request)
        request.headers.get.side_effect = lambda key, default='': {
            'Accept-Language': '',
            'accept-language': ''
        }.get(key, default)
        request.cookies.get.side_effect = lambda key, default=None: {
            'language': 'EN'  # Верхний регистр
        }.get(key, default)
        
        language = self.middleware._detect_user_language(request)
        assert language == Language.EN


# Импорт asyncio для async функций в тестах
