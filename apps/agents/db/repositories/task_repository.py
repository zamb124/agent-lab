"""
Репозиторий для работы с TaskConfig.
Использует shared БД (таблица tasks), is_global=False (изолирован по компаниям).
"""

import logging
import json
from typing import Optional, List
from datetime import datetime, timezone

from sqlalchemy import select, or_

from core.db.base_repository import BaseRepository
from core.db.storage import Storage
from apps.agents.models import TaskConfig
from core.db.models import Tasks as TasksModel

logger = logging.getLogger(__name__)


class TaskRepository(BaseRepository[TaskConfig]):
    """
    Репозиторий для работы с задачами.
    is_global=False - задачи изолированы по компаниям.
    owner_service=agents - принадлежит сервису agents.
    """
    
    is_global = False
    owner_service = "agents"
    api_prefix = "task"
    
    @classmethod
    def get_service_url(cls) -> str:
        """URL сервиса agents"""
        from apps.agents.db.repositories import get_agents_service_url
        return get_agents_service_url()

    def __init__(self, storage: Storage):
        super().__init__(storage=storage, model_class=TaskConfig)

    def _get_key(self, task_id: str) -> str:
        return f"task:{task_id}"

    def _get_prefix(self) -> str:
        return "task:"

    def _get_table_name(self) -> str:
        return "tasks"

    def _extract_entity_id(self, entity: TaskConfig) -> str:
        return entity.task_id

    async def set(self, entity: TaskConfig) -> bool:
        now = datetime.now(timezone.utc)
        if entity.status.value == "processing" and not entity.started_at:
            entity.started_at = now
        elif entity.status.value in ["completed", "failed"] and not entity.completed_at:
            entity.completed_at = now
        return await super().set(entity)

    async def list_pending(self, limit: int = 10) -> List[TaskConfig]:
        """
        Получает список задач в статусе pending готовых к выполнению.
        Фильтрует по execute_at: задачи без execute_at или с execute_at <= now().
        
        Args:
            limit: Максимальное количество результатов
            
        Returns:
            Список задач в статусе pending готовых к выполнению
        """
        now = datetime.now(timezone.utc).isoformat()
        table_name = self._get_table_name()
        
        base_prefix = self._get_prefix()
        final_prefix = self._build_final_key(base_prefix)

        async with self._storage._get_session() as session:
            result = await session.execute(
                select(TasksModel.key, TasksModel.value)
                .where(TasksModel.key.like(f"{final_prefix}%"))
                .where(TasksModel.value["status"].astext == "pending")
                .where(
                    or_(
                        TasksModel.value["execute_at"].astext.is_(None),
                        TasksModel.value["execute_at"].astext <= now
                    )
                )
                .order_by(TasksModel.value["execute_at"].astext.asc().nullsfirst())
                .limit(limit)
            )

            tasks = []
            rows = list(result)
            if len(rows) > 0:
                logger.info(f"Найдено {len(rows)} pending задач готовых к выполнению")

            for row in rows:
                try:
                    task_data = json.dumps(row.value)
                    task = TaskConfig.model_validate_json(task_data)
                    tasks.append(task)
                    logger.debug(f"Задача {task.task_id} загружена (key={row.key})")
                except Exception as e:
                    logger.error(f"Ошибка парсинга задачи {row.key}: {e}")
                    continue

            return tasks

    async def find_interrupted(self, session_id: str, flow_id: str) -> Optional[TaskConfig]:
        """
        Находит прерванную задачу (в статусе waiting_for_input).
        
        Args:
            session_id: ID сессии
            flow_id: ID flow
            
        Returns:
            Прерванная задача или None
        """
        base_prefix = self._get_prefix()
        final_prefix = self._build_final_key(base_prefix)

        async with self._storage._get_session() as session:
            result = await session.execute(
                select(TasksModel.key, TasksModel.value)
                .where(TasksModel.key.like(f"{final_prefix}%"))
                .where(TasksModel.value["status"].astext == "waiting_for_input")
                .where(TasksModel.value["session_id"].astext == session_id)
                .where(TasksModel.value["flow_id"].astext == flow_id)
                .limit(1)
            )

            row = result.fetchone()
            if row:
                task_data = row[1]
                return TaskConfig(**task_data)

            return None

    async def find_pending(self, session_id: str, flow_id: str) -> Optional[TaskConfig]:
        """
        Находит pending задачу для указанной сессии и flow.
        
        Args:
            session_id: ID сессии
            flow_id: ID flow
            
        Returns:
            Pending задача или None
        """
        base_prefix = self._get_prefix()
        final_prefix = self._build_final_key(base_prefix)

        async with self._storage._get_session() as session:
            result = await session.execute(
                select(TasksModel.key, TasksModel.value)
                .where(TasksModel.key.like(f"{final_prefix}%"))
                .where(TasksModel.value["status"].astext == "pending")
                .where(TasksModel.value["session_id"].astext == session_id)
                .where(TasksModel.value["flow_id"].astext == flow_id)
                .limit(1)
            )

            row = result.fetchone()
            if row:
                task_data = row[1]
                return TaskConfig(**task_data)

            return None
