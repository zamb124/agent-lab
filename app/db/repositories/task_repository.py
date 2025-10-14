"""
Репозиторий для работы с TaskConfig.
"""

import logging
import json
from typing import Optional, List
from datetime import datetime, timezone

from sqlalchemy import select

from app.db.repositories.base import BaseRepository
from app.db.repositories.storage import Storage
from app.models import TaskConfig
from app.db.database import AsyncSessionLocal
from app.db.models import Storage as StorageModel

logger = logging.getLogger(__name__)


class TaskRepository(BaseRepository[TaskConfig]):
    """Репозиторий для работы с задачами"""

    def _get_key(self, task_id: str) -> str:
        """Формирует ключ task:task_id"""
        return f"task:{task_id}"

    def _get_prefix(self) -> str:
        """Префикс для поиска задач"""
        return "task:"

    async def get(self, task_id: str) -> Optional[TaskConfig]:
        """
        Получает задачу по ID.
        
        Args:
            task_id: Идентификатор задачи
            
        Returns:
            TaskConfig или None если не найдена
        """
        key = self._get_key(task_id)
        data = await self.storage.get(key)
        if data:
            try:
                return TaskConfig.model_validate_json(data)
            except Exception as e:
                logger.error(f"Ошибка парсинга задачи {task_id}: {e}")
                return None
        return None

    async def set(self, config: TaskConfig) -> bool:
        """
        Сохраняет конфигурацию задачи.
        
        Args:
            config: Конфигурация задачи
            
        Returns:
            True если сохранение успешно
        """
        now = datetime.now(timezone.utc)
        
        if config.status.value == "processing" and not config.started_at:
            config.started_at = now
        elif config.status.value in ["completed", "failed"] and not config.completed_at:
            config.completed_at = now

        key = self._get_key(config.task_id)
        data = config.model_dump_json()
        return await self.storage.set(key, data)

    async def delete(self, task_id: str) -> bool:
        """
        Удаляет задачу по ID.
        
        Args:
            task_id: Идентификатор задачи
            
        Returns:
            True если удаление успешно
        """
        key = self._get_key(task_id)
        return await self.storage.delete(key)

    async def list_pending(self, limit: int = 10) -> List[TaskConfig]:
        """
        Получает список задач в статусе pending.
        Используется воркером для получения задач на обработку.
        
        Args:
            limit: Максимальное количество результатов
            
        Returns:
            Список задач в статусе pending
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(StorageModel.key, StorageModel.value)
                .where(StorageModel.key.like("%task:%"))
                .where(StorageModel.value["status"].astext == "pending")
                .limit(limit)
            )

            tasks = []
            rows = list(result)
            logger.info(f"Найдено {len(rows)} pending задач")
            
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
                select(StorageModel.key, StorageModel.value)
                .where(StorageModel.key.like("%task:%"))
                .where(StorageModel.value["status"].astext == "waiting_for_input")
                .where(StorageModel.value["session_id"].astext == session_id)
                .where(StorageModel.value["flow_id"].astext == flow_id)
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
                select(StorageModel.key, StorageModel.value)
                .where(StorageModel.key.like("%task:%"))
                .where(StorageModel.value["status"].astext == "pending")
                .where(StorageModel.value["session_id"].astext == session_id)
                .where(StorageModel.value["flow_id"].astext == flow_id)
                .limit(1)
            )

            row = result.fetchone()
            if row:
                task_data = row[1]
                return TaskConfig(**task_data)

            return None

