"""
NoteService - управление заметками CRM (Daily Notes).
"""

import logging
import uuid
from datetime import date, datetime, timezone
from typing import List, Optional

from core.context import get_context
from apps.crm.db.models import Note
from apps.crm.db.repositories.note_repository import NoteRepository
from apps.crm.services.entity_service import EntityService
from apps.crm.models.note_models import (
    NoteCreate,
    NoteUpdate,
    NoteResponse,
    NoteAnalyzeRequest,
    NoteAnalyzeResponse,
)

logger = logging.getLogger(__name__)


class NoteService:
    """
    Сервис для работы с заметками (Daily Notes).
    
    Заметки хранятся в PostgreSQL с индексами по дате.
    AI анализ делегируется в apps/agents через AgentsClient.
    """
    
    def __init__(
        self,
        note_repository: NoteRepository,
        entity_service: EntityService,
        agents_client,
    ):
        self._repo = note_repository
        self._entity_service = entity_service
        self._agents_client = agents_client
    
    def _get_company_id(self) -> str:
        """Получает company_id из контекста"""
        context = get_context()
        if not context or not context.active_company:
            raise ValueError("Нет активной компании в контексте")
        return context.active_company.company_id
    
    def _get_user_id(self) -> str:
        """Получает user_id из контекста"""
        context = get_context()
        if not context or not context.user:
            raise ValueError("Нет пользователя в контексте")
        return context.user.user_id
    
    async def create_note(
        self, 
        data: NoteCreate,
        company_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> NoteResponse:
        """Создает новую заметку"""
        company_id = company_id or self._get_company_id()
        user_id = user_id or self._get_user_id()
        
        note = Note(
            note_id=str(uuid.uuid4()),
            company_id=company_id,
            user_id=user_id,
            title=data.title,
            content=data.content,
            note_type=data.note_type.value,
            note_date=data.note_date,
            ai_summary=None,
            linked_entity_ids=data.linked_entity_ids,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        
        await self._repo.create(note)
        logger.info(f"Создана заметка: {note.note_id}")
        
        return self._to_response(note)
    
    async def get_note(
        self, 
        note_id: str,
        company_id: Optional[str] = None
    ) -> Optional[NoteResponse]:
        """Получает заметку по ID"""
        note = await self._repo.get(note_id)
        if not note:
            return None
        return self._to_response(note)
    
    async def update_note(
        self, 
        note_id: str,
        data: NoteUpdate,
        company_id: Optional[str] = None
    ) -> Optional[NoteResponse]:
        """Обновляет заметку"""
        note = await self._repo.get(note_id)
        if not note:
            return None
        
        if data.title is not None:
            note.title = data.title
        if data.content is not None:
            note.content = data.content
        if data.note_type is not None:
            note.note_type = data.note_type.value
        if data.note_date is not None:
            note.note_date = data.note_date
        if data.linked_entity_ids is not None:
            note.linked_entity_ids = data.linked_entity_ids
        
        note.updated_at = datetime.now(timezone.utc)
        
        await self._repo.update(note)
        logger.info(f"Обновлена заметка: {note_id}")
        
        return self._to_response(note)
    
    async def delete_note(
        self, 
        note_id: str,
        company_id: Optional[str] = None
    ) -> bool:
        """Удаляет заметку"""
        success = await self._repo.delete(note_id)
        if success:
            logger.info(f"Удалена заметка: {note_id}")
        return success
    
    async def get_daily_notes(
        self,
        note_date: date,
        company_id: Optional[str] = None
    ) -> List[NoteResponse]:
        """Получает заметки за определенную дату"""
        company_id = company_id or self._get_company_id()
        
        notes = await self._repo.get_by_date(company_id, note_date)
        return [self._to_response(note) for note in notes]
    
    async def get_notes_in_range(
        self,
        start_date: date,
        end_date: date,
        company_id: Optional[str] = None
    ) -> List[NoteResponse]:
        """Получает заметки за диапазон дат"""
        company_id = company_id or self._get_company_id()
        
        notes = await self._repo.get_by_date_range(company_id, start_date, end_date)
        return [self._to_response(note) for note in notes]
    
    async def list_notes(
        self,
        note_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        company_id: Optional[str] = None
    ) -> List[NoteResponse]:
        """Получает список заметок с фильтрацией"""
        company_id = company_id or self._get_company_id()
        
        if note_type:
            notes = await self._repo.get_by_type(company_id, note_type, limit)
        else:
            notes = await self._repo.get_by_company(company_id, limit, offset)
        
        return [self._to_response(note) for note in notes]
    
    async def search_notes(
        self,
        search_text: str,
        limit: int = 50,
        company_id: Optional[str] = None
    ) -> List[NoteResponse]:
        """Поиск по содержимому заметок"""
        company_id = company_id or self._get_company_id()
        
        notes = await self._repo.search_by_content(company_id, search_text, limit)
        return [self._to_response(note) for note in notes]
    
    async def get_notes_by_entity(
        self,
        entity_id: str,
        company_id: Optional[str] = None
    ) -> List[NoteResponse]:
        """Получает заметки, связанные с сущностью"""
        company_id = company_id or self._get_company_id()
        
        notes = await self._repo.get_linked_to_entity(company_id, entity_id)
        return [self._to_response(note) for note in notes]
    
    async def analyze_note(
        self,
        note_id: str,
        request: NoteAnalyzeRequest,
        company_id: Optional[str] = None
    ) -> NoteAnalyzeResponse:
        """
        Анализирует заметку с помощью AI.
        
        - Извлечение сущностей
        - Генерация резюме
        - Создание задач
        """
        company_id = company_id or self._get_company_id()
        
        note = await self._repo.get(note_id)
        if not note:
            raise ValueError(f"Заметка {note_id} не найдена")
        
        result = NoteAnalyzeResponse(
            summary=None,
            extracted_entities=[],
            extracted_relationships=[],
            created_tasks=[],
        )
        
        if request.extract_entities or request.generate_summary:
            ai_result = await self._agents_client.extract_entities(
                text=note.content,
                generate_summary=request.generate_summary,
            )
            
            if request.generate_summary and ai_result.get("summary"):
                result.summary = ai_result["summary"]
                
                note.ai_summary = result.summary
                await self._repo.update(note)
            
            if request.extract_entities:
                result.extracted_entities = ai_result.get("entities", [])
                result.extracted_relationships = ai_result.get("relationships", [])
        
        return result
    
    async def link_entity_to_note(
        self,
        note_id: str,
        entity_id: str,
        company_id: Optional[str] = None
    ) -> NoteResponse:
        """Связывает сущность с заметкой"""
        note = await self._repo.get(note_id)
        if not note:
            raise ValueError(f"Заметка {note_id} не найдена")
        
        if entity_id not in (note.linked_entity_ids or []):
            note.linked_entity_ids = (note.linked_entity_ids or []) + [entity_id]
            note.updated_at = datetime.now(timezone.utc)
            await self._repo.update(note)
        
        return self._to_response(note)
    
    async def unlink_entity_from_note(
        self,
        note_id: str,
        entity_id: str,
        company_id: Optional[str] = None
    ) -> NoteResponse:
        """Убирает связь сущности с заметкой"""
        note = await self._repo.get(note_id)
        if not note:
            raise ValueError(f"Заметка {note_id} не найдена")
        
        if entity_id in (note.linked_entity_ids or []):
            note.linked_entity_ids = [eid for eid in note.linked_entity_ids if eid != entity_id]
            note.updated_at = datetime.now(timezone.utc)
            await self._repo.update(note)
        
        return self._to_response(note)
    
    def _to_response(self, note: Note) -> NoteResponse:
        """Конвертирует модель в response"""
        return NoteResponse(
            note_id=note.note_id,
            company_id=note.company_id,
            user_id=note.user_id,
            title=note.title,
            content=note.content,
            note_type=note.note_type,
            note_date=note.note_date,
            ai_summary=note.ai_summary,
            linked_entity_ids=note.linked_entity_ids or [],
            created_at=note.created_at,
            updated_at=note.updated_at,
        )


