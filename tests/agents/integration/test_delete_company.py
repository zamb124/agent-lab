"""
Тесты для удаления компании через API endpoint
DELETE /frontend/api/admin/company/{company_id}
"""
import asyncio
import pytest
import pytest_asyncio
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport

from core.utils.tokens import get_token_service
from core.context import set_context, clear_context, get_context
from core.models import User, Company, Context
from core.models.identity_models import AuthProvider, UserStatus
from apps.agents.models import AgentConfig, FlowConfig


class TestDeleteCompanyEndpoint:
    """Тесты для endpoint удаления компании"""

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
    async def user_with_two_companies(
        self,
        user_repo,
        company_repo,
        subdomain_repo,
        unique_id
    ):
        """Создает пользователя с двумя компаниями"""
        company1_id = unique_id("company1")
        company2_id = unique_id("company2")
        user_id = unique_id("user")
        
        company1 = Company(
            company_id=company1_id,
            subdomain=company1_id,
            name="Company One",
            status="active",
            balance=50.0,
            created_at=datetime.now(timezone.utc)
        )
        await company_repo.set(company1)
        await subdomain_repo.set_mapping(company1_id, company1_id)
        
        company2 = Company(
            company_id=company2_id,
            subdomain=company2_id,
            name="Company Two",
            status="active",
            balance=0.0,
            created_at=datetime.now(timezone.utc)
        )
        await company_repo.set(company2)
        await subdomain_repo.set_mapping(company2_id, company2_id)
        
        user = User(
            user_id=user_id,
            provider=AuthProvider.YANDEX,
            provider_user_id=f"yandex_{user_id}",
            email=f"{user_id}@test.local",
            name="Test User Two Companies",
            status=UserStatus.ACTIVE,
            groups=["user"],
            companies={
                company1_id: ["admin", "user"],
                company2_id: ["admin", "user"],
            },
            active_company_id=company1_id
        )
        await user_repo.set(user)
        
        token_service = get_token_service()
        token = token_service.create_token(
            user_id=user.user_id,
            company_id=company1_id,
            session_id=f"test_session_{user_id}",
            expires_in=3600,
            metadata={"provider": "yandex", "user_name": user.name}
        )
        
        yield {
            "user": user,
            "company1": company1,
            "company2": company2,
            "token": token,
        }
        
        # Cleanup
        clear_context()
        await user_repo.delete(user_id)
        try:
            await company_repo.delete(company1_id)
        except Exception:
            pass
        try:
            await company_repo.delete(company2_id)
        except Exception:
            pass
        try:
            await subdomain_repo.delete(company1_id)
        except Exception:
            pass
        try:
            await subdomain_repo.delete(company2_id)
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_delete_company_forbidden_without_admin_role(
        self,
        async_client,
        user_repo,
        company_repo,
        subdomain_repo,
        unique_id
    ):
        """Тест: удаление компании запрещено без роли admin"""
        company1_id = unique_id("company_no_admin1")
        company2_id = unique_id("company_no_admin2")
        user_id = unique_id("user_no_admin")
        
        company1 = Company(
            company_id=company1_id,
            subdomain=company1_id,
            name="Company No Admin 1",
            status="active",
        )
        await company_repo.set(company1)
        await subdomain_repo.set_mapping(company1_id, company1_id)
        
        company2 = Company(
            company_id=company2_id,
            subdomain=company2_id,
            name="Company No Admin 2",
            status="active",
        )
        await company_repo.set(company2)
        await subdomain_repo.set_mapping(company2_id, company2_id)
        
        # Пользователь с ролью user (не admin) в обеих компаниях
        user = User(
            user_id=user_id,
            provider=AuthProvider.YANDEX,
            provider_user_id=f"yandex_{user_id}",
            email=f"{user_id}@test.local",
            name="User Without Admin",
            status=UserStatus.ACTIVE,
            groups=["user"],
            companies={
                company1_id: ["user"],
                company2_id: ["user"],
            },
            active_company_id=company1_id
        )
        await user_repo.set(user)
        
        token_service = get_token_service()
        token = token_service.create_token(
            user_id=user.user_id,
            company_id=company1_id,
            session_id=f"test_session_{user_id}",
            expires_in=3600,
        )
        
        try:
            response = await async_client.delete(
                f"/frontend/api/admin/company/{company2_id}",
                cookies={"auth_token": token},
                headers={"X-Company-Id": company1_id},
            )
            
            assert response.status_code == 403
            assert "admin" in response.json()["detail"].lower()
        finally:
            await user_repo.delete(user_id)
            await company_repo.delete(company1_id)
            await company_repo.delete(company2_id)
            await subdomain_repo.delete(company1_id)
            await subdomain_repo.delete(company2_id)

    @pytest.mark.asyncio
    async def test_delete_last_company_forbidden(
        self,
        async_client,
        user_repo,
        company_repo,
        subdomain_repo,
        unique_id
    ):
        """Тест: нельзя удалить единственную компанию пользователя"""
        company_id = unique_id("single_company")
        user_id = unique_id("single_company_user")
        
        company = Company(
            company_id=company_id,
            subdomain=company_id,
            name="Single Company",
            status="active",
        )
        await company_repo.set(company)
        await subdomain_repo.set_mapping(company_id, company_id)
        
        user = User(
            user_id=user_id,
            provider=AuthProvider.YANDEX,
            provider_user_id=f"yandex_{user_id}",
            email=f"{user_id}@test.local",
            name="Single Company User",
            status=UserStatus.ACTIVE,
            groups=["user"],
            companies={company_id: ["admin", "user"]},
            active_company_id=company_id
        )
        await user_repo.set(user)
        
        token_service = get_token_service()
        token = token_service.create_token(
            user_id=user.user_id,
            company_id=company_id,
            session_id=f"test_session_{user_id}",
            expires_in=3600,
        )
        
        try:
            response = await async_client.delete(
                f"/frontend/api/admin/company/{company_id}",
                cookies={"auth_token": token},
                headers={"X-Company-Id": company_id},
            )
            
            assert response.status_code == 400
            assert "единственную" in response.json()["detail"].lower()
        finally:
            await user_repo.delete(user_id)
            await company_repo.delete(company_id)
            await subdomain_repo.delete(company_id)

    @pytest.mark.asyncio
    async def test_delete_company_marks_as_deleting(
        self,
        async_client,
        user_with_two_companies,
        company_repo,
        taskiq_broker,
    ):
        """Тест: при удалении компания помечается статусом 'deleting'"""
        data = user_with_two_companies
        company_to_delete = data["company2"]
        token = data["token"]
        
        response = await async_client.delete(
            f"/frontend/api/admin/company/{company_to_delete.company_id}",
            cookies={"auth_token": token},
            headers={"X-Company-Id": data["company1"].company_id},
        )
        
        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "deleting"
        
        company = await company_repo.get(company_to_delete.company_id)
        assert company.status == "deleting"


class TestDeleteCompanyWithTaskIQ:
    """Интеграционные тесты удаления компании с TaskIQ воркером"""

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

    @pytest.mark.asyncio
    async def test_delete_company_removes_all_data(
        self,
        async_client,
        user_repo,
        company_repo,
        subdomain_repo,
        agent_repo,
        flow_repo,
        tool_repo,
        session_repo,
        mcp_repo,
        variable_repo,
        taskiq_broker,
        taskiq_worker_process,
        unique_id,
    ):
        """
        Полный интеграционный тест удаления компании.
        
        1. Создает компанию с данными (agents, flows, tools, sessions, variables)
        2. Вызывает DELETE endpoint
        3. Ждет выполнения TaskIQ задачи
        4. Проверяет что все данные удалены
        """
        company1_id = unique_id("keep_company")
        company2_id = unique_id("delete_company")
        user_id = unique_id("delete_test_user")
        
        # Создаем две компании
        company1 = Company(
            company_id=company1_id,
            subdomain=company1_id,
            name="Company to Keep",
            status="active",
            balance=50.0,
            created_at=datetime.now(timezone.utc)
        )
        await company_repo.set(company1)
        await subdomain_repo.set_mapping(company1_id, company1_id)
        
        company2 = Company(
            company_id=company2_id,
            subdomain=company2_id,
            name="Company to Delete",
            status="active",
            balance=0.0,
            created_at=datetime.now(timezone.utc)
        )
        await company_repo.set(company2)
        await subdomain_repo.set_mapping(company2_id, company2_id)
        
        user = User(
            user_id=user_id,
            provider=AuthProvider.YANDEX,
            provider_user_id=f"yandex_{user_id}",
            email=f"{user_id}@test.local",
            name="Delete Test User",
            status=UserStatus.ACTIVE,
            groups=["user"],
            companies={
                company1_id: ["admin", "user"],
                company2_id: ["admin", "user"],
            },
            active_company_id=company1_id
        )
        await user_repo.set(user)
        
        # Устанавливаем контекст для company2 чтобы создать данные
        context = Context(
            user=user,
            platform="test",
            active_company=company2,
            user_companies=[company1, company2]
        )
        set_context(context)
        
        try:
            # Создаем данные в company2
            test_agent = AgentConfig(
                agent_id=f"test_agent_{company2_id}",
                name="Test Agent for Delete",
                model="gpt-4",
                prompt="Test prompt",
                is_public=False,
            )
            await agent_repo.set(test_agent)
            
            test_flow = FlowConfig(
                flow_id=f"test_flow_{company2_id}",
                name="Test Flow for Delete",
                entry_point_agent=test_agent.agent_id,
                is_public=False,
            )
            await flow_repo.set(test_flow)
            
            from apps.agents.models import ToolReference
            test_tool = ToolReference(
                tool_id=f"test_tool_{company2_id}",
                name="Test Tool for Delete",
                code="async def test(): pass",
                is_public=False,
            )
            await tool_repo.set(test_tool)
            
            from apps.agents.models import SessionConfig, SessionStatus
            test_session = SessionConfig(
                session_id=f"test_session_{company2_id}",
                flow_id=test_flow.flow_id,
                user_id=user_id,
                platform="test",
                status=SessionStatus.ACTIVE,
            )
            await session_repo.set(test_session)
            
            from core.db.repositories.variable_repository import Variable
            test_variable = Variable(
                key=f"test_var_{company2_id}",
                value="test_value",
                description="Test variable for delete",
            )
            await variable_repo.set(test_variable)
            
            # Проверяем что данные созданы
            assert await agent_repo.get(test_agent.agent_id) is not None
            assert await flow_repo.get(test_flow.flow_id) is not None
            assert await tool_repo.get(test_tool.tool_id) is not None
            assert await session_repo.get(test_session.session_id) is not None
            assert await variable_repo.get(test_variable.key) is not None
            
            clear_context()
            
            # Создаем токен и вызываем DELETE endpoint
            token_service = get_token_service()
            token = token_service.create_token(
                user_id=user.user_id,
                company_id=company1_id,
                session_id=f"test_session_{user_id}",
                expires_in=3600,
            )
            
            response = await async_client.delete(
                f"/frontend/api/admin/company/{company2_id}",
                cookies={"auth_token": token},
                headers={"X-Company-Id": company1_id},
            )
            
            assert response.status_code == 200
            result = response.json()
            assert result["status"] == "deleting"
            
            # Ждем выполнения TaskIQ задачи (макс 60 секунд)
            deletion_complete = False
            for _ in range(60):
                await asyncio.sleep(1)
                
                company = await company_repo.get(company2_id)
                if company is None:
                    deletion_complete = True
                    break
            
            assert deletion_complete, "Компания должна быть удалена за 60 секунд"
            
            # Устанавливаем контекст company2 для проверки что данные удалены
            context = Context(
                user=user,
                platform="test",
                active_company=Company(
                    company_id=company2_id,
                    subdomain=company2_id,
                    name="Deleted",
                    status="deleted"
                ),
                user_companies=[]
            )
            set_context(context)
            
            # Проверяем что все данные удалены
            assert await agent_repo.get(test_agent.agent_id) is None, "Агент должен быть удален"
            assert await flow_repo.get(test_flow.flow_id) is None, "Flow должен быть удален"
            assert await tool_repo.get(test_tool.tool_id) is None, "Tool должен быть удален"
            assert await session_repo.get(test_session.session_id) is None, "Session должна быть удалена"
            assert await variable_repo.get(test_variable.key) is None, "Variable должна быть удалена"
            
            clear_context()
            
            # Проверяем что subdomain mapping удален
            subdomain_company_id = await subdomain_repo.get_company_id(company2_id)
            assert subdomain_company_id is None, "Subdomain mapping должен быть удален"
            
            # Проверяем что пользователь обновлен
            updated_user = await user_repo.get(user_id)
            assert company2_id not in updated_user.companies, "Компания должна быть удалена из списка пользователя"
            assert updated_user.active_company_id != company2_id, "Активная компания должна измениться"
            
        finally:
            clear_context()
            # Cleanup оставшихся данных
            try:
                await user_repo.delete(user_id)
            except Exception:
                pass
            try:
                await company_repo.delete(company1_id)
            except Exception:
                pass
            try:
                await subdomain_repo.delete(company1_id)
            except Exception:
                pass

    @pytest.mark.asyncio
    async def test_delete_company_does_not_affect_other_company(
        self,
        async_client,
        user_repo,
        company_repo,
        subdomain_repo,
        agent_repo,
        flow_repo,
        taskiq_broker,
        taskiq_worker_process,
        unique_id,
    ):
        """
        Тест: удаление одной компании не влияет на данные другой компании.
        """
        company1_id = unique_id("company_keep")
        company2_id = unique_id("company_delete")
        user_id = unique_id("isolation_test_user")
        
        company1 = Company(
            company_id=company1_id,
            subdomain=company1_id,
            name="Company to Keep",
            status="active",
        )
        await company_repo.set(company1)
        await subdomain_repo.set_mapping(company1_id, company1_id)
        
        company2 = Company(
            company_id=company2_id,
            subdomain=company2_id,
            name="Company to Delete",
            status="active",
        )
        await company_repo.set(company2)
        await subdomain_repo.set_mapping(company2_id, company2_id)
        
        user = User(
            user_id=user_id,
            provider=AuthProvider.YANDEX,
            provider_user_id=f"yandex_{user_id}",
            email=f"{user_id}@test.local",
            name="Isolation Test User",
            status=UserStatus.ACTIVE,
            groups=["user"],
            companies={
                company1_id: ["admin", "user"],
                company2_id: ["admin", "user"],
            },
            active_company_id=company1_id
        )
        await user_repo.set(user)
        
        # Создаем данные в company1
        context1 = Context(
            user=user,
            platform="test",
            active_company=company1,
            user_companies=[company1, company2]
        )
        set_context(context1)
        
        agent1 = AgentConfig(
            agent_id=f"agent_keep_{company1_id}",
            name="Agent in Company 1",
            model="gpt-4",
            prompt="Keep this",
            is_public=False,
        )
        await agent_repo.set(agent1)
        
        flow1 = FlowConfig(
            flow_id=f"flow_keep_{company1_id}",
            name="Flow in Company 1",
            entry_point_agent=agent1.agent_id,
            is_public=False,
        )
        await flow_repo.set(flow1)
        
        clear_context()
        
        # Создаем данные в company2
        context2 = Context(
            user=user,
            platform="test",
            active_company=company2,
            user_companies=[company1, company2]
        )
        set_context(context2)
        
        agent2 = AgentConfig(
            agent_id=f"agent_delete_{company2_id}",
            name="Agent in Company 2",
            model="gpt-4",
            prompt="Delete this",
            is_public=False,
        )
        await agent_repo.set(agent2)
        
        clear_context()
        
        try:
            # Удаляем company2
            token_service = get_token_service()
            token = token_service.create_token(
                user_id=user.user_id,
                company_id=company1_id,
                session_id=f"test_session_{user_id}",
                expires_in=3600,
            )
            
            response = await async_client.delete(
                f"/frontend/api/admin/company/{company2_id}",
                cookies={"auth_token": token},
                headers={"X-Company-Id": company1_id},
            )
            
            assert response.status_code == 200
            
            # Ждем удаления
            for _ in range(60):
                await asyncio.sleep(1)
                if await company_repo.get(company2_id) is None:
                    break
            
            # Проверяем что данные company1 сохранились
            set_context(context1)
            
            loaded_agent1 = await agent_repo.get(agent1.agent_id)
            assert loaded_agent1 is not None, "Агент company1 должен сохраниться"
            assert loaded_agent1.name == "Agent in Company 1"
            
            loaded_flow1 = await flow_repo.get(flow1.flow_id)
            assert loaded_flow1 is not None, "Flow company1 должен сохраниться"
            
            clear_context()
            
            # Проверяем что company1 не затронута
            loaded_company1 = await company_repo.get(company1_id)
            assert loaded_company1 is not None, "Company1 должна сохраниться"
            assert loaded_company1.status == "active"
            
        finally:
            clear_context()
            # Cleanup
            set_context(context1)
            try:
                await agent_repo.delete(agent1.agent_id)
            except Exception:
                pass
            try:
                await flow_repo.delete(flow1.flow_id)
            except Exception:
                pass
            clear_context()
            
            try:
                await user_repo.delete(user_id)
            except Exception:
                pass
            try:
                await company_repo.delete(company1_id)
            except Exception:
                pass
            try:
                await subdomain_repo.delete(company1_id)
            except Exception:
                pass

