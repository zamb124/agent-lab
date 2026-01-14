"""
Integration тесты для API управления API ключами.

Тесты БЕЗ моков - проверяем реальные HTTP запросы с реальной БД.
Проверяем создание, управление и отзыв API ключей.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient


@pytest.mark.asyncio
class TestApiKeysAPI:
    """Тесты для API управления API ключами"""

    async def test_list_api_keys_success(self, frontend_client: AsyncClient, auth_headers):
        """Получение списка API ключей"""
        response = await frontend_client.get(
            "/frontend/api/api-keys",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        keys = response.json()
        assert isinstance(keys, list)

    async def test_list_api_keys_unauthorized(self, frontend_client: AsyncClient):
        """Попытка получить ключи без авторизации"""
        response = await frontend_client.get("/frontend/api/api-keys")
        
        assert response.status_code == 401

    async def test_create_api_key_success(self, frontend_client: AsyncClient, auth_headers):
        """Создание нового API ключа"""
        response = await frontend_client.post(
            "/frontend/api/api-keys",
            headers=auth_headers,
            json={
                "name": "Test API Key",
                "scopes": ["agents:read", "agents:write"]
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "key_id" in data
        assert "secret" in data
        assert data["name"] == "Test API Key"
        assert "agents:read" in data["scopes"]
        assert "agents:write" in data["scopes"]
        
        # Проверяем что секрет начинается с "hum_"
        assert data["secret"].startswith("hum_")
        
        # Проверяем наличие предупреждения
        assert "больше не будет показан" in data["message"].lower()

    async def test_create_api_key_invalid_scope(
        self, 
        frontend_client: AsyncClient, 
        auth_headers
    ):
        """Создание ключа с недопустимым scope"""
        response = await frontend_client.post(
            "/frontend/api/api-keys",
            headers=auth_headers,
            json={
                "name": "Invalid Key",
                "scopes": ["invalid:scope"]
            }
        )
        
        assert response.status_code == 400
        assert "Недопустимый scope" in response.json()["detail"]

    async def test_create_api_key_multiple_scopes(
        self, 
        frontend_client: AsyncClient, 
        auth_headers
    ):
        """Создание ключа с несколькими scopes"""
        response = await frontend_client.post(
            "/frontend/api/api-keys",
            headers=auth_headers,
            json={
                "name": "Multi Scope Key",
                "scopes": [
                    "agents:read",
                    "agents:write",
                    "crm:read",
                    "rag:read"
                ]
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["scopes"]) == 4

    async def test_create_api_key_as_viewer_forbidden(
        self, 
        frontend_client: AsyncClient, 
        frontend_container
    ):
        """Попытка создать ключ с ролью viewer (нет прав)"""
        import uuid
        from core.utils.tokens import get_token_service
        from core.models.identity_models import User, Company
        
        company_id = f"test_company_{uuid.uuid4().hex[:8]}"
        company = Company(
            company_id=company_id,
            name="Test Company",
            owner_id="owner_user",
            members={"viewer_user": ["viewer"]}
        )
        await frontend_container.company_repository.set(company)
        
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
            "/frontend/api/api-keys",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Test Key",
                "scopes": ["agents:read"]
            }
        )
        
        assert response.status_code == 403

    async def test_update_api_key_name(
        self, 
        frontend_client: AsyncClient, 
        auth_headers
    ):
        """Обновление названия API ключа"""
        # Сначала создаем ключ
        create_response = await frontend_client.post(
            "/frontend/api/api-keys",
            headers=auth_headers,
            json={
                "name": "Original Name",
                "scopes": ["agents:read"]
            }
        )
        
        assert create_response.status_code == 200
        key_id = create_response.json()["key_id"]
        
        # Обновляем название
        update_response = await frontend_client.patch(
            f"/frontend/api/api-keys/{key_id}",
            headers=auth_headers,
            json={"name": "Updated Name"}
        )
        
        assert update_response.status_code == 200
        data = update_response.json()
        assert data["success"] is True
        assert data["name"] == "Updated Name"

    async def test_revoke_api_key_success(
        self, 
        frontend_client: AsyncClient, 
        auth_headers
    ):
        """Отзыв API ключа"""
        # Создаем ключ
        create_response = await frontend_client.post(
            "/frontend/api/api-keys",
            headers=auth_headers,
            json={
                "name": "Key To Revoke",
                "scopes": ["agents:read"]
            }
        )
        
        assert create_response.status_code == 200
        key_id = create_response.json()["key_id"]
        
        # Отзываем ключ
        revoke_response = await frontend_client.delete(
            f"/frontend/api/api-keys/{key_id}",
            headers=auth_headers
        )
        
        assert revoke_response.status_code == 200
        data = revoke_response.json()
        assert data["success"] is True
        assert "отозван" in data["message"].lower()

    async def test_api_key_uniqueness(
        self, 
        frontend_client: AsyncClient, 
        auth_headers
    ):
        """Проверка уникальности сгенерированных ключей"""
        # Создаем несколько ключей
        secrets = []
        
        for i in range(3):
            response = await frontend_client.post(
                "/frontend/api/api-keys",
                headers=auth_headers,
                json={
                    "name": f"Key {i}",
                    "scopes": ["agents:read"]
                }
            )
            
            assert response.status_code == 200
            secret = response.json()["secret"]
            secrets.append(secret)
        
        # Все ключи должны быть уникальными
        assert len(secrets) == len(set(secrets))
        
        # Все должны иметь правильный префикс
        for secret in secrets:
            assert secret.startswith("hum_")
            assert len(secret) > 40  # Достаточная длина для безопасности

    async def test_api_key_scopes_validation(
        self, 
        frontend_client: AsyncClient, 
        auth_headers
    ):
        """Проверка валидации всех допустимых scopes"""
        valid_scopes = [
            "agents:read",
            "agents:write",
            "crm:read",
            "crm:write",
            "rag:read",
            "rag:write",
            "billing:read"
        ]
        
        response = await frontend_client.post(
            "/frontend/api/api-keys",
            headers=auth_headers,
            json={
                "name": "Full Scope Key",
                "scopes": valid_scopes
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["scopes"]) == len(valid_scopes)
        
        for scope in valid_scopes:
            assert scope in data["scopes"]

    async def test_api_key_empty_scopes(
        self, 
        frontend_client: AsyncClient, 
        auth_headers
    ):
        """Создание ключа с пустым списком scopes"""
        response = await frontend_client.post(
            "/frontend/api/api-keys",
            headers=auth_headers,
            json={
                "name": "No Scope Key",
                "scopes": []
            }
        )
        
        # Должен успешно создаться с пустыми правами
        assert response.status_code == 200
        data = response.json()
        assert data["scopes"] == []

    async def test_api_key_isolation_between_companies(
        self, 
        frontend_client: AsyncClient, 
        frontend_container
    ):
        """Проверка изоляции API ключей между компаниями"""
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
            members={"user1": ["owner"]}
        )
        company2 = Company(
            company_id=company2_id,
            name="Company 2",
            owner_id="user2",
            members={"user2": ["owner"]}
        )
        
        await frontend_container.company_repository.set(company1)
        await frontend_container.company_repository.set(company2)
        
        user1 = User(
            user_id="user1",
            name="User 1",
            companies={company1_id: ["owner"]},
            active_company_id=company1_id
        )
        user2 = User(
            user_id="user2",
            name="User 2",
            companies={company2_id: ["owner"]},
            active_company_id=company2_id
        )
        
        await frontend_container.user_repository.set(user1)
        await frontend_container.user_repository.set(user2)
        
        token_service = get_token_service()
        token1 = token_service.create_token("user1", company_id=company1_id)
        token2 = token_service.create_token("user2", company_id=company2_id)
        
        # Company1 создает ключ
        response1 = await frontend_client.post(
            "/frontend/api/api-keys",
            headers={"Authorization": f"Bearer {token1}"},
            json={
                "name": "Company 1 Key",
                "scopes": ["agents:read"]
            }
        )
        assert response1.status_code == 200
        
        # Company2 не должна видеть ключи Company1
        response2 = await frontend_client.get(
            "/frontend/api/api-keys",
            headers={"Authorization": f"Bearer {token2}"}
        )
        
        assert response2.status_code == 200
        keys = response2.json()
        
        # Список ключей company2 должен быть пустым
        assert len(keys) == 0

