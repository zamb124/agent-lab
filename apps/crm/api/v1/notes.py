"""
API для заметок CRM (Daily Notes).
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form

from apps.crm.dependencies import NoteServiceDep
from apps.crm.models.note_models import (
    NoteCreate,
    NoteUpdate,
    NoteResponse,
    NoteAnalyzeRequest,
    NoteAnalyzeResponse,
    ConfirmEntitiesRequest,
    ConfirmEntitiesResponse,
)

router = APIRouter()


@router.get("", response_model=List[NoteResponse])
async def list_notes(
    note_service: NoteServiceDep,
    note_type: Optional[str] = Query(None, description="Фильтр по типу"),
    user_id: Optional[str] = Query(None, description="Фильтр по автору"),
    entity_id: Optional[str] = Query(None, description="Фильтр по связанной сущности"),
    start_date: Optional[date] = Query(None, description="Начало диапазона дат"),
    end_date: Optional[date] = Query(None, description="Конец диапазона дат"),
    q: Optional[str] = Query(None, description="Поиск по тексту"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """Получает список заметок с расширенной фильтрацией"""
    # Если есть фильтры - используем расширенный метод
    if any([user_id, entity_id, start_date, end_date, q]):
        return await note_service.filter_notes(
            user_id=user_id,
            note_type=note_type,
            start_date=start_date,
            end_date=end_date,
            entity_id=entity_id,
            search_text=q,
            limit=limit,
            offset=offset,
        )
    
    return await note_service.list_notes(
        note_type=note_type,
        limit=limit,
        offset=offset,
    )


@router.get("/templates", response_model=List[NoteResponse])
async def get_templates(
    note_service: NoteServiceDep,
    note_type: Optional[str] = Query(None, description="Фильтр по типу"),
    limit: int = Query(100, ge=1, le=1000),
):
    """Получает список шаблонов заметок"""
    return await note_service.get_templates(note_type=note_type, limit=limit)


@router.post("/from-template/{template_id}", response_model=NoteResponse)
async def create_from_template(
    template_id: str,
    note_service: NoteServiceDep,
    note_date: date = Query(default=None),
):
    """Создает новую заметку на основе шаблона"""
    from datetime import date as date_cls
    actual_date = note_date if note_date else date_cls.today()
    return await note_service.create_from_template(template_id, actual_date)


@router.get("/daily/{note_date}", response_model=List[NoteResponse])
async def get_daily_notes(
    note_date: date,
    note_service: NoteServiceDep,
):
    """Получает заметки за определенную дату"""
    return await note_service.get_daily_notes(note_date)


@router.get("/daily-summary/{note_date}")
async def get_daily_summary(
    note_date: date,
    note_service: NoteServiceDep,
):
    """Генерирует AI саммари всех заметок за день"""
    summary = await note_service.get_daily_summary(note_date)
    return {"date": str(note_date), "summary": summary}


@router.post("/import", response_model=NoteResponse)
async def import_note_from_file(
    note_service: NoteServiceDep,
    file: UploadFile = File(...),
    title: str = Form(None),
    note_type: str = Form("freeform"),
    note_date: date = Form(None),
):
    """
    Импортирует заметку из файла (txt, docx, pdf).
    Использует RAG парсер для извлечения текста.
    """
    from datetime import date as date_cls
    actual_date = note_date if note_date else date_cls.today()
    actual_title = title if title else file.filename
    
    return await note_service.import_from_file(
        file=file,
        title=actual_title,
        note_type=note_type,
        note_date=actual_date,
    )


@router.get("/range", response_model=List[NoteResponse])
async def get_notes_in_range(
    note_service: NoteServiceDep,
    start_date: date = Query(...),
    end_date: date = Query(...),
):
    """Получает заметки за диапазон дат"""
    return await note_service.get_notes_in_range(start_date, end_date)


@router.get("/entity/{entity_id}", response_model=List[NoteResponse])
async def get_notes_by_entity(
    entity_id: str,
    note_service: NoteServiceDep,
):
    """Получает заметки, связанные с сущностью"""
    return await note_service.get_notes_by_entity(entity_id)


@router.get("/search", response_model=List[NoteResponse])
async def search_notes(
    note_service: NoteServiceDep,
    q: str = Query(..., min_length=2),
    limit: int = Query(50, ge=1, le=200),
):
    """Поиск по содержимому заметок"""
    return await note_service.search_notes(q, limit)


@router.get("/{note_id}", response_model=NoteResponse)
async def get_note(
    note_id: str,
    note_service: NoteServiceDep,
):
    """Получает заметку по ID"""
    note = await note_service.get_note(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Заметка не найдена")
    return note


@router.post("", response_model=NoteResponse)
async def create_note(
    data: NoteCreate,
    note_service: NoteServiceDep,
):
    """Создает новую заметку"""
    return await note_service.create_note(data)


@router.put("/{note_id}", response_model=NoteResponse)
async def update_note(
    note_id: str,
    data: NoteUpdate,
    note_service: NoteServiceDep,
):
    """Обновляет заметку"""
    note = await note_service.update_note(note_id, data)
    if not note:
        raise HTTPException(status_code=404, detail="Заметка не найдена")
    return note


@router.delete("/{note_id}")
async def delete_note(
    note_id: str,
    note_service: NoteServiceDep,
):
    """Удаляет заметку"""
    success = await note_service.delete_note(note_id)
    if not success:
        raise HTTPException(status_code=404, detail="Заметка не найдена")
    return {"status": "deleted"}


@router.post("/{note_id}/analyze", response_model=NoteAnalyzeResponse)
async def analyze_note(
    note_id: str,
    request: NoteAnalyzeRequest,
    note_service: NoteServiceDep,
):
    """Анализирует заметку с помощью AI"""
    return await note_service.analyze_note(note_id, request)


@router.post("/{note_id}/confirm-entities", response_model=ConfirmEntitiesResponse)
async def confirm_entities(
    note_id: str,
    request: ConfirmEntitiesRequest,
    note_service: NoteServiceDep,
):
    """
    Подтверждает извлечённые сущности и создаёт их в БД.
    
    Создаёт:
    - Event сущность (meeting/call/email) если create_event=True
    - Все подтверждённые сущности
    - Связи между сущностями
    - Связь автора с событием если link_author=True
    """
    return await note_service.confirm_entities(note_id, request)


@router.post("/{note_id}/link/{entity_id}", response_model=NoteResponse)
async def link_entity_to_note(
    note_id: str,
    entity_id: str,
    note_service: NoteServiceDep,
):
    """Связывает сущность с заметкой"""
    return await note_service.link_entity_to_note(note_id, entity_id)


@router.delete("/{note_id}/link/{entity_id}", response_model=NoteResponse)
async def unlink_entity_from_note(
    note_id: str,
    entity_id: str,
    note_service: NoteServiceDep,
):
    """Убирает связь сущности с заметкой"""
    return await note_service.unlink_entity_from_note(note_id, entity_id)


@router.post("/{note_id}/attachments")
async def upload_attachment(
    note_id: str,
    note_service: NoteServiceDep,
    file: UploadFile = File(...),
):
    """
    Загружает файл и добавляет его к заметке.
    Возвращает информацию о загруженном файле.
    """
    result = await note_service.add_attachment(note_id, file)
    if not result:
        raise HTTPException(status_code=404, detail="Заметка не найдена")
    return result


@router.delete("/{note_id}/attachments/{file_id}")
async def remove_attachment(
    note_id: str,
    file_id: str,
    note_service: NoteServiceDep,
):
    """Удаляет файл из заметки"""
    success = await note_service.remove_attachment(note_id, file_id)
    if not success:
        raise HTTPException(status_code=404, detail="Заметка или файл не найден")
    return {"status": "deleted"}


@router.get("/{note_id}/attachments")
async def get_attachments(
    note_id: str,
    note_service: NoteServiceDep,
):
    """Получает список файлов заметки"""
    attachments = await note_service.get_attachments(note_id)
    if attachments is None:
        raise HTTPException(status_code=404, detail="Заметка не найдена")
    return attachments


@router.get("/{note_id}/attachments/{file_id}/download")
async def download_attachment(
    note_id: str,
    file_id: str,
    note_service: NoteServiceDep,
):
    """Получает URL для скачивания файла"""
    download_url = await note_service.get_attachment_download_url(note_id, file_id)
    if not download_url:
        raise HTTPException(status_code=404, detail="Файл не найден")
    return {"download_url": download_url}


@router.get("/{note_id}/attachments/{file_id}/content")
async def get_attachment_content(
    note_id: str,
    file_id: str,
    note_service: NoteServiceDep,
):
    """Получает распаршенный контент файла из RAG"""
    content = await note_service.get_attachment_content(note_id, file_id)
    if content is None:
        raise HTTPException(status_code=404, detail="Контент не найден")
    return {"content": content}

