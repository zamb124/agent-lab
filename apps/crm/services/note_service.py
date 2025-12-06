"""
NoteService - управление заметками CRM (Daily Notes).
"""

import logging
import uuid
from datetime import date, datetime, timezone
from typing import List, Optional

from core.context import get_context
from core.files import get_default_file_processor
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
from apps.crm.tasks import (
    process_crm_attachment_task,
    delete_crm_attachment_task,
    delete_note_attachments_task,
    import_note_from_file_task,
)
from apps.crm.models.entity_models import EntityCreate, EntityStatus
from apps.crm.models.relationship_models import RelationshipCreate
from apps.crm.models.note_models import ConfirmEntitiesResponse

logger = logging.getLogger(__name__)


class NoteService:
    """
    Сервис для работы с заметками (Daily Notes).
    
    Заметки хранятся в PostgreSQL с индексами по дате.
    Attachments индексируются в RAG через асинхронные TaskIQ задачи.
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
        
        status_value = data.status.value if hasattr(data.status, 'value') else str(data.status)
        
        visibility_value = data.visibility.value if hasattr(data.visibility, 'value') else str(data.visibility)
        
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
            is_template=data.is_template,
            status=status_value,
            visibility=visibility_value,
            shared_with=data.shared_with,
            attachment_ids=data.attachment_ids,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        
        await self._repo.create(note)
        logger.info(f"Создана заметка: {note.note_id} (шаблон: {note.is_template})")
        
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
        if data.is_template is not None:
            note.is_template = data.is_template
        if data.status is not None:
            note.status = data.status.value if hasattr(data.status, 'value') else str(data.status)
        if data.visibility is not None:
            note.visibility = data.visibility.value if hasattr(data.visibility, 'value') else str(data.visibility)
        if data.shared_with is not None:
            note.shared_with = data.shared_with
        if data.attachment_ids is not None:
            note.attachment_ids = data.attachment_ids
        
        note.updated_at = datetime.now(timezone.utc)
        
        await self._repo.update(note)
        logger.info(f"Обновлена заметка: {note_id}")
        
        return self._to_response(note)
    
    async def delete_note(
        self, 
        note_id: str,
        company_id: Optional[str] = None
    ) -> bool:
        """
        Удаляет заметку и все её attachments.
        
        Заметка удаляется синхронно, затем запускается
        асинхронная TaskIQ задача для удаления attachments из RAG и S3.
        """
        note = await self._repo.get(note_id)
        if not note:
            return False
        
        company_id = company_id or self._get_company_id()
        attachment_ids = note.attachment_ids or []
        
        # 1. Собираем информацию об attachments для удаления
        attachments = []
        if attachment_ids:
            file_processor = await get_default_file_processor()
            for file_id in attachment_ids:
                file_record = await file_processor.get_file_record(file_id)
                attachments.append({
                    "file_id": file_id,
                    "s3_key": file_record.s3_key if file_record else "",
                })
        
        # 2. Удаляем заметку из БД
        success = await self._repo.delete(note_id)
        if not success:
            return False
        
        # 3. Асинхронно удаляем attachments из RAG и S3
        if attachments:
            await delete_note_attachments_task.kiq(
                company_id=company_id,
                note_id=note_id,
                attachments=attachments,
            )
            logger.info(
                f"Заметка {note_id} удалена, "
                f"удаление {len(attachments)} attachments запущено асинхронно"
            )
        else:
            logger.info(f"Удалена заметка: {note_id}")
        
        return True
    
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
    
    async def filter_notes(
        self,
        user_id: Optional[str] = None,
        note_type: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        entity_id: Optional[str] = None,
        search_text: Optional[str] = None,
        is_template: Optional[bool] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        company_id: Optional[str] = None
    ) -> List[NoteResponse]:
        """Расширенная фильтрация заметок по нескольким параметрам"""
        company_id = company_id or self._get_company_id()
        
        notes = await self._repo.filter_notes(
            company_id=company_id,
            user_id=user_id,
            note_type=note_type,
            start_date=start_date,
            end_date=end_date,
            entity_id=entity_id,
            search_text=search_text,
            is_template=is_template,
            status=status,
            limit=limit,
            offset=offset
        )
        
        return [self._to_response(note) for note in notes]
    
    async def get_templates(
        self,
        note_type: Optional[str] = None,
        limit: int = 100,
        company_id: Optional[str] = None
    ) -> List[NoteResponse]:
        """Получает шаблоны заметок"""
        company_id = company_id or self._get_company_id()
        
        templates = await self._repo.get_templates(company_id, note_type, limit)
        return [self._to_response(t) for t in templates]
    
    async def import_from_file(
        self,
        file,
        title: str,
        note_type: str,
        note_date: date,
        company_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> NoteResponse:
        """
        Импортирует заметку из файла (txt, docx, pdf).
        
        Файл загружается в S3, создается заметка со статусом 'importing',
        затем запускается TaskIQ таска для парсинга.
        """
        company_id = company_id or self._get_company_id()
        user_id = user_id or self._get_user_id()
        
        # Читаем содержимое файла
        content_bytes = await file.read()
        filename = file.filename or "document"
        content_type = file.content_type or "application/octet-stream"
        
        # 1. Загружаем файл в S3
        file_processor = await get_default_file_processor()
        file_record = await file_processor.process_file_from_bytes(
            data=content_bytes,
            original_name=filename,
            content_type=content_type,
            uploaded_by=user_id,
            metadata={"company_id": company_id, "import": "true"},
            public=False,
        )
        
        # 2. Создаем заметку со статусом importing
        note = Note(
            note_id=str(uuid.uuid4()),
            company_id=company_id,
            user_id=user_id,
            title=title,
            content="",  # Будет заполнено после парсинга
            note_type=note_type,
            note_date=note_date,
            ai_summary=None,
            linked_entity_ids=[],
            is_template=False,
            status="importing",  # Статус "в процессе импорта"
            visibility="private",
            shared_with=[],
            attachment_ids=[file_record.file_id],  # Исходный файл как attachment
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        
        await self._repo.create(note)
        
        # 3. Запускаем асинхронный парсинг
        await import_note_from_file_task.kiq(
            note_id=note.note_id,
            company_id=company_id,
            user_id=user_id,
            file_id=file_record.file_id,
            s3_key=file_record.s3_key,
            filename=filename,
            title=title,
            note_type=note_type,
            note_date=str(note_date),
        )
        
        logger.info(f"Импорт заметки из {filename} запущен: {note.note_id}")
        
        return self._to_response(note)
    
    async def create_from_template(
        self,
        template_id: str,
        note_date: date,
        company_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> NoteResponse:
        """Создает новую заметку на основе шаблона"""
        company_id = company_id or self._get_company_id()
        user_id = user_id or self._get_user_id()
        
        template = await self._repo.get(template_id)
        if not template:
            raise ValueError(f"Шаблон {template_id} не найден")
        
        if not template.is_template:
            raise ValueError(f"Заметка {template_id} не является шаблоном")
        
        note = Note(
            note_id=str(uuid.uuid4()),
            company_id=company_id,
            user_id=user_id,
            title=template.title,
            content=template.content,
            note_type=template.note_type,
            note_date=note_date,
            ai_summary=None,
            linked_entity_ids=[],
            is_template=False,
            status="draft",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        
        await self._repo.create(note)
        logger.info(f"Создана заметка из шаблона {template_id}: {note.note_id}")
        
        return self._to_response(note)
    
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
    
    async def get_daily_summary(
        self,
        note_date: date,
        company_id: Optional[str] = None
    ) -> str:
        """
        Генерирует AI саммари всех заметок за день.
        """
        company_id = company_id or self._get_company_id()
        
        notes = await self._repo.get_by_date(company_id, note_date)
        
        if not notes:
            return "Нет заметок за этот день."
        
        # Собираем текст всех заметок
        combined_text = "\n\n---\n\n".join([
            f"**{note.title}**\n{note.content}" 
            for note in notes
        ])
        
        # Вызываем AI для генерации саммари
        summary_result = await self._agents_client.extract_entities(
            text=f"Создай краткое саммари следующих заметок за день:\n\n{combined_text}",
            generate_summary=True,
        )
        
        return summary_result.get("summary", "Не удалось сгенерировать саммари.")
    
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
            from apps.crm.services.agents_client import AgentsUnavailableError
            try:
                # Получаем актуальные типы сущностей из БД
                entity_types = await self._get_entity_types_for_extraction(company_id, note.note_type)
                
                # Получаем информацию об авторе
                author_info = await self._get_author_info(note.user_id, company_id)
                
                # Получаем существующие сущности (упомянутые через @mention)
                existing_entities = []
                if request.mentioned_entity_ids:
                    for eid in request.mentioned_entity_ids:
                        entity = await self._entity_service.get_entity(eid)
                        if entity:
                            existing_entities.append({
                                "entity_id": entity.entity_id,
                                "name": entity.name,
                                "type": entity.type,
                                "description": entity.description,
                            })
                
                # Контекст заметки
                note_context = {
                    "note_type": note.note_type,
                    "title": note.title,
                    "note_date": str(note.note_date),
                }
                
                ai_result = await self._agents_client.extract_entities(
                    text=note.content,
                    entity_types=entity_types,
                    generate_summary=request.generate_summary,
                    author_info=author_info,
                    note_context=note_context,
                    existing_entities=existing_entities,
                )
                
                if request.generate_summary and ai_result.get("summary"):
                    result.summary = ai_result["summary"]
                    
                    note.ai_summary = result.summary
                    await self._repo.update(note)
                
                if request.extract_entities:
                    result.extracted_entities = ai_result.get("entities", [])
                    result.extracted_relationships = ai_result.get("relationships", [])
            except AgentsUnavailableError as e:
                result.error = str(e)
        
        return result
    
    async def _get_entity_types_for_extraction(
        self,
        company_id: str,
        note_type: str,
    ) -> list:
        """
        Получает типы сущностей для AI извлечения.
        
        Включает:
        - Все типы сущностей (person, organization, project, task)
        - Event типы (meeting, call, email) - для правильного распознавания контекста
        - Инструкции по связям
        """
        from apps.crm.container import get_crm_container
        
        container = get_crm_container()
        all_types = await container.entity_type_service.get_all_types(company_id)
        
        # Преобразуем в формат для промпта
        entity_types = []
        for t in all_types:
            type_dict = {
                "type_id": t.type_id,
                "name": t.name,
                "description": t.description,
                "prompt": t.prompt,
                "is_event": t.is_event,
                "required_fields": {
                    k: v.model_dump() if hasattr(v, 'model_dump') else v
                    for k, v in (t.required_fields or {}).items()
                },
                "optional_fields": {
                    k: v.model_dump() if hasattr(v, 'model_dump') else v
                    for k, v in (t.optional_fields or {}).items()
                },
            }
            entity_types.append(type_dict)
        
        return entity_types
    
    async def _get_author_info(
        self,
        user_id: str,
        company_id: str,
    ) -> dict:
        """
        Получает информацию об авторе заметки для AI.
        
        Пытается найти person сущность для user_id,
        иначе возвращает базовую информацию из user.
        """
        # Сначала пробуем найти person сущность для этого user
        person_entity = await self._find_user_person_entity(user_id, company_id)
        
        if person_entity:
            return {
                "name": person_entity.name,
                "user_id": user_id,
                "entity_id": person_entity.entity_id,
                "attributes": person_entity.attributes,
            }
        
        # Получаем имя из контекста
        from core.context import get_context
        context = get_context()
        if context and context.user and context.user.user_id == user_id:
            return {
                "name": context.user.name or context.user.email or user_id,
                "user_id": user_id,
            }
        
        return {
            "name": user_id,
            "user_id": user_id,
        }
    
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
    
    async def add_attachment(
        self,
        note_id: str,
        file,
        company_id: Optional[str] = None
    ) -> Optional[dict]:
        """
        Загружает файл и добавляет его к заметке.
        
        Файл сохраняется в S3 синхронно, затем запускается
        асинхронная TaskIQ задача для индексации в RAG.
        """
        note = await self._repo.get(note_id)
        if not note:
            return None
        
        user_id = self._get_user_id()
        company_id = company_id or self._get_company_id()
        
        content = await file.read()
        filename = file.filename or "attachment"
        content_type = file.content_type
        
        # 1. Синхронно загружаем в S3
        file_processor = await get_default_file_processor()
        file_record = await file_processor.process_file_from_bytes(
            data=content,
            original_name=filename,
            content_type=content_type,
            uploaded_by=user_id,
            metadata={"note_id": note_id, "company_id": company_id},
            public=False,
        )
        
        # 2. Добавляем file_id в attachment_ids заметки
        note.attachment_ids = (note.attachment_ids or []) + [file_record.file_id]
        note.updated_at = datetime.now(timezone.utc)
        await self._repo.update(note)
        
        # 3. Асинхронно индексируем в RAG через TaskIQ
        await process_crm_attachment_task.kiq(
            company_id=company_id,
            note_id=note_id,
            file_id=file_record.file_id,
            s3_key=file_record.s3_key,
            document_name=filename,
            content_type=content_type,
            note_title=note.title,
            user_id=user_id,
        )
        
        logger.info(
            f"Файл {file_record.file_id} загружен в S3, "
            f"индексация в RAG запущена асинхронно"
        )
        
        return {
            "file_id": file_record.file_id,
            "original_name": file_record.original_name,
            "content_type": file_record.content_type,
            "file_size": file_record.file_size,
            "status": "indexing",  # Индексация еще в процессе
        }
    
    async def remove_attachment(
        self,
        note_id: str,
        file_id: str,
        company_id: Optional[str] = None
    ) -> bool:
        """
        Удаляет файл из заметки.
        
        Убирает file_id из списка синхронно, затем запускается
        асинхронная TaskIQ задача для удаления из RAG и S3.
        """
        note = await self._repo.get(note_id)
        if not note:
            return False
        
        if file_id not in (note.attachment_ids or []):
            return False
        
        company_id = company_id or self._get_company_id()
        
        # 1. Получаем s3_key для файла
        file_processor = await get_default_file_processor()
        file_record = await file_processor.get_file_record(file_id)
        s3_key = file_record.s3_key if file_record else ""
        
        # 2. Убираем file_id из списка
        note.attachment_ids = [fid for fid in note.attachment_ids if fid != file_id]
        note.updated_at = datetime.now(timezone.utc)
        await self._repo.update(note)
        
        # 3. Асинхронно удаляем из RAG и S3 через TaskIQ
        await delete_crm_attachment_task.kiq(
            company_id=company_id,
            note_id=note_id,
            file_id=file_id,
            s3_key=s3_key,
        )
        
        logger.info(
            f"Файл {file_id} отвязан от заметки, "
            f"удаление из RAG/S3 запущено асинхронно"
        )
        return True
    
    async def get_attachments(
        self,
        note_id: str,
        company_id: Optional[str] = None
    ) -> Optional[List[dict]]:
        """Получает список файлов заметки с метаданными"""
        note = await self._repo.get(note_id)
        if not note:
            return None
        
        attachments = []
        file_processor = await get_default_file_processor()
        
        for file_id in (note.attachment_ids or []):
            file_record = await file_processor.get_file_record(file_id)
            if file_record:
                attachments.append({
                    "file_id": file_record.file_id,
                    "original_name": file_record.original_name,
                    "content_type": file_record.content_type,
                    "file_size": file_record.file_size,
                })
        
        return attachments
    
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
            is_template=getattr(note, 'is_template', False),
            status=getattr(note, 'status', 'published'),
            visibility=getattr(note, 'visibility', 'public'),
            shared_with=getattr(note, 'shared_with', []) or [],
            attachment_ids=getattr(note, 'attachment_ids', []) or [],
            created_at=note.created_at,
            updated_at=note.updated_at,
        )
    
    async def get_attachment_download_url(
        self,
        note_id: str,
        file_id: str,
    ) -> Optional[str]:
        """Получает presigned URL для скачивания файла"""
        note = await self._repo.get(note_id)
        if not note:
            logger.warning(f"Note {note_id} не найден")
            return None
        
        if file_id not in (note.attachment_ids or []):
            logger.warning(f"File {file_id} не в attachment_ids заметки: {note.attachment_ids}")
            return None
        
        try:
            file_processor = await get_default_file_processor()
            file_record = await file_processor.file_repository.get(file_id)
            if not file_record:
                logger.warning(f"File record {file_id} не найден в repository")
                return None
            if not file_record.s3_key:
                logger.warning(f"File record {file_id} не имеет s3_key")
                return None
            
            # Генерируем presigned URL через S3 клиент
            s3_client = await file_processor._get_s3_client()
            url = await s3_client.generate_presigned_url(
                key=file_record.s3_key,
                expiration=3600,  # 1 час
            )
            await s3_client.close()
            return url
        except Exception as e:
            logger.error(f"Ошибка получения download URL: {e}", exc_info=True)
            return None
    
    async def get_attachment_content(
        self,
        note_id: str,
        file_id: str,
    ) -> Optional[str]:
        """Получает распаршенный контент файла из RAG"""
        note = await self._repo.get(note_id)
        if not note or file_id not in (note.attachment_ids or []):
            return None
        
        company_id = self._get_company_id()
        
        try:
            from core.rag import get_rag_provider
            rag_provider = get_rag_provider()
            
            # Namespace как в attachment_tasks.py
            namespace_id = f"crm_attachments_{company_id}"
            
            # Используем get_raw для получения текста чанков
            # Ищем по file_id в metadata (не по document_id!)
            if hasattr(rag_provider, 'get_raw'):
                results = await rag_provider.get_raw(
                    namespace_id=namespace_id,
                    where={"file_id": file_id},
                    include=["documents", "metadatas"],
                    limit=100,
                )
                
                if results and results.get("documents"):
                    # Сортируем чанки по индексу если есть
                    chunks = []
                    for i, doc in enumerate(results["documents"]):
                        meta = results["metadatas"][i] if results.get("metadatas") else {}
                        chunk_idx = meta.get("chunk_index", i)
                        chunks.append((chunk_idx, doc))
                    
                    chunks.sort(key=lambda x: x[0])
                    return "\n\n".join([c[1] for c in chunks if c[1]])
            
            return None
        except Exception as e:
            logger.error(f"Ошибка получения контента файла: {e}")
            return None

    async def confirm_entities(
        self,
        note_id: str,
        request,
        company_id: Optional[str] = None,
    ):
        """
        Подтверждает извлечённые сущности и создаёт их в БД вместе со связями.
        
        Процесс:
        1. Если create_event=True и note_type подходит - создаём event сущность
        2. Создаём все подтверждённые сущности
        3. Создаём связи между сущностями
        4. Если link_author=True - связываем автора с event
        5. Линкуем все созданные сущности к заметке
        """

        
        company_id = company_id or self._get_company_id()
        user_id = self._get_user_id()
        
        note = await self._repo.get(note_id)
        if not note:
            raise ValueError(f"Заметка {note_id} не найдена")
        
        created_entities = []
        created_relationships = []
        event_entity = None
        entity_id_map = {}  # index -> entity_id для связей
        
        # Маппинг note_type -> event type
        note_type_to_event = {
            "meeting_minutes": "meeting",
            "call_log": "call",
        }
        
        # 1. Создаём event сущность если нужно
        if request.create_event and note.note_type in note_type_to_event:
            event_type = note_type_to_event[note.note_type]
            
            event_data = EntityCreate(
                type=event_type,
                name=note.title,
                description=note.ai_summary or note.content[:500],
                ai_description=f"Событие из заметки от {note.note_date}",
                attributes={
                    "date": str(note.note_date),
                    "source_note_id": note_id,
                },
                status=EntityStatus.APPROVED,
                source_note_id=note_id,
            )
            
            event_entity = await self._entity_service.create_entity(event_data, company_id)
            created_entities.append(event_entity.model_dump())
            entity_id_map[-1] = event_entity.entity_id  # Специальный индекс для event
        
        # 2. Создаём подтверждённые сущности
        for idx, entity_item in enumerate(request.entities):
            entity_data = EntityCreate(
                type=entity_item.type,
                name=entity_item.name,
                description=entity_item.description,
                ai_description=entity_item.ai_description,
                attributes=entity_item.attributes,
                status=EntityStatus.APPROVED,
                source_note_id=note_id,
            )
            
            created = await self._entity_service.create_entity(entity_data, company_id)
            created_entities.append(created.model_dump())
            entity_id_map[idx] = created.entity_id
        
        # 3. Создаём связи между сущностями
        from apps.crm.container import get_crm_container
        container = get_crm_container()
        relationship_service = container.relationship_service
        
        for rel_item in request.relationships:
            source_id = entity_id_map.get(rel_item.source_index)
            target_id = entity_id_map.get(rel_item.target_index)
            
            if not source_id or not target_id:
                logger.warning(f"Не найден entity для связи: source={rel_item.source_index}, target={rel_item.target_index}")
                continue
            
            rel_data = RelationshipCreate(
                source_entity_id=source_id,
                target_entity_id=target_id,
                relationship_type=rel_item.relationship_type,
                weight=rel_item.weight,
                attributes={
                    **rel_item.attributes,
                    "source_note_id": note_id,
                    "confidence": rel_item.attributes.get("confidence", 1.0),
                },
            )
            
            created_rel, was_created = await relationship_service.get_or_create_relationship(rel_data, company_id)
            if was_created:
                created_relationships.append(created_rel.model_dump())
        
        # 4. Связываем все сущности с event (participated_in / mentioned_in)
        if event_entity:
            for idx, entity_id in entity_id_map.items():
                if idx == -1:  # Пропускаем сам event
                    continue
                
                # Определяем тип связи
                entity_type = request.entities[idx].type if idx < len(request.entities) else "unknown"
                rel_type = "participated_in" if entity_type == "person" else "mentioned_in"
                
                rel_data = RelationshipCreate(
                    source_entity_id=entity_id,
                    target_entity_id=event_entity.entity_id,
                    relationship_type=rel_type,
                    weight=1.0,
                    attributes={"source_note_id": note_id, "auto_created": True},
                )
                
                created_rel, was_created = await relationship_service.get_or_create_relationship(rel_data, company_id)
                if was_created:
                    created_relationships.append(created_rel.model_dump())
        
        # 5. Связываем автора с event
        if request.link_author and event_entity:
            # Ищем person сущность для автора по user_id
            author_entity = await self._find_user_person_entity(user_id, company_id)
            
            if author_entity:
                rel_data = RelationshipCreate(
                    source_entity_id=event_entity.entity_id,
                    target_entity_id=author_entity.entity_id,
                    relationship_type="organized_by",
                    weight=1.0,
                    attributes={"source_note_id": note_id, "auto_created": True},
                )
                
                created_rel, was_created = await relationship_service.get_or_create_relationship(rel_data, company_id)
                if was_created:
                    created_relationships.append(created_rel.model_dump())
        
        # 6. Линкуем все созданные сущности к заметке
        all_entity_ids = list(entity_id_map.values())
        note.linked_entity_ids = list(set((note.linked_entity_ids or []) + all_entity_ids))
        note.updated_at = datetime.now(timezone.utc)
        await self._repo.update(note)
        
        logger.info(
            f"Подтверждены сущности для заметки {note_id}: "
            f"{len(created_entities)} entities, {len(created_relationships)} relationships"
        )
        
        return ConfirmEntitiesResponse(
            created_entities=created_entities,
            created_relationships=created_relationships,
            event_entity=event_entity.model_dump() if event_entity else None,
            linked_entity_ids=all_entity_ids,
        )
    
    async def _find_user_person_entity(
        self,
        user_id: str,
        company_id: str,
    ):
        """Ищет person сущность для пользователя"""
        # Ищем по атрибуту user_id в сущностях типа person
        entities = await self._entity_service.list_entities(
            entity_type="person",
            limit=1000,
            company_id=company_id,
        )
        
        for entity in entities:
            if entity.attributes.get("user_id") == user_id:
                return entity
        
        return None


