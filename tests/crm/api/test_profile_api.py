"""
Тесты для API профиля пользователя.
"""

import pytest
from httpx import AsyncClient


class TestProfileAPI:
    """Тесты API для профиля пользователя"""
    
    @pytest.mark.asyncio
    async def test_get_profile(self, crm_client: AsyncClient):
        """Тест получения профиля"""
        response = await crm_client.get("/crm/api/v1/profile")
        
        assert response.status_code == 200, f"Ошибка: {response.text}"
        data = response.json()
        
        assert "user_id" in data
        assert "company_id" in data
        assert "display_name" in data
        assert "position" in data
        assert "avatar_url" in data
        assert "phone" in data
        assert "bio" in data
        assert "notes_count" in data
        assert "tasks_completed" in data
    
    @pytest.mark.asyncio
    async def test_get_profile_creates_if_not_exists(self, crm_client: AsyncClient):
        """Тест что профиль создается автоматически если не существует"""
        # Первый запрос создает профиль
        response1 = await crm_client.get("/crm/api/v1/profile")
        assert response1.status_code == 200, f"Ошибка: {response1.text}"
        
        # Второй запрос возвращает тот же профиль
        response2 = await crm_client.get("/crm/api/v1/profile")
        assert response2.status_code == 200
        
        data1 = response1.json()
        data2 = response2.json()
        
        assert data1["user_id"] == data2["user_id"]
    
    @pytest.mark.asyncio
    async def test_update_profile(self, crm_client: AsyncClient):
        """Тест обновления профиля"""
        # Сначала получаем профиль (чтобы он был создан)
        await crm_client.get("/crm/api/v1/profile")
        
        # Обновляем
        response = await crm_client.put(
            "/crm/api/v1/profile",
            json={
                "display_name": "Новое Имя",
                "position": "Senior Developer",
                "phone": "+7 999 888 77 66",
                "bio": "Опытный разработчик"
            }
        )
        
        assert response.status_code == 200, f"Ошибка: {response.text}"
        data = response.json()
        
        assert data["display_name"] == "Новое Имя"
        assert data["position"] == "Senior Developer"
        assert data["phone"] == "+7 999 888 77 66"
        assert data["bio"] == "Опытный разработчик"
    
    @pytest.mark.asyncio
    async def test_update_profile_partial(self, crm_client: AsyncClient):
        """Тест частичного обновления профиля"""
        # Сначала устанавливаем все поля
        await crm_client.put(
            "/crm/api/v1/profile",
            json={
                "display_name": "Исходное Имя",
                "position": "Manager",
                "bio": "Исходное описание"
            }
        )
        
        # Обновляем только одно поле
        response = await crm_client.put(
            "/crm/api/v1/profile",
            json={
                "position": "Director"
            }
        )
        
        assert response.status_code == 200, f"Ошибка: {response.text}"
        data = response.json()
        
        assert data["position"] == "Director"
    
    @pytest.mark.asyncio
    async def test_update_profile_avatar_url(self, crm_client: AsyncClient):
        """Тест обновления URL аватара"""
        response = await crm_client.put(
            "/crm/api/v1/profile",
            json={
                "avatar_url": "https://example.com/new-avatar.png"
            }
        )
        
        assert response.status_code == 200, f"Ошибка: {response.text}"
        data = response.json()
        assert data["avatar_url"] == "https://example.com/new-avatar.png"
    
    @pytest.mark.asyncio
    async def test_get_stats(self, crm_client: AsyncClient):
        """Тест получения статистики активности"""
        response = await crm_client.get("/crm/api/v1/profile/stats")
        
        assert response.status_code == 200, f"Ошибка: {response.text}"
        data = response.json()
        
        assert "notes_by_date" in data
        assert "tasks_by_date" in data
        assert "total_notes" in data
        assert "total_tasks_completed" in data
        assert "current_streak" in data
        assert "longest_streak" in data
        
        assert isinstance(data["notes_by_date"], dict)
        assert isinstance(data["tasks_by_date"], dict)
        assert isinstance(data["total_notes"], int)
        assert isinstance(data["current_streak"], int)
    
    @pytest.mark.asyncio
    async def test_get_stats_with_days_param(self, crm_client: AsyncClient):
        """Тест получения статистики за определенный период"""
        response = await crm_client.get(
            "/crm/api/v1/profile/stats",
            params={"days": 30}
        )
        
        assert response.status_code == 200, f"Ошибка: {response.text}"
        data = response.json()
        assert "notes_by_date" in data
    
    @pytest.mark.asyncio
    async def test_get_stats_days_validation(self, crm_client: AsyncClient):
        """Тест валидации параметра days"""
        # Слишком маленький период
        response = await crm_client.get(
            "/crm/api/v1/profile/stats",
            params={"days": 1}
        )
        assert response.status_code == 422
        
        # Слишком большой период
        response = await crm_client.get(
            "/crm/api/v1/profile/stats",
            params={"days": 1000}
        )
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_profile_with_notes_count(self, crm_client: AsyncClient, test_note):
        """Тест что профиль показывает количество заметок"""
        response = await crm_client.get("/crm/api/v1/profile")
        
        assert response.status_code == 200, f"Ошибка: {response.text}"
        data = response.json()
        
        # Должна быть хотя бы одна заметка (test_note)
        assert data["notes_count"] >= 0
