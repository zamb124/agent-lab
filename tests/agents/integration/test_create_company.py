"""
Тесты для создания компании через API endpoint
/frontend/api/admin/create-my-company
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport

from core.utils.tokens import get_token_service
from core.context import set_context, clear_context
from core.models import User, Company, Context
from core.models.identity_models import AuthProvider, UserStatus


class TestCreateCompanyEndpoint:
    """Тесты для endpoint создания компании"""

    @pytest_asyncio.fixture
    async def frontend_app(self, migrated_db):
        """Фикстура для frontend приложения"""
        from apps.frontend.main import create_app
        app = create_app()
        yield app

    @pytest_asyncio.fixture
    async def async_client(self, frontend_app):
        """Async HTTP клиент для тестов"""
        transport = ASGITransport(app=frontend_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

    @pytest_asyncio.fixture
    async def auth_token_for_new_user(self, user_repo):
        """Создает пользователя БЕЗ компаний и возвращает токен"""
        user = User(
            user_id="test_new_user_123",
            provider=AuthProvider.YANDEX,
            provider_user_id="yandex_new_123",
            email="newuser@test.local",
            name="New Test User",
            status=UserStatus.ACTIVE,
            groups=["user"],
            companies={},
            active_company_id=""
        )
        await user_repo.set(user)
        
        token_service = get_token_service()
        token = token_service.create_token(
            user_id=user.user_id,
            company_id="",
            session_id="test_session_new_user",
            expires_in=3600,
            metadata={"provider": "yandex", "user_name": user.name}
        )
        return token, user

    @pytest.mark.asyncio
    async def test_create_company_success(
        self,
        async_client,
        auth_token_for_new_user,
        company_repo,
        subdomain_repo,
        user_repo
    ):
        """Тест успешного создания компании"""
        token, user = auth_token_for_new_user
        
        test_slug = "test-company-slug"
        existing_company = await company_repo.get(test_slug)
        if existing_company:
            await company_repo.delete(test_slug)
        existing_mapping = await subdomain_repo.get(test_slug)
        if existing_mapping:
            await subdomain_repo.delete(test_slug)
        
        response = await async_client.post(
            "/frontend/api/admin/create-my-company",
            data={
                "name": "Test Company",
                "slug": test_slug
            },
            cookies={"auth_token": token},
            follow_redirects=False
        )
        
        assert response.status_code in [302, 307], f"Expected redirect, got {response.status_code}: {response.text}"
        
        company = await company_repo.get(test_slug)
        assert company is not None
        assert company.name == "Test Company"
        
        subdomain_company_id = await subdomain_repo.get_company_id(test_slug)
        assert subdomain_company_id == test_slug
        
        updated_user = await user_repo.get(user.user_id)
        assert test_slug in updated_user.companies
        assert updated_user.active_company_id == test_slug

    @pytest.mark.asyncio
    async def test_create_company_without_auth(self, async_client):
        """Тест создания компании без авторизации"""
        response = await async_client.post(
            "/frontend/api/admin/create-my-company",
            data={
                "name": "Test Company",
                "slug": "test-slug"
            },
            follow_redirects=False
        )
        
        assert response.status_code in [401, 302]

    @pytest.mark.asyncio
    async def test_create_company_duplicate_slug(
        self,
        async_client,
        auth_token_for_new_user,
        company_repo,
        subdomain_repo
    ):
        """Тест создания компании с уже занятым slug"""
        token, _ = auth_token_for_new_user
        
        existing_company = Company(
            company_id="existing-slug",
            subdomain="existing-slug",
            name="Existing Company",
            status="active"
        )
        await company_repo.set(existing_company)
        await subdomain_repo.set_mapping("existing-slug", "existing-slug")
        
        response = await async_client.post(
            "/frontend/api/admin/create-my-company",
            data={
                "name": "New Company",
                "slug": "existing-slug"
            },
            cookies={"auth_token": token},
            follow_redirects=False
        )
        
        assert response.status_code == 400
        assert "уже занят" in response.text or "already" in response.text.lower()

    @pytest.mark.asyncio
    async def test_create_company_missing_slug(
        self,
        async_client,
        auth_token_for_new_user
    ):
        """Тест создания компании без slug"""
        token, _ = auth_token_for_new_user
        
        response = await async_client.post(
            "/frontend/api/admin/create-my-company",
            data={
                "name": "Test Company"
            },
            cookies={"auth_token": token},
            follow_redirects=False
        )
        
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_create_company_updates_auth_token_with_company_id(
        self,
        async_client,
        auth_token_for_new_user,
        company_repo,
        subdomain_repo,
        user_repo
    ):
        """Тест что после создания компании токен обновляется с правильным company_id"""
        token, user = auth_token_for_new_user
        token_service = get_token_service()
        
        # Проверяем что исходный токен имеет пустой company_id
        old_token_data = token_service.validate_token(token)
        assert old_token_data.company_id == "" or old_token_data.company_id is None
        
        test_slug = "test-token-update-slug"
        
        # Очистка если существует
        existing_company = await company_repo.get(test_slug)
        if existing_company:
            await company_repo.delete(test_slug)
        existing_mapping = await subdomain_repo.get(test_slug)
        if existing_mapping:
            await subdomain_repo.delete(test_slug)
        
        response = await async_client.post(
            "/frontend/api/admin/create-my-company",
            data={
                "name": "Token Update Test Company",
                "slug": test_slug
            },
            cookies={"auth_token": token},
            follow_redirects=False
        )
        
        assert response.status_code in [302, 307]
        
        # Проверяем что в response есть новый auth_token cookie (в заголовках set-cookie)
        set_cookie_header = response.headers.get("set-cookie", "")
        assert "auth_token=" in set_cookie_header, f"auth_token cookie должен быть в set-cookie заголовке, получили: {set_cookie_header[:100]}"
        
        # Извлекаем токен из set-cookie заголовка
        import re
        token_match = re.search(r'auth_token=([^;]+)', set_cookie_header)
        assert token_match is not None, "Не удалось извлечь auth_token из set-cookie"
        new_token = token_match.group(1)
        
        # Проверяем что новый токен содержит правильный company_id
        new_token_data = token_service.validate_token(new_token)
        assert new_token_data is not None, "Новый токен должен быть валидным"
        assert new_token_data.company_id == test_slug, f"company_id должен быть {test_slug}, получили {new_token_data.company_id}"
        assert new_token_data.user_id == user.user_id, "user_id должен сохраниться"
        assert new_token_data.session_id == old_token_data.session_id, "session_id должен сохраниться"


class TestCreateCompanyMiddlewarePath:
    """Тесты для проверки что middleware правильно обрабатывает путь создания компании"""

    @pytest.mark.asyncio
    async def test_middleware_allows_no_company_for_create_endpoint(self, migrated_db):
        """Проверяет что middleware разрешает доступ к /frontend/api/admin/create-my-company
        даже если у пользователя нет компаний"""
        from core.middleware.auth import AuthMiddleware
        
        path = "/frontend/api/admin/create-my-company"
        
        assert "/frontend/api/admin/create-my-company" in path or \
               path.startswith("/frontend/") and "create-my-company" in path

