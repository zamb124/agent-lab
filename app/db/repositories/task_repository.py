"""
Репозиторий для работы с TaskConfig.
Наследуется от Storage, поэтому имеет все его методы + типизированную работу с TaskConfig.
"""

import logging
import json
from typing import Optional, List
from datetime import datetime, timezone

from sqlalchemy import select, or_

from app.db.repositories.base import BaseRepository
from app.db.repositories.storage import Storage
from app.models import TaskConfig
from app.db.database import AsyncSessionLocal
from app.db.models import Tasks as TasksModel

logger = logging.getLogger(__name__)


class TaskRepository(BaseRepository[TaskConfig]):
    """
    Репозиторий для работы с задачами.
    Наследуется от Storage, поэтому имеет все его методы (get/set/delete).
    Добавляет типизированную работу с TaskConfig через Generic[TaskConfig].
    """

    def __init__(self, storage: Storage = None):
        # Передаем model_class=TaskConfig для типизации
        super().__init__(model_class=TaskConfig, storage=storage)

    def _get_key(self, task_id: str) -> str:
        """Формирует ключ task:task_id"""
        return f"task:{task_id}"

    def _get_prefix(self) -> str:
        """Префикс для поиска задач"""
        return "task:"

    async def get(self, task_id: str) -> Optional[TaskConfig]:
        """
        Получает задачу по ID с типизацией.

        Args:
            task_id: Идентификатор задачи

        Returns:
            TaskConfig или None если не найдена
        """
        return await self._get_typed(task_id)

    async def set(self, config: TaskConfig) -> bool:
        """
        Сохраняет конфигурацию задачи с типизацией.

        Args:
            config: Конфигурация задачи

        Returns:
            True если сохранение успешно
        """
        # Обновляем timestamps
        now = datetime.now(timezone.utc)
        if config.status.value == "processing" and not config.started_at:
            config.started_at = now
        elif config.status.value in ["completed", "failed"] and not config.completed_at:
            config.completed_at = now

        return await self._set_typed(config)

    async def delete(self, task_id: str) -> bool:
        """
        Удаляет задачу по ID.

        Args:
            task_id: Идентификатор задачи

        Returns:
            True если удаление успешно
        """
        return await self._delete_typed(task_id)

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
        
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(TasksModel.key, TasksModel.value)
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
            logger.info(f"Найдено {len(rows)} pending задач готовых к выполнению")
            
            for row in rows:
                try:
                    task_data = json.dumps(row.value)
                    task = TaskConfig.model_validate_json(task_data)
                    tasks.append(task)
                    logger.info(f"Задача {task.task_id} загружена (key={row.key})")
                except Exception as e:
                    logger.error(f"Ошибка парсинга задачи {row.key}: {e}")
                    continue

            return tasks

    async def find_interrupted(
        self, session_id: str, flow_id: str
    ) -> Optional[TaskConfig]:
        """
        Находит прерванную задачу (в статусе waiting_for_input).
        
        Args:
            session_id: ID сессии
            flow_id: ID flow
            
        Returns:
            Прерванная задача или None
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(TasksModel.key, TasksModel.value)
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

    async def find_pending(
        self, session_id: str, flow_id: str
    ) -> Optional[TaskConfig]:
        """
        Находит pending задачу для указанной сессии и flow.
        
        Args:
            session_id: ID сессии
            flow_id: ID flow
            
        Returns:
            Pending задача или None
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(TasksModel.key, TasksModel.value)
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

