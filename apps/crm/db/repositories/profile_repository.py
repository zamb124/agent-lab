"""
Репозиторий для профилей пользователей.
"""

from typing import Optional, Type

from sqlalchemy import select

from apps.crm.db.base import BaseCRMRepository, CRMDatabase
from apps.crm.db.models import UserProfile


class ProfileRepository(BaseCRMRepository[UserProfile]):
    """
    Репозиторий для работы с профилями пользователей.
    """
    
    def __init__(self, db: CRMDatabase):
        super().__init__(db)
    
    @property
    def model_class(self) -> Type[UserProfile]:
        return UserProfile
    
    @property
    def id_field(self) -> str:
        return "profile_id"
    
    async def get_by_user_company(
        self,
        user_id: str,
        company_id: str
    ) -> Optional[UserProfile]:
        """Получает профиль по user_id и company_id"""
        async with self._db.session() as session:
            stmt = select(UserProfile).where(
                UserProfile.user_id == user_id,
                UserProfile.company_id == company_id
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
    
    async def create(self, profile: UserProfile) -> UserProfile:
        """Создает профиль"""
        async with self._db.session() as session:
            session.add(profile)
            await session.commit()
            await session.refresh(profile)
            return profile
    
    async def update(
        self,
        profile_id: str,
        **kwargs
    ) -> Optional[UserProfile]:
        """Обновляет профиль"""
        async with self._db.session() as session:
            stmt = select(UserProfile).where(
                UserProfile.profile_id == profile_id
            )
            result = await session.execute(stmt)
            profile = result.scalar_one_or_none()
            
            if not profile:
                return None
            
            for key, value in kwargs.items():
                if hasattr(profile, key) and value is not None:
                    setattr(profile, key, value)
            
            await session.commit()
            await session.refresh(profile)
            return profile
    
    async def get_by_telegram_username(
        self,
        company_id: str,
        telegram_username: str
    ) -> Optional[UserProfile]:
        """Находит профиль по Telegram username в рамках компании"""
        # Убираем @ если есть
        username = telegram_username.lstrip("@").lower()
        
        async with self._db.session() as session:
            stmt = select(UserProfile).where(
                UserProfile.company_id == company_id,
                UserProfile.telegram_username == username
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

