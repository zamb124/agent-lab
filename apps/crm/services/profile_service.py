"""
ProfileService - управление профилями пользователей CRM.
"""

import logging
import uuid
from datetime import date, timedelta
from typing import Optional

from core.context import get_context

from apps.crm.db.repositories.profile_repository import ProfileRepository
from apps.crm.db.repositories.note_repository import NoteRepository
from apps.crm.db.repositories.task_repository import TaskRepository
from apps.crm.db.models import UserProfile
from apps.crm.models.profile_models import (
    UserProfileCreate,
    UserProfileResponse,
    UserStatsResponse,
)

logger = logging.getLogger(__name__)


class ProfileService:
    """
    Сервис для работы с профилями пользователей.
    """
    
    def __init__(
        self,
        profile_repository: ProfileRepository,
        note_repository: NoteRepository,
        task_repository: TaskRepository,
    ):
        self._profile_repo = profile_repository
        self._note_repo = note_repository
        self._task_repo = task_repository
    
    def _get_user_id(self) -> str:
        """Получает ID текущего пользователя"""
        context = get_context()
        if not context or not context.user:
            raise ValueError("Нет пользователя в контексте")
        return context.user.user_id
    
    def _get_company_id(self) -> str:
        """Получает ID текущей компании"""
        context = get_context()
        if not context or not context.active_company:
            raise ValueError("Нет активной компании в контексте")
        return context.active_company.company_id
    
    async def get_profile(self, user_id: Optional[str] = None) -> UserProfileResponse:
        """
        Получает профиль пользователя.
        Если профиль не существует - создает пустой.
        """
        user_id = user_id or self._get_user_id()
        company_id = self._get_company_id()
        
        profile = await self._profile_repo.get_by_user_company(user_id, company_id)
        
        if not profile:
            # Создаем пустой профиль
            profile = await self._create_default_profile(user_id, company_id)
        
        return await self._to_response(profile)
    
    async def _create_default_profile(self, user_id: str, company_id: str) -> UserProfile:
        """Создает профиль по умолчанию"""
        context = get_context()
        display_name = context.user.name if context and context.user else None
        
        profile = UserProfile(
            profile_id=str(uuid.uuid4()),
            user_id=user_id,
            company_id=company_id,
            display_name=display_name,
        )
        return await self._profile_repo.create(profile)
    
    async def update_profile(self, data: UserProfileCreate) -> UserProfileResponse:
        """Обновляет профиль текущего пользователя"""
        user_id = self._get_user_id()
        company_id = self._get_company_id()
        
        profile = await self._profile_repo.get_by_user_company(user_id, company_id)
        
        if not profile:
            profile = await self._create_default_profile(user_id, company_id)
        
        # Обновляем поля
        update_data = data.model_dump(exclude_unset=True)
        if update_data:
            profile = await self._profile_repo.update(profile.profile_id, **update_data)
        
        logger.info(f"Профиль обновлен: {user_id}")
        return await self._to_response(profile)
    
    async def get_stats(self, days: int = 365) -> UserStatsResponse:
        """
        Получает статистику активности пользователя.
        Используется для графика продуктивности.
        """
        user_id = self._get_user_id()
        company_id = self._get_company_id()
        
        # Получаем заметки за период
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        notes = await self._note_repo.filter_notes(
            company_id=company_id,
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            is_template=False,
        )
        
        # Группируем по датам
        notes_by_date = {}
        for note in notes:
            note_date = note.note_date.isoformat()
            notes_by_date[note_date] = notes_by_date.get(note_date, 0) + 1
        
        # Получаем завершенные задачи
        tasks = await self._task_repo.get_by_user(
            company_id=company_id,
            user_id=user_id,
            status="completed"
        )
        
        tasks_by_date = {}
        for task in tasks:
            if task.updated_at:
                task_date = task.updated_at.date().isoformat()
                tasks_by_date[task_date] = tasks_by_date.get(task_date, 0) + 1
        
        # Вычисляем streak
        current_streak, longest_streak = self._calculate_streaks(notes_by_date, end_date)
        
        return UserStatsResponse(
            notes_by_date=notes_by_date,
            tasks_by_date=tasks_by_date,
            total_notes=len(notes),
            total_tasks_completed=len(tasks),
            current_streak=current_streak,
            longest_streak=longest_streak,
        )
    
    def _calculate_streaks(self, notes_by_date: dict, end_date: date) -> tuple:
        """Вычисляет текущую и максимальную серию дней"""
        current_streak = 0
        longest_streak = 0
        temp_streak = 0
        
        # Проверяем последние 365 дней
        check_date = end_date
        while True:
            date_str = check_date.isoformat()
            if notes_by_date.get(date_str, 0) > 0:
                temp_streak += 1
                if check_date == end_date or current_streak > 0:
                    current_streak += 1
            else:
                if temp_streak > longest_streak:
                    longest_streak = temp_streak
                temp_streak = 0
                if check_date != end_date:
                    current_streak = 0
            
            check_date -= timedelta(days=1)
            if check_date < end_date - timedelta(days=365):
                break
        
        if temp_streak > longest_streak:
            longest_streak = temp_streak
        
        return current_streak, longest_streak
    
    async def _to_response(self, profile: UserProfile) -> UserProfileResponse:
        """Конвертирует модель в response с статистикой"""
        company_id = self._get_company_id()
        
        # Получаем статистику через filter_notes
        notes = await self._note_repo.filter_notes(
            company_id=company_id,
            user_id=profile.user_id,
            is_template=False,
            limit=1000
        )
        
        tasks = await self._task_repo.get_by_user(
            company_id=company_id,
            user_id=profile.user_id,
            status="completed"
        )
        
        return UserProfileResponse(
            user_id=profile.user_id,
            company_id=profile.company_id,
            display_name=profile.display_name,
            position=profile.position,
            avatar_url=profile.avatar_url,
            phone=profile.phone,
            bio=profile.bio,
            telegram_username=getattr(profile, 'telegram_username', None),
            sidebar_config=getattr(profile, 'sidebar_config', {}) or {},
            widget_config=getattr(profile, 'widget_config', {}) or {},
            created_at=profile.created_at,
            updated_at=profile.updated_at,
            notes_count=len(notes),
            tasks_completed=len(tasks),
            entities_created=0,
        )
    
    async def link_telegram(self, telegram_username: str) -> "TelegramLinkResponse":
        """Привязывает Telegram username к профилю пользователя"""
        from apps.crm.models.profile_models import TelegramLinkResponse
        
        user_id = self._get_user_id()
        company_id = self._get_company_id()
        
        # Нормализуем username
        username = telegram_username.lstrip("@").lower()
        
        profile = await self._profile_repo.get_by_user_company(user_id, company_id)
        if not profile:
            profile = await self._create_default_profile(user_id, company_id)
        
        # Обновляем telegram_username
        await self._profile_repo.update(profile.profile_id, telegram_username=username)
        
        logger.info(f"Telegram @{username} привязан к пользователю {user_id}")
        
        return TelegramLinkResponse(
            linked=True,
            telegram_username=username
        )
    
    async def unlink_telegram(self) -> "TelegramLinkResponse":
        """Отвязывает Telegram от профиля"""
        from apps.crm.models.profile_models import TelegramLinkResponse
        
        user_id = self._get_user_id()
        company_id = self._get_company_id()
        
        profile = await self._profile_repo.get_by_user_company(user_id, company_id)
        if profile:
            await self._profile_repo.update(profile.profile_id, telegram_username=None)
            logger.info(f"Telegram отвязан от пользователя {user_id}")
        
        return TelegramLinkResponse(linked=False, telegram_username=None)
    
    async def get_user_by_telegram(self, telegram_username: str) -> Optional[str]:
        """
        Находит user_id по telegram username.
        Используется при обработке Telegram сообщений.
        """
        company_id = self._get_company_id()
        profile = await self._profile_repo.get_by_telegram_username(company_id, telegram_username)
        return profile.user_id if profile else None

