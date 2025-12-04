"""
API для заметок CRM (Daily Notes).
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from apps.crm.dependencies import NoteServiceDep
from apps.crm.models.note_models import (
    NoteCreate,
    NoteUpdate,
    NoteResponse,
    NoteAnalyzeRequest,
    NoteAnalyzeResponse,
)

router = APIRouter()


@router.get("", response_model=List[NoteResponse])
async def list_notes(
    note_service: NoteServiceDep,
    note_type: Optional[str] = Query(None, description="Фильтр по типу"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """Получает список заметок"""
    return await note_service.list_notes(
        note_type=note_type,
        limit=limit,
        offset=offset,
    )


@router.get("/daily/{note_date}", response_model=List[NoteResponse])
async def get_daily_notes(
    note_date: date,
    note_service: NoteServiceDep,
):
    """Получает заметки за определенную дату"""
    return await note_service.get_daily_notes(note_date)


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


