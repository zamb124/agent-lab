"""
Репозиторий для заметок CRM (Daily Notes).
Работает с SQLAlchemy напрямую для эффективных запросов по датам.
"""

import logging
from datetime import date
from typing import List, Type, Optional

from sqlalchemy import select, and_, desc

from apps.crm.db.base import BaseCRMRepository, CRMDatabase
from apps.crm.db.models import Note

logger = logging.getLogger(__name__)


class NoteRepository(BaseCRMRepository[Note]):
    """
    Репозиторий для заметок.
    Использует индексы по дате для быстрого поиска Daily Notes.
    """
    
    def __init__(self, db: CRMDatabase):
        super().__init__(db)
    
    @property
    def model_class(self) -> Type[Note]:
        return Note
    
    @property
    def id_field(self) -> str:
        return "note_id"
    
    async def get_by_company(
        self, 
        company_id: str, 
        limit: int = 100, 
        offset: int = 0
    ) -> List[Note]:
        """Получает заметки компании с пагинацией"""
        async with self._db.session() as session:
            stmt = (
                select(Note)
                .where(Note.company_id == company_id)
                .order_by(desc(Note.note_date))
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def get_by_date(
        self, 
        company_id: str, 
        note_date: date
    ) -> List[Note]:
        """Получает все заметки за определенную дату"""
        async with self._db.session() as session:
            stmt = (
                select(Note)
                .where(
                    and_(
                        Note.company_id == company_id,
                        Note.note_date == note_date
                    )
                )
                .order_by(desc(Note.created_at))
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def get_by_date_range(
        self, 
        company_id: str, 
        start_date: date, 
        end_date: date,
        limit: int = 1000
    ) -> List[Note]:
        """Получает заметки за диапазон дат"""
        async with self._db.session() as session:
            stmt = (
                select(Note)
                .where(
                    and_(
                        Note.company_id == company_id,
                        Note.note_date >= start_date,
                        Note.note_date <= end_date
                    )
                )
                .order_by(desc(Note.note_date))
                .limit(limit)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def get_by_user(
        self, 
        company_id: str, 
        user_id: str,
        limit: int = 100
    ) -> List[Note]:
        """Получает все заметки пользователя"""
        async with self._db.session() as session:
            stmt = (
                select(Note)
                .where(
                    and_(
                        Note.company_id == company_id,
                        Note.user_id == user_id
                    )
                )
                .order_by(desc(Note.note_date))
                .limit(limit)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def get_by_type(
        self, 
        company_id: str, 
        note_type: str,
        limit: int = 100
    ) -> List[Note]:
        """Получает заметки определенного типа"""
        async with self._db.session() as session:
            stmt = (
                select(Note)
                .where(
                    and_(
                        Note.company_id == company_id,
                        Note.note_type == note_type
                    )
                )
                .order_by(desc(Note.note_date))
                .limit(limit)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def search_by_content(
        self, 
        company_id: str, 
        search_text: str,
        limit: int = 50
    ) -> List[Note]:
        """Поиск по содержимому заметок (ILIKE)"""
        async with self._db.session() as session:
            stmt = (
                select(Note)
                .where(
                    and_(
                        Note.company_id == company_id,
                        Note.content.ilike(f"%{search_text}%")
                    )
                )
                .order_by(desc(Note.note_date))
                .limit(limit)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def get_linked_to_entity(
        self, 
        company_id: str, 
        entity_id: str
    ) -> List[Note]:
        """
        Получает заметки, связанные с сущностью.
        Использует JSONB contains для поиска по массиву linked_entity_ids.
        """
        async with self._db.session() as session:
            stmt = (
                select(Note)
                .where(
                    and_(
                        Note.company_id == company_id,
                        Note.linked_entity_ids.contains([entity_id])
                    )
                )
                .order_by(desc(Note.note_date))
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
