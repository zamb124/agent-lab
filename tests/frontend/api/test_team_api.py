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

    async def test_invite_member_success(self, frontend_client: AsyncClient, auth_headers):
        """Приглашение нового участника"""
        response = await frontend_client.post(
            "/frontend/api/team/invite",
            headers=auth_headers,
            json={
                "email": "newmember@test.com",
                "role": "developer"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "newmember@test.com" in data["email"]

    async def test_invite_member_invalid_role(self, frontend_client: AsyncClient, auth_headers):
        """Приглашение с недопустимой ролью"""
        response = await frontend_client.post(
            "/frontend/api/team/invite",
            headers=auth_headers,
            json={
                "email": "test@test.com",
                "role": "invalid_role"
            }
        )
        
        assert response.status_code == 400
        assert "Недопустимая роль" in response.json()["detail"]

    async def test_invite_member_as_viewer_forbidden(
        self, 
        frontend_client: AsyncClient, 
        frontend_container
    ):
        """Попытка пригласить участника с ролью viewer (нет прав)"""
        import uuid
        from core.utils.tokens import get_token_service
        from core.models.identity_models import User, Company
        
        # Создаем компанию
        company_id = f"test_company_{uuid.uuid4().hex[:8]}"
        company = Company(
            company_id=company_id,
            name="Test Company",
            owner_id="owner_user",
            members={"viewer_user": ["viewer"]}
        )
        await frontend_container.company_repository.set(company)
        
        # Создаем viewer пользователя
        user = User(
            user_id="viewer_user",
            name="Viewer User",
            companies={company_id: ["viewer"]},
            active_company_id=company_id
        )
        await frontend_container.user_repository.set(user)
        
        token_service = get_token_service()
        token = token_service.create_token("viewer_user", company_id=company_id)
        
        response = await frontend_client.post(
            "/frontend/api/team/invite",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email": "new@test.com",
                "role": "developer"
            }
        )
        
        assert response.status_code == 403

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
        from core.utils.tokens import get_token_service
        from core.models.identity_models import User
        
        token_service = get_token_service()
        token_data = token_service.validate_token(auth_headers["Authorization"].replace("Bearer ", ""))
        company_id = token_data.company_id
        
        company = await frontend_container.company_repository.get(company_id)
        
        # Добавляем участника для удаления
        test_user_id = "test_member_to_remove"
        company.members[test_user_id] = ["developer"]
        await frontend_container.company_repository.set(company)
        
        test_user = User(
            user_id=test_user_id,
            name="Test Member To Remove",
            companies={company_id: ["developer"]},
            active_company_id=company_id
        )
        await frontend_container.user_repository.set(test_user)
        
        # Удаляем
        response = await frontend_client.delete(
            f"/frontend/api/team/members/{test_user_id}",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        
        # Проверяем что участник действительно удален
        updated_company = await frontend_container.company_repository.get(company_id)
        assert test_user_id not in updated_company.members
        
        # Проверяем что у пользователя удалена компания
        updated_user = await frontend_container.user_repository.get(test_user_id)
        assert company_id not in updated_user.companies

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

