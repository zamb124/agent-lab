"""
TaskService - управление задачами CRM.
"""

import logging
import uuid
from datetime import date, datetime, timezone
from typing import List, Optional, Dict

from core.context import get_context
from apps.crm.db.models import Task
from apps.crm.db.repositories.task_repository import TaskRepository
from apps.crm.services.entity_service import EntityService
from apps.crm.models.task_models import (
    TaskCreate,
    TaskUpdate,
    TaskResponse,
    TaskStatus,
)

logger = logging.getLogger(__name__)


class TaskService:
    """
    Сервис для работы с задачами.
    
    Задачи хранятся в PostgreSQL с индексами по:
    - status, priority, due_date
    - user_id, company_id
    """
    
    def __init__(
        self,
        task_repository: TaskRepository,
        entity_service: EntityService,
    ):
        self._repo = task_repository
        self._entity_service = entity_service
    
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
    
    async def create_task(
        self, 
        data: TaskCreate,
        company_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> TaskResponse:
        """Создает новую задачу"""
        company_id = company_id or self._get_company_id()
        user_id = user_id or self._get_user_id()
        
        task = Task(
            task_id=str(uuid.uuid4()),
            company_id=company_id,
            user_id=user_id,
            title=data.title,
            description=data.description,
            priority=data.priority.value,
            status=TaskStatus.PENDING.value,
            due_date=data.due_date,
            linked_entity_id=data.linked_entity_id,
            source_note_id=data.source_note_id,
            tags=data.tags,
            assignees=data.assignees,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        
        await self._repo.create(task)
        logger.info(f"Создана задача: {task.task_id}")
        
        return self._to_response(task)
    
    async def get_task(
        self, 
        task_id: str,
        company_id: Optional[str] = None
    ) -> Optional[TaskResponse]:
        """Получает задачу по ID"""
        task = await self._repo.get(task_id)
        if not task:
            return None
        return self._to_response(task)
    
    async def update_task(
        self, 
        task_id: str,
        data: TaskUpdate,
        company_id: Optional[str] = None
    ) -> Optional[TaskResponse]:
        """Обновляет задачу"""
        task = await self._repo.get(task_id)
        if not task:
            return None
        
        if data.title is not None:
            task.title = data.title
        if data.description is not None:
            task.description = data.description
        if data.priority is not None:
            task.priority = data.priority.value
        if data.status is not None:
            task.status = data.status.value
        if data.due_date is not None:
            task.due_date = data.due_date
        if data.linked_entity_id is not None:
            task.linked_entity_id = data.linked_entity_id
        if data.tags is not None:
            task.tags = data.tags
        if data.assignees is not None:
            task.assignees = data.assignees
        
        task.updated_at = datetime.now(timezone.utc)
        
        await self._repo.update(task)
        logger.info(f"Обновлена задача: {task_id}")
        
        return self._to_response(task)
    
    async def delete_task(
        self, 
        task_id: str,
        company_id: Optional[str] = None
    ) -> bool:
        """Удаляет задачу"""
        success = await self._repo.delete(task_id)
        if success:
            logger.info(f"Удалена задача: {task_id}")
        return success
    
    async def complete_task(
        self, 
        task_id: str,
        company_id: Optional[str] = None
    ) -> Optional[TaskResponse]:
        """Помечает задачу как выполненную"""
        return await self.update_task(
            task_id,
            TaskUpdate(status=TaskStatus.COMPLETED),
            company_id
        )
    
    async def cancel_task(
        self, 
        task_id: str,
        company_id: Optional[str] = None
    ) -> Optional[TaskResponse]:
        """Отменяет задачу"""
        return await self.update_task(
            task_id,
            TaskUpdate(status=TaskStatus.CANCELLED),
            company_id
        )
    
    async def get_my_tasks(
        self,
        status: Optional[str] = None,
        limit: int = 100,
        company_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> List[TaskResponse]:
        """Получает задачи текущего пользователя"""
        company_id = company_id or self._get_company_id()
        user_id = user_id or self._get_user_id()
        
        tasks = await self._repo.get_by_user(company_id, user_id, status, limit)
        return [self._to_response(task) for task in tasks]
    
    async def get_overdue_tasks(
        self,
        company_id: Optional[str] = None
    ) -> List[TaskResponse]:
        """Получает просроченные задачи"""
        company_id = company_id or self._get_company_id()
        
        tasks = await self._repo.get_overdue(company_id)
        return [self._to_response(task) for task in tasks]
    
    async def get_due_today(
        self,
        company_id: Optional[str] = None
    ) -> List[TaskResponse]:
        """Получает задачи с дедлайном сегодня"""
        company_id = company_id or self._get_company_id()
        
        tasks = await self._repo.get_due_today(company_id)
        return [self._to_response(task) for task in tasks]
    
    async def get_due_this_week(
        self,
        company_id: Optional[str] = None
    ) -> List[TaskResponse]:
        """Получает задачи на эту неделю"""
        company_id = company_id or self._get_company_id()
        
        tasks = await self._repo.get_due_this_week(company_id)
        return [self._to_response(task) for task in tasks]
    
    async def list_tasks(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        company_id: Optional[str] = None
    ) -> List[TaskResponse]:
        """Получает список задач с фильтрацией"""
        company_id = company_id or self._get_company_id()
        
        if status:
            tasks = await self._repo.get_by_status(company_id, status, limit)
        elif priority:
            tasks = await self._repo.get_by_priority(company_id, priority, limit)
        else:
            tasks = await self._repo.get_by_company(company_id, limit, offset)
        
        return [self._to_response(task) for task in tasks]
    
    async def get_tasks_by_entity(
        self,
        entity_id: str,
        company_id: Optional[str] = None
    ) -> List[TaskResponse]:
        """Получает задачи, связанные с сущностью"""
        company_id = company_id or self._get_company_id()
        
        tasks = await self._repo.get_by_entity(company_id, entity_id)
        return [self._to_response(task) for task in tasks]
    
    async def get_task_stats(
        self,
        company_id: Optional[str] = None
    ) -> Dict[str, int]:
        """Получает статистику по задачам"""
        company_id = company_id or self._get_company_id()
        
        stats = await self._repo.count_by_status(company_id)
        return stats
    
    async def add_tag(
        self,
        task_id: str,
        tag: str,
        company_id: Optional[str] = None
    ) -> TaskResponse:
        """Добавляет тег к задаче"""
        task = await self._repo.get(task_id)
        if not task:
            raise ValueError(f"Задача {task_id} не найдена")
        
        tags = list(task.tags or [])
        if tag not in tags:
            tags.append(tag)
            task.tags = tags
            task.updated_at = datetime.now(timezone.utc)
            await self._repo.update(task)
        
        return self._to_response(task)
    
    async def remove_tag(
        self,
        task_id: str,
        tag: str,
        company_id: Optional[str] = None
    ) -> TaskResponse:
        """Удаляет тег из задачи"""
        task = await self._repo.get(task_id)
        if not task:
            raise ValueError(f"Задача {task_id} не найдена")
        
        tags = list(task.tags or [])
        if tag in tags:
            tags.remove(tag)
            task.tags = tags
            task.updated_at = datetime.now(timezone.utc)
            await self._repo.update(task)
        
        return self._to_response(task)
    
    async def add_assignee(
        self,
        task_id: str,
        assignee_id: str,
        company_id: Optional[str] = None
    ) -> TaskResponse:
        """Добавляет соучастника к задаче"""
        task = await self._repo.get(task_id)
        if not task:
            raise ValueError(f"Задача {task_id} не найдена")
        
        assignees = list(task.assignees or [])
        if assignee_id not in assignees:
            assignees.append(assignee_id)
            task.assignees = assignees
            task.updated_at = datetime.now(timezone.utc)
            await self._repo.update(task)
        
        return self._to_response(task)
    
    async def remove_assignee(
        self,
        task_id: str,
        assignee_id: str,
        company_id: Optional[str] = None
    ) -> TaskResponse:
        """Удаляет соучастника из задачи"""
        task = await self._repo.get(task_id)
        if not task:
            raise ValueError(f"Задача {task_id} не найдена")
        
        assignees = list(task.assignees or [])
        if assignee_id in assignees:
            assignees.remove(assignee_id)
            task.assignees = assignees
            task.updated_at = datetime.now(timezone.utc)
            await self._repo.update(task)
        
        return self._to_response(task)
    
    async def get_tasks_by_tag(
        self,
        tag: str,
        limit: int = 100,
        company_id: Optional[str] = None
    ) -> List[TaskResponse]:
        """Получает задачи по тегу"""
        company_id = company_id or self._get_company_id()
        
        tasks = await self._repo.get_by_tag(company_id, tag, limit)
        return [self._to_response(task) for task in tasks]
    
    async def get_tasks_by_assignee(
        self,
        assignee_id: str,
        limit: int = 100,
        company_id: Optional[str] = None
    ) -> List[TaskResponse]:
        """Получает задачи по соучастнику"""
        company_id = company_id or self._get_company_id()
        
        tasks = await self._repo.get_by_assignee(company_id, assignee_id, limit)
        return [self._to_response(task) for task in tasks]
    
    def _to_response(self, task: Task) -> TaskResponse:
        """Конвертирует модель в response"""
        return TaskResponse(
            task_id=task.task_id,
            company_id=task.company_id,
            user_id=task.user_id,
            title=task.title,
            description=task.description,
            priority=task.priority,
            status=task.status,
            due_date=task.due_date,
            linked_entity_id=task.linked_entity_id,
            source_note_id=task.source_note_id,
            tags=getattr(task, 'tags', []) or [],
            assignees=getattr(task, 'assignees', []) or [],
            created_at=task.created_at,
            updated_at=task.updated_at,
        )

