"""
Integration тесты для API управления командой.

Тесты БЕЗ моков - проверяем реальные HTTP запросы с реальной БД.
Проверяем изоляцию по компаниям, роли и права доступа.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient


@pytest.mark.asyncio
class TestTeamAPI:
    """Тесты для API управления командой"""

    async def test_get_team_members_success(self, frontend_client: AsyncClient, auth_headers):
        """Получение списка участников команды"""
        response = await frontend_client.get(
            "/frontend/api/team/members",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        members = response.json()
        assert isinstance(members, list)

    async def test_get_team_members_unauthorized(self, frontend_client: AsyncClient):
        """Попытка получить участников без авторизации"""
        response = await frontend_client.get("/frontend/api/team/members")
        
        assert response.status_code == 401

    async def test_update_member_role_success(
        self, 
        frontend_client: AsyncClient, 
        auth_headers,
        frontend_container
    ):
        """Обновление ролей участника"""
        # Получаем текущего пользователя
        from core.utils.tokens import get_token_service
        token_service = get_token_service()
        token_data = token_service.validate_token(auth_headers["Authorization"].replace("Bearer ", ""))
        company_id = token_data.company_id
        
        # Получаем компанию
        company = await frontend_container.company_repository.get(company_id)
        
        # Добавляем тестового участника
        test_user_id = "test_member_to_update"
        company.members[test_user_id] = ["developer"]
        await frontend_container.company_repository.set(company)
        
        # Создаем пользователя
        from core.models.identity_models import User
        test_user = User(
            user_id=test_user_id,
            name="Test Member",
            companies={company_id: ["developer"]},
            active_company_id=company_id
        )
        await frontend_container.user_repository.set(test_user)
        
        # Обновляем роль
        response = await frontend_client.patch(
            f"/frontend/api/team/members/{test_user_id}",
            headers=auth_headers,
            json={"roles": ["admin"]}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "admin" in data["roles"]
        
        # Проверяем что роль действительно обновилась в БД
        updated_company = await frontend_container.company_repository.get(company_id)
        assert "admin" in updated_company.members[test_user_id]

    async def test_update_member_role_cannot_remove_owner(
        self, 
        frontend_client: AsyncClient, 
        auth_headers,
        frontend_container
    ):
        """Нельзя удалить роль owner у владельца"""
        from core.utils.tokens import get_token_service
        token_service = get_token_service()
        token_data = token_service.validate_token(auth_headers["Authorization"].replace("Bearer ", ""))
        company_id = token_data.company_id
        
        company = await frontend_container.company_repository.get(company_id)
        owner_id = company.owner_user_id
        
        response = await frontend_client.patch(
            f"/frontend/api/team/members/{owner_id}",
            headers=auth_headers,
            json={"roles": ["admin"]}
        )
        
        assert response.status_code == 400
        assert "owner" in response.json()["detail"].lower()

    async def test_remove_member_success(
        self, 
        frontend_client: AsyncClient, 
        auth_headers,
        frontend_container
    ):
        """Удаление участника из команды"""
        import uuid
        from core.utils.tokens import get_token_service
        from core.models.identity_models import User, Company
        
        token_service = get_token_service()
        token_data = token_service.validate_token(auth_headers["Authorization"].replace("Bearer ", ""))
        company_id = token_data.company_id
        
        company = await frontend_container.company_repository.get(company_id)
        
        test_user_id = f"member_rm_{uuid.uuid4().hex[:8]}"
        
        fallback_company_id = f"fallback_{uuid.uuid4().hex[:8]}"
        fallback_company = Company(
            company_id=fallback_company_id,
            name="Fallback",
            owner_user_id=test_user_id,
            members={test_user_id: ["owner"]},
        )
        await frontend_container.company_repository.set(fallback_company)
        
        company.members[test_user_id] = ["developer"]
        await frontend_container.company_repository.set(company)
        
        test_user = User(
            user_id=test_user_id,
            name="Test Member To Remove",
            companies={
                company_id: ["developer"],
                fallback_company_id: ["owner"],
            },
            active_company_id=company_id,
        )
        await frontend_container.user_repository.set(test_user)
        
        response = await frontend_client.delete(
            f"/frontend/api/team/members/{test_user_id}",
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        
        updated_company = await frontend_container.company_repository.get(company_id)
        assert test_user_id not in updated_company.members
        
        updated_user = await frontend_container.user_repository.get(test_user_id)
        assert company_id not in updated_user.companies
        assert updated_user.active_company_id == fallback_company_id

    async def test_remove_member_cannot_remove_owner(
        self, 
        frontend_client: AsyncClient, 
        auth_headers,
        frontend_container
    ):
        """Нельзя удалить владельца компании"""
        from core.utils.tokens import get_token_service
        token_service = get_token_service()
        token_data = token_service.validate_token(auth_headers["Authorization"].replace("Bearer ", ""))
        company_id = token_data.company_id
        
        company = await frontend_container.company_repository.get(company_id)
        owner_id = company.owner_user_id
        
        response = await frontend_client.delete(
            f"/frontend/api/team/members/{owner_id}",
            headers=auth_headers
        )
        
        assert response.status_code == 400
        assert "владельца" in response.json()["detail"].lower()

    async def test_team_isolation_between_companies(
        self, 
        frontend_client: AsyncClient, 
        frontend_container
    ):
        """Проверка изоляции команд между компаниями"""
        import uuid
        from core.utils.tokens import get_token_service
        from core.models.identity_models import User, Company
        
        # Создаем две компании
        company1_id = f"company1_{uuid.uuid4().hex[:8]}"
        company2_id = f"company2_{uuid.uuid4().hex[:8]}"
        
        company1 = Company(
            company_id=company1_id,
            name="Company 1",
            owner_id="user1",
            members={"user1": ["owner"], "shared_member": ["developer"]}
        )
        company2 = Company(
            company_id=company2_id,
            name="Company 2",
            owner_id="user2",
            members={"user2": ["owner"]}
        )
        
        await frontend_container.company_repository.set(company1)
        await frontend_container.company_repository.set(company2)
        
        # Создаем пользователя company2
        user2 = User(
            user_id="user2",
            name="User 2",
            companies={company2_id: ["owner"]},
            active_company_id=company2_id
        )
        await frontend_container.user_repository.set(user2)
        
        token_service = get_token_service()
        token2 = token_service.create_token("user2", company_id=company2_id)
        
        # Пользователь company2 получает свою команду
        response = await frontend_client.get(
            "/frontend/api/team/members",
            headers={"Authorization": f"Bearer {token2}"}
        )
        
        assert response.status_code == 200
        members = response.json()
        
        # Не должен видеть shared_member из company1
        member_ids = [m["user_id"] for m in members]
        assert "shared_member" not in member_ids
        assert "user2" in member_ids


@pytest.mark.asyncio
class TestSystemAccessAPI:
    """Тесты self-access для пользователей компании system."""

    async def _create_system_actor(self, frontend_container):
        import uuid
        from core.models.identity_models import Company, User
        from core.utils.tokens import get_token_service

        user_id = f"system_actor_{uuid.uuid4().hex[:8]}"
        system_company = await frontend_container.company_repository.get("system")
        if system_company is None:
            system_company = Company(
                company_id="system",
                name="System",
                owner_user_id=user_id,
                members={},
            )
        system_company.members[user_id] = ["admin"]
        await frontend_container.company_repository.set(system_company)

        user = User(
            user_id=user_id,
            name="System Actor",
            companies={"system": ["admin"]},
            active_company_id="system",
        )
        await frontend_container.user_repository.set(user)

        token_service = get_token_service()
        token = token_service.create_token(user_id=user_id, company_id="system")
        return user_id, {"Authorization": f"Bearer {token}"}

    async def test_enter_company_as_system_member_success(self, frontend_client: AsyncClient, frontend_container):
        import uuid
        from core.models.identity_models import Company

        system_user_id, auth_headers = await self._create_system_actor(frontend_container)
        company_id = f"target_company_{uuid.uuid4().hex[:8]}"
        target_company = Company(
            company_id=company_id,
            name="Target",
            owner_user_id="target_owner",
            members={"target_owner": ["owner"]},
            subdomain=f"target-{uuid.uuid4().hex[:6]}",
        )
        await frontend_container.company_repository.set(target_company)

        response = await frontend_client.post(
            f"/frontend/api/companies/{company_id}/system-access",
            headers=auth_headers,
            json={"role": "admin"},
        )

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert "admin" in response.json()["roles"]

        updated_user = await frontend_container.user_repository.get(system_user_id)
        assert "admin" in updated_user.companies[company_id]
        updated_company = await frontend_container.company_repository.get(company_id)
        assert "admin" in updated_company.members[system_user_id]

    async def test_enter_company_as_system_member_rejects_owner_role(
        self,
        frontend_client: AsyncClient,
        frontend_container,
    ):
        import uuid
        from core.models.identity_models import Company

        _, auth_headers = await self._create_system_actor(frontend_container)
        company_id = f"target_company_{uuid.uuid4().hex[:8]}"
        target_company = Company(
            company_id=company_id,
            name="Target",
            owner_user_id="target_owner",
            members={"target_owner": ["owner"]},
            subdomain=f"target-{uuid.uuid4().hex[:6]}",
        )
        await frontend_container.company_repository.set(target_company)

        response = await frontend_client.post(
            f"/frontend/api/companies/{company_id}/system-access",
            headers=auth_headers,
            json={"role": "owner"},
        )

        assert response.status_code == 400
        assert "Недопустимая роль" in response.json()["detail"]

    async def test_enter_company_as_system_member_rejects_non_system_user(
        self,
        frontend_client: AsyncClient,
        auth_headers_company2,
        frontend_container,
    ):
        import uuid
        from core.models.identity_models import Company

        company_id = f"target_company_{uuid.uuid4().hex[:8]}"
        target_company = Company(
            company_id=company_id,
            name="Target",
            owner_user_id="target_owner",
            members={"target_owner": ["owner"]},
            subdomain=f"target-{uuid.uuid4().hex[:6]}",
        )
        await frontend_container.company_repository.set(target_company)

        response = await frontend_client.post(
            f"/frontend/api/companies/{company_id}/system-access",
            headers=auth_headers_company2,
            json={"role": "admin"},
        )

        assert response.status_code == 403
        assert "system" in response.json()["detail"].lower()

    async def test_leave_company_switches_active_company_to_system(
        self,
        frontend_client: AsyncClient,
        frontend_container,
    ):
        import uuid
        from core.models.identity_models import Company

        system_user_id, auth_headers = await self._create_system_actor(frontend_container)
        company_id = f"target_company_{uuid.uuid4().hex[:8]}"
        target_company = Company(
            company_id=company_id,
            name="Target",
            owner_user_id="target_owner",
            members={"target_owner": ["owner"], system_user_id: ["admin"]},
            subdomain=f"target-{uuid.uuid4().hex[:6]}",
        )
        await frontend_container.company_repository.set(target_company)

        user = await frontend_container.user_repository.get(system_user_id)
        user.companies[company_id] = ["admin"]
        user.active_company_id = company_id
        await frontend_container.user_repository.set(user)

        response = await frontend_client.delete(
            f"/frontend/api/companies/{company_id}/system-access",
            headers=auth_headers,
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is True
        assert payload["switched_to_system"] is True
        set_cookie = response.headers.get("set-cookie")
        assert set_cookie is not None
        assert "auth_token=" in set_cookie

        updated_user = await frontend_container.user_repository.get(system_user_id)
        assert company_id not in updated_user.companies
        assert updated_user.active_company_id == "system"
        updated_company = await frontend_container.company_repository.get(company_id)
        assert system_user_id not in updated_company.members
