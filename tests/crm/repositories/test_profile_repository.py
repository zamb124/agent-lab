"""
Тесты для ProfileRepository.
"""

import pytest
import uuid

from apps.crm.db.models import UserProfile


@pytest.fixture
def profile_repository(crm_container):
    """Fixture для ProfileRepository"""
    return crm_container.profile_repository


@pytest.fixture
async def sample_profile(profile_repository, test_company_id):
    """Создает тестовый профиль с уникальным user_id"""
    unique_user_id = f"profile_user_{uuid.uuid4().hex[:8]}"
    profile = UserProfile(
        profile_id=str(uuid.uuid4()),
        user_id=unique_user_id,
        company_id=test_company_id,
        display_name="Тестовый Пользователь",
        position="Менеджер",
        avatar_url="https://example.com/avatar.jpg",
        phone="+7 999 123 45 67",
        bio="Опытный специалист"
    )
    return await profile_repository.create(profile)


class TestProfileRepository:
    """Тесты ProfileRepository"""
    
    @pytest.mark.asyncio
    async def test_create_profile(self, profile_repository, test_company_id):
        """Тест создания профиля"""
        user_id = f"user_{uuid.uuid4().hex[:8]}"
        profile = UserProfile(
            profile_id=str(uuid.uuid4()),
            user_id=user_id,
            company_id=test_company_id,
            display_name="Новый Пользователь",
            position="Аналитик"
        )
        
        created = await profile_repository.create(profile)
        
        assert created.profile_id == profile.profile_id
        assert created.user_id == user_id
        assert created.display_name == "Новый Пользователь"
        assert created.position == "Аналитик"
    
    @pytest.mark.asyncio
    async def test_get_profile(self, profile_repository, sample_profile):
        """Тест получения профиля по ID"""
        fetched = await profile_repository.get(sample_profile.profile_id)
        
        assert fetched is not None
        assert fetched.profile_id == sample_profile.profile_id
        assert fetched.display_name == sample_profile.display_name
    
    @pytest.mark.asyncio
    async def test_get_by_user_company(self, profile_repository, sample_profile, test_company_id):
        """Тест получения профиля по user_id и company_id"""
        fetched = await profile_repository.get_by_user_company(
            user_id=sample_profile.user_id,
            company_id=test_company_id
        )
        
        assert fetched is not None
        assert fetched.user_id == sample_profile.user_id
        assert fetched.company_id == test_company_id
    
    @pytest.mark.asyncio
    async def test_get_by_user_company_not_found(self, profile_repository):
        """Тест получения несуществующего профиля"""
        fetched = await profile_repository.get_by_user_company(
            user_id="nonexistent_user",
            company_id="nonexistent_company"
        )
        
        assert fetched is None
    
    @pytest.mark.asyncio
    async def test_update_profile(self, profile_repository, sample_profile):
        """Тест обновления профиля"""
        updated = await profile_repository.update(
            sample_profile.profile_id,
            display_name="Обновленное Имя",
            position="Директор",
            phone="+7 999 999 99 99"
        )
        
        assert updated is not None
        assert updated.display_name == "Обновленное Имя"
        assert updated.position == "Директор"
        assert updated.phone == "+7 999 999 99 99"
        # Остальные поля не изменились
        assert updated.bio == sample_profile.bio
    
    @pytest.mark.asyncio
    async def test_update_profile_partial(self, profile_repository, sample_profile):
        """Тест частичного обновления профиля"""
        original_position = sample_profile.position
        
        updated = await profile_repository.update(
            sample_profile.profile_id,
            bio="Новое описание"
        )
        
        assert updated is not None
        assert updated.bio == "Новое описание"
        assert updated.position == original_position  # Не изменилось
    
    @pytest.mark.asyncio
    async def test_update_nonexistent_profile(self, profile_repository):
        """Тест обновления несуществующего профиля"""
        result = await profile_repository.update(
            "nonexistent_profile_id",
            display_name="Test"
        )
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_profile_with_null_fields(self, profile_repository, test_company_id):
        """Тест создания профиля с пустыми полями"""
        user_id = f"user_{uuid.uuid4().hex[:8]}"
        profile = UserProfile(
            profile_id=str(uuid.uuid4()),
            user_id=user_id,
            company_id=test_company_id
            # Все остальные поля None
        )
        
        created = await profile_repository.create(profile)
        
        assert created.profile_id is not None
        assert created.display_name is None
        assert created.position is None
        assert created.avatar_url is None
        assert created.phone is None
        assert created.bio is None

