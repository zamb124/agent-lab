"""
Репозиторий для задач CRM.
Работает с SQLAlchemy напрямую для эффективной фильтрации по статусу/приоритету.
"""

import logging
from datetime import date
from typing import List, Type, Optional

from sqlalchemy import select, and_, or_, desc, asc, func

from apps.crm.db.base import BaseCRMRepository, CRMDatabase
from apps.crm.db.models import Task

logger = logging.getLogger(__name__)


class TaskRepository(BaseCRMRepository[Task]):
    """
    Репозиторий для задач.
    Использует индексы по status, priority, due_date.
    """
    
    def __init__(self, db: CRMDatabase):
        super().__init__(db)
    
    @property
    def model_class(self) -> Type[Task]:
        return Task
    
    @property
    def id_field(self) -> str:
        return "task_id"
    
    async def get_by_company(
        self, 
        company_id: str, 
        limit: int = 100, 
        offset: int = 0
    ) -> List[Task]:
        """Получает задачи компании с пагинацией"""
        async with self._db.session() as session:
            stmt = (
                select(Task)
                .where(Task.company_id == company_id)
                .order_by(desc(Task.created_at))
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def get_by_user(
        self, 
        company_id: str, 
        user_id: str,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[Task]:
        """Получает задачи пользователя с опциональной фильтрацией по статусу"""
        async with self._db.session() as session:
            conditions = [
                Task.company_id == company_id,
                Task.user_id == user_id
            ]
            if status:
                conditions.append(Task.status == status)
            
            stmt = (
                select(Task)
                .where(and_(*conditions))
                .order_by(asc(Task.due_date.is_(None)), asc(Task.due_date))
                .limit(limit)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def get_by_status(
        self, 
        company_id: str, 
        status: str,
        limit: int = 100
    ) -> List[Task]:
        """Получает задачи с определенным статусом"""
        async with self._db.session() as session:
            stmt = (
                select(Task)
                .where(
                    and_(
                        Task.company_id == company_id,
                        Task.status == status
                    )
                )
                .order_by(asc(Task.due_date.is_(None)), asc(Task.due_date))
                .limit(limit)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def get_by_priority(
        self, 
        company_id: str, 
        priority: str,
        limit: int = 100
    ) -> List[Task]:
        """Получает задачи с определенным приоритетом"""
        async with self._db.session() as session:
            stmt = (
                select(Task)
                .where(
                    and_(
                        Task.company_id == company_id,
                        Task.priority == priority
                    )
                )
                .order_by(asc(Task.due_date.is_(None)), asc(Task.due_date))
                .limit(limit)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def get_overdue(self, company_id: str) -> List[Task]:
        """Получает просроченные задачи"""
        today = date.today()
        async with self._db.session() as session:
            stmt = (
                select(Task)
                .where(
                    and_(
                        Task.company_id == company_id,
                        Task.due_date < today,
                        Task.status.not_in(["completed", "cancelled"])
                    )
                )
                .order_by(asc(Task.due_date))
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def get_due_today(self, company_id: str) -> List[Task]:
        """Получает задачи с дедлайном сегодня"""
        today = date.today()
        async with self._db.session() as session:
            stmt = (
                select(Task)
                .where(
                    and_(
                        Task.company_id == company_id,
                        Task.due_date == today,
                        Task.status.not_in(["completed", "cancelled"])
                    )
                )
                .order_by(desc(Task.priority))
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def get_due_this_week(self, company_id: str) -> List[Task]:
        """Получает задачи на эту неделю"""
        from datetime import timedelta
        today = date.today()
        week_end = today + timedelta(days=7)
        
        async with self._db.session() as session:
            stmt = (
                select(Task)
                .where(
                    and_(
                        Task.company_id == company_id,
                        Task.due_date >= today,
                        Task.due_date <= week_end,
                        Task.status.not_in(["completed", "cancelled"])
                    )
                )
                .order_by(asc(Task.due_date))
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def get_by_entity(
        self, 
        company_id: str, 
        entity_id: str
    ) -> List[Task]:
        """Получает задачи, связанные с сущностью"""
        async with self._db.session() as session:
            stmt = (
                select(Task)
                .where(
                    and_(
                        Task.company_id == company_id,
                        Task.linked_entity_id == entity_id
                    )
                )
                .order_by(asc(Task.due_date.is_(None)), asc(Task.due_date))
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def count_by_status(self, company_id: str) -> dict:
        """Считает задачи по статусам"""
        async with self._db.session() as session:
            stmt = (
                select(Task.status, func.count(Task.task_id))
                .where(Task.company_id == company_id)
                .group_by(Task.status)
            )
            result = await session.execute(stmt)
            return {row[0]: row[1] for row in result.all()}
    
    async def get_by_tag(
        self, 
        company_id: str, 
        tag: str,
        limit: int = 100
    ) -> List[Task]:
        """Получает задачи по тегу"""
        async with self._db.session() as session:
            stmt = (
                select(Task)
                .where(
                    and_(
                        Task.company_id == company_id,
                        Task.tags.contains([tag])
                    )
                )
                .order_by(asc(Task.due_date.is_(None)), asc(Task.due_date))
                .limit(limit)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def get_by_assignee(
        self, 
        company_id: str, 
        assignee_id: str,
        limit: int = 100
    ) -> List[Task]:
        """Получает задачи по соучастнику"""
        async with self._db.session() as session:
            stmt = (
                select(Task)
                .where(
                    and_(
                        Task.company_id == company_id,
                        Task.assignees.contains([assignee_id])
                    )
                )
                .order_by(asc(Task.due_date.is_(None)), asc(Task.due_date))
                .limit(limit)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())