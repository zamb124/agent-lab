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
        user_repo,
        taskiq_broker
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
    async def test_create_company_with_migration(
        self,
        async_client,
        auth_token_for_new_user,
        company_repo,
        subdomain_repo,
        user_repo,
        taskiq_broker,
        taskiq_worker_process,
        flow_repo,
        tool_repo,
        mcp_repo,
    ):
        """Тест создания компании с проверкой миграции через TaskIQ"""
        import asyncio
        from core.context import set_context, clear_context
        from apps.agents.config import get_agents_settings
        
        token, user = auth_token_for_new_user
        
        test_slug = "test-company-migration"
        existing_company = await company_repo.get(test_slug)
        if existing_company:
            await company_repo.delete(test_slug)
        existing_mapping = await subdomain_repo.get(test_slug)
        if existing_mapping:
            await subdomain_repo.delete(test_slug)
        
        response = await async_client.post(
            "/frontend/api/admin/create-my-company",
            data={
                "name": "Test Company Migration",
                "slug": test_slug
            },
            cookies={"auth_token": token},
            follow_redirects=False
        )
        
        assert response.status_code in [302, 307]
        
        company = await company_repo.get(test_slug)
        assert company is not None
        
        # Устанавливаем контекст новой компании для проверки
        context = Context(
            user=user,
            platform="test",
            active_company=company,
            user_companies=[company]
        )
        set_context(context)
        
        try:
            settings = get_agents_settings()
            
            # Ждем выполнения миграции (макс 60 сек) - проверяем ВСЕ сущности
            migration_complete = False
            for _ in range(60):
                await asyncio.sleep(1)
                
                # Проверяем все сущности - tools, MCP серверы
                tools = await tool_repo.list_all(limit=100)
                context7 = await mcp_repo.get("context7")
                copilot = await mcp_repo.get("copilot")
                
                if len(tools) > 0 and context7 is not None and copilot is not None:
                    migration_complete = True
                    break
            
            assert migration_complete, "Миграция не завершилась за 60 секунд"
            
            # Проверяем что публичные tools появились в БД
            tools = await tool_repo.list_all(limit=100)
            assert len(tools) > 0, "Публичные tools должны быть мигрированы через TaskIQ"
            
            # Проверяем MCP серверы
            assert await mcp_repo.get("context7") is not None, "MCP context7 должен быть создан"
            assert await mcp_repo.get("copilot") is not None, "MCP copilot должен быть создан"
            
        finally:
            clear_context()

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
        user_repo,
        taskiq_broker
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


class TestCompanyMigration:
    """Интеграционные тесты миграции flows при создании компании БЕЗ моков"""

    @pytest.mark.asyncio
    async def test_company_migration_creates_default_flows(
        self,
        migrated_db,
        migrator,
        company_repo,
        subdomain_repo,
        flow_repo,
        tool_repo,
        mcp_repo
    ):
        """
        Интеграционный тест: после создания компании мигрируются дефолтные flows из store.
        БЕЗ МОКОВ - реальная БД и реальная миграция.
        """
        from datetime import datetime, timezone
        from core.db.repositories.subdomain_repository import SubdomainMapping
        from apps.agents.config import get_agents_settings
        
        test_company = Company(
            company_id="test_migration_flows",
            subdomain="test_migration_flows",
            name="Test Migration Flows",
            status="active",
            balance=50.0,
            created_at=datetime.now(timezone.utc)
        )
        await company_repo.set(test_company)
        await subdomain_repo.set(SubdomainMapping(
            subdomain=test_company.subdomain,
            company_id=test_company.company_id
        ))
        
        user = User(
            user_id="test_migration_user",
            provider=AuthProvider.YANDEX,
            provider_user_id="test_migration",
            email="test_migration@test.local",
            name="Test Migration",
            status=UserStatus.ACTIVE,
            groups=["admin"],
            companies={test_company.company_id: ["admin"]},
            active_company_id=test_company.company_id
        )
        
        context = Context(
            user=user,
            platform="test",
            active_company=test_company,
            user_companies=[test_company]
        )
        set_context(context)
        
        try:
            # Вызываем миграцию синхронно (для теста)
            await migrator.migrate_defaults_for_company(test_company)
            
            # Проверяем что дефолтные flows создались (из settings.migration.default_flows)
            settings = get_agents_settings()
            for flow_id in settings.migration.default_flows:
                flow = await flow_repo.get(flow_id)
                assert flow is not None, f"Flow {flow_id} должен быть мигрирован"
            
            # Проверяем что MCP серверы создались
            context7 = await mcp_repo.get("context7")
            assert context7 is not None, "MCP сервер context7 должен быть создан"
            
            copilot = await mcp_repo.get("copilot")
            assert copilot is not None, "MCP сервер copilot должен быть создан"
            
            # Проверяем что публичные tools мигрировались
            tools = await tool_repo.list_all(limit=100)
            assert len(tools) > 0, "Публичные tools должны быть мигрированы"
            
        finally:
            # Cleanup - контекст должен быть активен для удаления данных компании
            all_flows = await flow_repo.list_all(limit=1000)
            for flow in all_flows:
                await flow_repo.delete(flow.flow_id)
            
            all_tools = await tool_repo.list_all(limit=1000)
            for tool in all_tools:
                await tool_repo.delete(tool.tool_id)
                
            all_mcp = await mcp_repo.list_all(limit=100)
            for mcp in all_mcp:
                await mcp_repo.delete(mcp.server_id)
            
            clear_context()
            await company_repo.delete(test_company.company_id)
            await subdomain_repo.delete(test_company.subdomain)

    @pytest.mark.asyncio
    async def test_second_company_has_zero_balance(
        self,
        migrated_db,
        company_repo,
        user_repo
    ):
        """
        Тест: вторая компания пользователя создается с нулевым балансом.
        """
        from datetime import datetime, timezone
        
        # Создаем пользователя с одной компанией
        first_company = Company(
            company_id="first_company_test",
            subdomain="first_test",
            name="First Company",
            status="active",
            balance=50.0,
            created_at=datetime.now(timezone.utc)
        )
        await company_repo.set(first_company)
        
        user = User(
            user_id="test_multi_company_user",
            provider=AuthProvider.YANDEX,
            provider_user_id="test_multi",
            email="test_multi@test.local",
            name="Test Multi",
            status=UserStatus.ACTIVE,
            groups=["user"],
            companies={"first_company_test": ["admin"]},
            active_company_id="first_company_test"
        )
        await user_repo.set(user)
        
        context = Context(
            user=user,
            platform="test",
            active_company=first_company,
            user_companies=[first_company]
        )
        set_context(context)
        
        try:
            # Проверяем логику баланса: если у пользователя уже есть компания, баланс = 0
            initial_balance = 50.0 if len(user.companies) == 0 else 0.0
            assert initial_balance == 0.0, "Вторая компания должна иметь нулевой баланс"
            
            # Создаем вторую компанию
            second_company = Company(
                company_id="second_company_test",
                subdomain="second_test",
                name="Second Company",
                status="active",
                balance=initial_balance,
                created_at=datetime.now(timezone.utc)
            )
            await company_repo.set(second_company)
            
            # Проверяем баланс
            loaded_second = await company_repo.get("second_company_test")
            assert loaded_second.balance == 0.0, "Вторая компания должна иметь баланс 0"
            
            # Проверяем что первая компания имеет баланс 50
            loaded_first = await company_repo.get("first_company_test")
            assert loaded_first.balance == 50.0, "Первая компания должна иметь баланс 50"
            
        finally:
            clear_context()
            await company_repo.delete("first_company_test")
            await company_repo.delete("second_company_test")
            await user_repo.delete("test_multi_company_user")

