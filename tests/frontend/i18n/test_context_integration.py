"""
Тесты интеграции системы переводов с Context и ContextFactory
"""

import pytest
from unittest.mock import Mock, AsyncMock
from fastapi import Request

from core.models.context_models import Context
from core.models.i18n_models import Language
from core.models import User, Company, AuthProvider, UserStatus
from core.middleware.auth.context_factory import ContextFactory


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


class TestContextFactoryLanguageDetection:
    """Тесты определения языка в ContextFactory"""
    
    def setup_method(self):
        """Подготовка к каждому тесту"""
        # Создаем mock контейнера
        mock_container = Mock()
        mock_container.user_repository = Mock()
        mock_container.company_repository = Mock()
        self.factory = ContextFactory(mock_container)
    
    def test_detect_user_language_from_accept_language_header(self):
        """Проверяем определение языка из заголовка Accept-Language (HTMX)"""
        request = Mock(spec=Request)
        request.headers.get.side_effect = lambda key, default='': {
            'Accept-Language': 'en',
            'accept-language': '',
        }.get(key, default)
        request.cookies.get.return_value = None
        
        language = self.factory._detect_language(request)
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
        
        language = self.factory._detect_language(request)
        assert language == Language.EN
    
    def test_detect_user_language_from_browser_accept_language(self):
        """Проверяем определение языка из браузерного заголовка accept-language"""
        request = Mock(spec=Request)
        request.headers.get.side_effect = lambda key, default='': {
            'Accept-Language': '',
            'accept-language': 'en-US,en;q=0.9,ru;q=0.8'
        }.get(key, default)
        request.cookies.get.return_value = None
        
        language = self.factory._detect_language(request)
        assert language == Language.EN
    
    def test_detect_user_language_browser_russian_priority(self):
        """Проверяем приоритет русского языка в браузерном заголовке"""
        request = Mock(spec=Request)
        request.headers.get.side_effect = lambda key, default='': {
            'Accept-Language': '',
            'accept-language': 'ru-RU,ru;q=0.9,en;q=0.8'
        }.get(key, default)
        request.cookies.get.return_value = None
        
        language = self.factory._detect_language(request)
        assert language == Language.RU
    
    def test_detect_user_language_fallback_to_default(self):
        """Проверяем fallback на язык по умолчанию"""
        request = Mock(spec=Request)
        request.headers.get.side_effect = lambda key, default='': {
            'Accept-Language': '',
            'accept-language': 'fr-FR,fr;q=0.9'  # Неподдерживаемый язык
        }.get(key, default)
        request.cookies.get.return_value = None
        
        language = self.factory._detect_language(request)
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
        
        language = self.factory._detect_language(request)
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
            'language': 'ru'
        }.get(key, default)
        
        language = self.factory._detect_language(request)
        assert language == Language.EN  # HTMX заголовок побеждает


class TestContextFactoryContextCreation:
    """Тесты создания Context с языком в ContextFactory"""
    
    def setup_method(self):
        """Подготовка к каждому тесту"""
        mock_container = Mock()
        mock_container.user_repository = AsyncMock()
        mock_container.company_repository = AsyncMock()
        self.factory = ContextFactory(mock_container)
        
        self.test_company = Company(
            company_id="test_company",
            name="Test Company",
            subdomain="test", 
            status="active"
        )
    
    @pytest.mark.asyncio
    async def test_create_anonymous_context_with_language(self):
        """Проверяем создание анонимного контекста с языком"""
        request = Mock(spec=Request)
        request.headers = Mock()
        request.headers.get = Mock(side_effect=lambda key, default='': {
            'host': 'localhost',
            'Accept-Language': 'en',
            'accept-language': ''
        }.get(key, default))
        request.cookies.get.return_value = None
        
        context = await self.factory.create(
            request=request,
            context_type="anonymous",
            company=self.test_company,
        )
        
        assert context.language == Language.EN
        assert context.platform == "anonymous"
        assert context.user.user_id == "anonymous"


class TestLanguageDetectionEdgeCases:
    """Тесты граничных случаев определения языка"""
    
    def setup_method(self):
        """Подготовка к каждому тесту"""
        mock_container = Mock()
        mock_container.user_repository = Mock()
        mock_container.company_repository = Mock()
        self.factory = ContextFactory(mock_container)
    
    def test_detect_language_empty_headers(self):
        """Проверяем обработку пустых заголовков"""
        request = Mock(spec=Request)
        request.headers.get.return_value = ''
        request.cookies.get.return_value = None
        
        language = self.factory._detect_language(request)
        assert language == Language.RU
    
    def test_detect_language_malformed_accept_language(self):
        """Проверяем обработку некорректного заголовка accept-language"""
        request = Mock(spec=Request)
        request.headers.get.side_effect = lambda key, default='': {
            'Accept-Language': '',
            'accept-language': 'malformed;header;without;proper;format'
        }.get(key, default)
        request.cookies.get.return_value = None
        
        language = self.factory._detect_language(request)
        assert language == Language.RU
    
    def test_detect_language_case_insensitive(self):
        """Проверяем нечувствительность к регистру"""
        request = Mock(spec=Request)
        request.headers.get.side_effect = lambda key, default='': {
            'Accept-Language': 'EN',  # Верхний регистр
            'accept-language': ''
        }.get(key, default)
        request.cookies.get.return_value = None
        
        language = self.factory._detect_language(request)
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
        
        language = self.factory._detect_language(request)
        assert language == Language.EN
