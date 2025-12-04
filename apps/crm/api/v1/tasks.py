"""
API для задач CRM.
"""

from typing import List, Optional, Dict

from fastapi import APIRouter, HTTPException, Query

from apps.crm.dependencies import TaskServiceDep
from apps.crm.models.task_models import TaskCreate, TaskUpdate, TaskResponse

router = APIRouter()


@router.get("", response_model=List[TaskResponse])
async def list_tasks(
    task_service: TaskServiceDep,
    status: Optional[str] = Query(None, description="Фильтр по статусу"),
    priority: Optional[str] = Query(None, description="Фильтр по приоритету"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """Получает список задач"""
    return await task_service.list_tasks(
        status=status,
        priority=priority,
        limit=limit,
        offset=offset,
    )


@router.get("/my", response_model=List[TaskResponse])
async def get_my_tasks(
    task_service: TaskServiceDep,
    status: Optional[str] = Query(None, description="Фильтр по статусу"),
    limit: int = Query(100, ge=1, le=500),
):
    """Получает задачи текущего пользователя"""
    return await task_service.get_my_tasks(status=status, limit=limit)


@router.get("/overdue", response_model=List[TaskResponse])
async def get_overdue_tasks(
    task_service: TaskServiceDep,
):
    """Получает просроченные задачи"""
    return await task_service.get_overdue_tasks()


@router.get("/due-today", response_model=List[TaskResponse])
async def get_due_today(
    task_service: TaskServiceDep,
):
    """Получает задачи с дедлайном сегодня"""
    return await task_service.get_due_today()


@router.get("/due-this-week", response_model=List[TaskResponse])
async def get_due_this_week(
    task_service: TaskServiceDep,
):
    """Получает задачи на эту неделю"""
    return await task_service.get_due_this_week()


@router.get("/stats", response_model=Dict[str, int])
async def get_task_stats(
    task_service: TaskServiceDep,
):
    """Получает статистику по задачам"""
    return await task_service.get_task_stats()


@router.get("/entity/{entity_id}", response_model=List[TaskResponse])
async def get_tasks_by_entity(
    entity_id: str,
    task_service: TaskServiceDep,
):
    """Получает задачи, связанные с сущностью"""
    return await task_service.get_tasks_by_entity(entity_id)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    task_service: TaskServiceDep,
):
    """Получает задачу по ID"""
    task = await task_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return task


@router.post("", response_model=TaskResponse)
async def create_task(
    data: TaskCreate,
    task_service: TaskServiceDep,
):
    """Создает новую задачу"""
    return await task_service.create_task(data)


@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: str,
    data: TaskUpdate,
    task_service: TaskServiceDep,
):
    """Обновляет задачу"""
    task = await task_service.update_task(task_id, data)
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return task


@router.delete("/{task_id}")
async def delete_task(
    task_id: str,
    task_service: TaskServiceDep,
):
    """Удаляет задачу"""
    success = await task_service.delete_task(task_id)
    if not success:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return {"status": "deleted"}


@router.post("/{task_id}/complete", response_model=TaskResponse)
async def complete_task(
    task_id: str,
    task_service: TaskServiceDep,
):
    """Помечает задачу как выполненную"""
    task = await task_service.complete_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return task


@router.post("/{task_id}/cancel", response_model=TaskResponse)
async def cancel_task(
    task_id: str,
    task_service: TaskServiceDep,
):
    """Отменяет задачу"""
    task = await task_service.cancel_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return task


