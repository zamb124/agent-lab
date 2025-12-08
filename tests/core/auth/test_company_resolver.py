"""
Тесты для CompanyResolver - определение компании из запроса.

Сценарии:
1. Только токен -> компания из токена (для API)
2. Токен + X-Company-Id (с доступом) -> компания из X-Company-Id
3. Токен + X-Company-Id (без доступа) -> 403
4. Токен + X-Company-Id (совпадают) -> компания из X-Company-Id
5. Субдомен без токена -> компания из субдомена
6. Local env - X-Company-Id без проверки доступа
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

from core.middleware.auth.company_resolver import CompanyResolver
from core.models.identity_models import Company, User
from core.utils.tokens import TokenData


def make_token_data(user_id: str, company_id: str) -> TokenData:
    """Создает TokenData с корректным exp"""
    return TokenData(
        user_id=user_id,
        company_id=company_id,
        exp=datetime.now(timezone.utc) + timedelta(hours=1),
    )


@pytest.fixture
def mock_container():
    """Мок контейнера с репозиториями"""
    container = MagicMock()
    container.company_repository = AsyncMock()
    container.user_repository = AsyncMock()
    container.subdomain_repository = AsyncMock()
    return container


@pytest.fixture
def company_ggg():
    """Компания ggg"""
    return Company(
        company_id="ggg",
        name="Company GGG",
        subdomain="ggg",
    )


@pytest.fixture
def company_zzz():
    """Компания zzz"""
    return Company(
        company_id="zzz",
        name="Company ZZZ",
        subdomain="zzz",
    )


@pytest.fixture
def user_with_both_companies():
    """Пользователь с доступом к ggg и zzz"""
    return User(
        user_id="user_123",
        name="Test User",
        companies={
            "ggg": ["admin"],
            "zzz": ["member"],
        },
        active_company_id="zzz",
    )


@pytest.fixture
def user_with_only_zzz():
    """Пользователь с доступом только к zzz"""
    return User(
        user_id="user_456",
        name="Test User 2",
        companies={
            "zzz": ["member"],
        },
        active_company_id="zzz",
    )


@pytest.fixture
def token_data_zzz():
    """Токен с компанией zzz"""
    return make_token_data(user_id="user_123", company_id="zzz")


@pytest.fixture
def mock_request():
    """Мок FastAPI Request"""
    request = MagicMock()
    request.headers = {}
    return request


def make_request(headers: dict = None, host: str = "localhost:8000"):
    """Создает мок запроса с заданными headers"""
    request = MagicMock()
    headers = headers or {}
    headers["host"] = host
    request.headers = MagicMock()
    request.headers.get = lambda key, default="": headers.get(key, default)
    return request


class TestCompanyResolverTokenOnly:
    """Тесты: только токен без X-Company-Id"""
    
    @pytest.mark.asyncio
    @pytest.mark.parametrize("context_type", ["api", "webhook"])
    async def test_api_request_with_token_returns_company_from_token(
        self, mock_container, company_zzz, token_data_zzz, context_type
    ):
        """API запрос с токеном -> компания из токена"""
        mock_container.company_repository.get.return_value = company_zzz
        
        resolver = CompanyResolver(mock_container)
        request = make_request()
        
        with patch("core.middleware.auth.company_resolver.settings") as mock_settings:
            mock_settings.server.env = "production"
            
            result = await resolver.resolve(
                request=request,
                token_data=token_data_zzz,
                context_type=context_type,
            )
        
        assert result == company_zzz
        mock_container.company_repository.get.assert_called_once_with("zzz")
    
    @pytest.mark.asyncio
    async def test_api_token_company_not_found_raises_403(
        self, mock_container, token_data_zzz
    ):
        """API токен с несуществующей компанией -> 403"""
        mock_container.company_repository.get.return_value = None
        
        resolver = CompanyResolver(mock_container)
        request = make_request()
        
        with patch("core.middleware.auth.company_resolver.settings") as mock_settings:
            mock_settings.server.env = "production"
            
            with pytest.raises(HTTPException) as exc_info:
                await resolver.resolve(
                    request=request,
                    token_data=token_data_zzz,
                    context_type="api",
                )
        
        assert exc_info.value.status_code == 403


class TestCompanyResolverWithOverride:
    """Тесты: API + X-Company-Id (переключение компании)"""
    
    @pytest.mark.asyncio
    @pytest.mark.parametrize("context_type", ["api", "webhook"])
    async def test_api_override_to_allowed_company_succeeds(
        self, mock_container, company_ggg, user_with_both_companies, token_data_zzz, context_type
    ):
        """API: переключение на компанию с доступом -> успех"""
        mock_container.user_repository.get.return_value = user_with_both_companies
        mock_container.company_repository.get.return_value = company_ggg
        
        resolver = CompanyResolver(mock_container)
        request = make_request(headers={"X-Company-Id": "ggg"})
        
        with patch("core.middleware.auth.company_resolver.settings") as mock_settings:
            mock_settings.server.env = "production"
            
            result = await resolver.resolve(
                request=request,
                token_data=token_data_zzz,
                context_type=context_type,
            )
        
        assert result == company_ggg
        mock_container.user_repository.get.assert_called_once_with("user_123")
        mock_container.company_repository.get.assert_called_once_with("ggg")
    
    @pytest.mark.asyncio
    async def test_api_override_to_forbidden_company_raises_403(
        self, mock_container, user_with_only_zzz
    ):
        """API: переключение на компанию без доступа -> 403"""
        mock_container.user_repository.get.return_value = user_with_only_zzz
        
        resolver = CompanyResolver(mock_container)
        request = make_request(headers={"X-Company-Id": "ggg"})
        
        token_data = make_token_data(user_id="user_456", company_id="zzz")
        
        with patch("core.middleware.auth.company_resolver.settings") as mock_settings:
            mock_settings.server.env = "production"
            
            with pytest.raises(HTTPException) as exc_info:
                await resolver.resolve(
                    request=request,
                    token_data=token_data,
                    context_type="api",
                )
        
        assert exc_info.value.status_code == 403
        assert "нет доступа" in exc_info.value.detail.lower()
    
    @pytest.mark.asyncio
    async def test_api_override_same_company_as_token_succeeds(
        self, mock_container, company_zzz, user_with_both_companies, token_data_zzz
    ):
        """API: X-Company-Id совпадает с токеном -> успех"""
        mock_container.user_repository.get.return_value = user_with_both_companies
        mock_container.company_repository.get.return_value = company_zzz
        
        resolver = CompanyResolver(mock_container)
        request = make_request(headers={"X-Company-Id": "zzz"})
        
        with patch("core.middleware.auth.company_resolver.settings") as mock_settings:
            mock_settings.server.env = "production"
            
            result = await resolver.resolve(
                request=request,
                token_data=token_data_zzz,
                context_type="api",
            )
        
        assert result == company_zzz
    
    @pytest.mark.asyncio
    async def test_api_override_user_not_found_raises_403(self, mock_container, token_data_zzz):
        """API: X-Company-Id с несуществующим пользователем -> 403"""
        mock_container.user_repository.get.return_value = None
        
        resolver = CompanyResolver(mock_container)
        request = make_request(headers={"X-Company-Id": "ggg"})
        
        with patch("core.middleware.auth.company_resolver.settings") as mock_settings:
            mock_settings.server.env = "production"
            
            with pytest.raises(HTTPException) as exc_info:
                await resolver.resolve(
                    request=request,
                    token_data=token_data_zzz,
                    context_type="api",
                )
        
        assert exc_info.value.status_code == 403
        assert "не найден" in exc_info.value.detail.lower()


class TestCompanyResolverLocalEnv:
    """Тесты: local environment - без проверки доступа"""
    
    @pytest.mark.asyncio
    async def test_local_env_override_without_access_check(
        self, mock_container, company_ggg
    ):
        """В local env X-Company-Id работает без проверки доступа"""
        mock_container.company_repository.get.return_value = company_ggg
        
        resolver = CompanyResolver(mock_container)
        request = make_request(headers={"X-Company-Id": "ggg"})
        
        with patch("core.middleware.auth.company_resolver.settings") as mock_settings:
            mock_settings.server.env = "local"
            
            result = await resolver.resolve(
                request=request,
                token_data=None,  # даже без токена
                context_type="api",
            )
        
        assert result == company_ggg
        # user_repository НЕ должен вызываться в local env
        mock_container.user_repository.get.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_local_env_with_localhost_subdomain(self, mock_container, company_ggg):
        """В local env субдомен из .localhost"""
        mock_container.subdomain_repository.get_company_id.return_value = "ggg"
        mock_container.company_repository.get.return_value = company_ggg
        
        resolver = CompanyResolver(mock_container)
        request = make_request(host="ggg.localhost:8000")
        
        with patch("core.middleware.auth.company_resolver.settings") as mock_settings:
            mock_settings.server.env = "local"
            
            result = await resolver.resolve(
                request=request,
                token_data=None,
                context_type="frontend",
            )
        
        assert result == company_ggg


class TestCompanyResolverSubdomain:
    """Тесты: определение компании по субдомену"""
    
    @pytest.mark.asyncio
    async def test_subdomain_resolves_to_company(self, mock_container, company_ggg):
        """Субдомен ggg.humanitec.ru -> компания ggg"""
        mock_container.subdomain_repository.get_company_id.return_value = "ggg"
        mock_container.company_repository.get.return_value = company_ggg
        
        resolver = CompanyResolver(mock_container)
        request = make_request(host="ggg.humanitec.ru")
        
        with patch("core.middleware.auth.company_resolver.settings") as mock_settings:
            mock_settings.server.env = "production"
            
            with patch("core.middleware.auth.company_resolver.extract_subdomain") as mock_extract:
                mock_extract.return_value = "ggg"
                
                result = await resolver.resolve(
                    request=request,
                    token_data=None,
                    context_type="frontend",
                )
        
        assert result == company_ggg
    
    @pytest.mark.asyncio
    async def test_subdomain_not_found_raises_404(self, mock_container):
        """Неизвестный субдомен -> 404"""
        mock_container.subdomain_repository.get_company_id.return_value = None
        
        resolver = CompanyResolver(mock_container)
        request = make_request(host="unknown.humanitec.ru")
        
        with patch("core.middleware.auth.company_resolver.settings") as mock_settings:
            mock_settings.server.env = "production"
            
            with patch("core.middleware.auth.company_resolver.extract_subdomain") as mock_extract:
                mock_extract.return_value = "unknown"
                
                with pytest.raises(HTTPException) as exc_info:
                    await resolver.resolve(
                        request=request,
                        token_data=None,
                        context_type="frontend",
                    )
        
        assert exc_info.value.status_code == 404


class TestCompanyResolverFrontendSubdomainPriority:
    """Тесты: frontend - субдомен имеет приоритет, но проверяется доступ"""
    
    @pytest.mark.asyncio
    async def test_frontend_subdomain_with_access(
        self, mock_container, company_ggg, user_with_both_companies, token_data_zzz
    ):
        """Frontend: субдомен ggg + токен с доступом к ggg -> успех"""
        mock_container.subdomain_repository.get_company_id.return_value = "ggg"
        mock_container.user_repository.get.return_value = user_with_both_companies
        mock_container.company_repository.get.return_value = company_ggg
        
        resolver = CompanyResolver(mock_container)
        request = make_request(host="ggg.humanitec.ru")
        
        with patch("core.middleware.auth.company_resolver.settings") as mock_settings:
            mock_settings.server.env = "production"
            
            with patch("core.middleware.auth.company_resolver.extract_subdomain") as mock_extract:
                mock_extract.return_value = "ggg"
                
                result = await resolver.resolve(
                    request=request,
                    token_data=token_data_zzz,  # токен с zzz, но user имеет доступ к ggg
                    context_type="frontend",
                )
        
        assert result == company_ggg
    
    @pytest.mark.asyncio
    async def test_frontend_subdomain_without_access_raises_403(
        self, mock_container, user_with_only_zzz
    ):
        """Frontend: субдомен ggg + токен без доступа к ggg -> 403"""
        mock_container.subdomain_repository.get_company_id.return_value = "ggg"
        mock_container.user_repository.get.return_value = user_with_only_zzz
        
        resolver = CompanyResolver(mock_container)
        request = make_request(host="ggg.humanitec.ru")
        
        token_data = make_token_data(user_id="user_456", company_id="zzz")
        
        with patch("core.middleware.auth.company_resolver.settings") as mock_settings:
            mock_settings.server.env = "production"
            
            with patch("core.middleware.auth.company_resolver.extract_subdomain") as mock_extract:
                mock_extract.return_value = "ggg"
                
                with pytest.raises(HTTPException) as exc_info:
                    await resolver.resolve(
                        request=request,
                        token_data=token_data,
                        context_type="frontend",
                    )
        
        assert exc_info.value.status_code == 403
        assert "нет доступа" in exc_info.value.detail.lower()
    
    @pytest.mark.asyncio
    async def test_frontend_subdomain_without_token(
        self, mock_container, company_ggg
    ):
        """Frontend: субдомен работает без токена (анонимный доступ)"""
        mock_container.subdomain_repository.get_company_id.return_value = "ggg"
        mock_container.company_repository.get.return_value = company_ggg
        
        resolver = CompanyResolver(mock_container)
        request = make_request(host="ggg.humanitec.ru")
        
        with patch("core.middleware.auth.company_resolver.settings") as mock_settings:
            mock_settings.server.env = "production"
            
            with patch("core.middleware.auth.company_resolver.extract_subdomain") as mock_extract:
                mock_extract.return_value = "ggg"
                
                result = await resolver.resolve(
                    request=request,
                    token_data=None,
                    context_type="frontend",
                )
        
        assert result == company_ggg
    
    @pytest.mark.asyncio
    async def test_frontend_without_subdomain_returns_none(
        self, mock_container, token_data_zzz
    ):
        """Frontend: без субдомена -> None (для редиректа на select-company)"""
        resolver = CompanyResolver(mock_container)
        request = make_request(host="humanitec.ru")  # без субдомена
        
        with patch("core.middleware.auth.company_resolver.settings") as mock_settings:
            mock_settings.server.env = "production"
            
            with patch("core.middleware.auth.company_resolver.extract_subdomain") as mock_extract:
                mock_extract.return_value = None  # нет субдомена
                
                result = await resolver.resolve(
                    request=request,
                    token_data=token_data_zzz,  # токен есть, но игнорируется
                    context_type="frontend",
                )
        
        # Без субдомена для frontend возвращаем None -> редирект
        assert result is None


class TestCompanyResolverAnonymous:
    """Тесты: anonymous контекст"""
    
    @pytest.mark.asyncio
    async def test_anonymous_returns_system_company(self, mock_container):
        """Anonymous запрос -> системная компания"""
        system_company = Company(company_id="system", name="System")
        mock_container.company_repository.get.return_value = system_company
        
        resolver = CompanyResolver(mock_container)
        request = make_request()
        
        with patch("core.middleware.auth.company_resolver.settings") as mock_settings:
            mock_settings.server.env = "production"
            
            with patch("core.middleware.auth.company_resolver.extract_subdomain") as mock_extract:
                mock_extract.return_value = None
                
                result = await resolver.resolve(
                    request=request,
                    token_data=None,
                    context_type="anonymous",
                )
        
        assert result == system_company


class TestActiveCompanySync:
    """Тесты: синхронизация active_company_id в middleware"""
    
    @pytest.mark.asyncio
    async def test_sync_active_company_when_different(self):
        """При смене компании обновляется active_company_id"""
        from core.middleware.auth.middleware import AuthMiddleware
        
        user = User(
            user_id="user_123",
            name="Test",
            companies={"zzz": ["member"], "ggg": ["admin"]},
            active_company_id="zzz",
        )
        company = Company(company_id="ggg", name="GGG")
        
        container = MagicMock()
        container.user_repository = AsyncMock()
        container.user_repository.set = AsyncMock()
        
        middleware = AuthMiddleware(None)
        await middleware._sync_active_company(container, user, company)
        
        assert user.active_company_id == "ggg"
        container.user_repository.set.assert_called_once_with(user)
    
    @pytest.mark.asyncio
    async def test_no_sync_when_same_company(self):
        """Если компания та же - не обновляем"""
        from core.middleware.auth.middleware import AuthMiddleware
        
        user = User(
            user_id="user_123",
            name="Test",
            companies={"ggg": ["admin"]},
            active_company_id="ggg",
        )
        company = Company(company_id="ggg", name="GGG")
        
        container = MagicMock()
        container.user_repository = AsyncMock()
        container.user_repository.set = AsyncMock()
        
        middleware = AuthMiddleware(None)
        await middleware._sync_active_company(container, user, company)
        
        # Не должны вызывать set если компания та же
        container.user_repository.set.assert_not_called()

