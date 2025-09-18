"""
Storage - простой key-value storage для всех сущностей платформы.
Одна таблица, три метода: get, set, delete.
"""

import logging
import json
from typing import Optional, List
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert

from app.models import AgentConfig, FlowConfig, TaskConfig, SessionConfig, SessionStatus
from app.db.database import AsyncSessionLocal
from app.db.models import Storage as StorageModel

logger = logging.getLogger(__name__)


class Storage:
    """
    Простой key-value storage.
    Все сущности хранятся в одной таблице с ключами типа:
    - agent:agent_id
    - flow:flow_id
    - task:task_id
    - session:session_id
    """

    def __init__(self):
        # Используем dependency injection для БД сессий
        self.session_factory = None

    def _get_company_key(self, key: str, force_global: bool = False) -> str:
        """Добавляет префикс компании к ключу если нужно"""
        if force_global:
            return key
            
        # Глобальные ключи (НЕ добавляем префикс)
        global_prefixes = [
            'user:', 'company:', 'subdomain:', 
            'auth_session:', 'auth_state:'
        ]
        
        if any(key.startswith(prefix) for prefix in global_prefixes):
            return key
        
        # Получаем контекст для определения активной компании
        try:
            from ..core.context import get_context
            context = get_context()
            
            if context and context.active_company:
                company_id = context.active_company.company_id
                return f"company:{company_id}:{key}"
        except:
            # Если контекст недоступен - возвращаем оригинальный ключ
            pass
        
        return key

    # === Базовые методы key-value storage ===

    async def get(self, key: str, db_session=None, force_global: bool = False) -> Optional[str]:
        """
        Получает значение по ключу.

        Args:
            key: Ключ для поиска
            db_session: Сессия БД (если не передана, создается новая)
            force_global: Принудительно использовать глобальный ключ без префикса компании

        Returns:
            JSON строка или None, если не найдено
        """
        final_key = self._get_company_key(key, force_global)
        
        if db_session:
            return await self._get_with_session(final_key, db_session)

        session_factory = self.session_factory or AsyncSessionLocal
        async with session_factory() as session:
            return await self._get_with_session(final_key, session)

    async def _get_with_session(self, key: str, session) -> Optional[str]:
        """Получает значение с использованием переданной сессии"""
        result = await session.execute(
            select(StorageModel.value).where(StorageModel.key == key)
        )
        row = result.first()
        if row:
            return json.dumps(row.value) if row.value is not None else None
        return None

    async def set(
        self, key: str, value: str, ttl: Optional[int] = None, db_session=None, force_global: bool = False
    ) -> bool:
        """
        Сохраняет значение по ключу с опциональным TTL.

        Args:
            key: Ключ для сохранения
            value: JSON строка для сохранения
            ttl: Время жизни в секундах (по умолчанию 5 дней = 432000 сек)
            db_session: Сессия БД (если не передана, создается новая)
            force_global: Принудительно использовать глобальный ключ без префикса компании

        Returns:
            True, если сохранение успешно
        """
        final_key = self._get_company_key(key, force_global)
        
        if db_session:
            return await self._set_with_session(final_key, value, ttl, db_session)

        session_factory = self.session_factory or AsyncSessionLocal
        async with session_factory() as session:
            result = await self._set_with_session(final_key, value, ttl, session)
            await session.commit()
            return result

    async def _set_with_session(
        self, key: str, value: str, ttl: Optional[int], session
    ) -> bool:
        """Сохраняет значение с использованием переданной сессии"""
        try:
            # Парсим JSON для сохранения как JSONB
            json_value = json.loads(value)

            # Вычисляем expired_at
            expired_at = None
            if ttl is not None:
                expired_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
            else:
                # Дефолтный TTL = 5 дней
                expired_at = datetime.now(timezone.utc) + timedelta(days=5)

            # Используем UPSERT (INSERT ... ON CONFLICT)
            stmt = insert(StorageModel).values(
                key=key, value=json_value, expired_at=expired_at
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["key"],
                set_=dict(
                    value=stmt.excluded.value,
                    updated_at=stmt.excluded.updated_at,
                    expired_at=stmt.excluded.expired_at,
                ),
            )

            await session.execute(stmt)
            logger.debug(f"Сохранено: {key}")
            return True

        except Exception as e:
            logger.error(f"Ошибка сохранения {key}: {e}")
            return False

    async def delete(self, key: str, db_session=None) -> bool:
        """
        Удаляет значение по ключу.

        Args:
            key: Ключ для удаления
            db_session: Сессия БД (если не передана, создается новая)

        Returns:
            True, если удаление успешно
        """
        if db_session:
            return await self._delete_with_session(key, db_session)

        async with AsyncSessionLocal() as session:
            result = await self._delete_with_session(key, session)
            await session.commit()
            return result

    async def _delete_with_session(self, key: str, session) -> bool:
        """Удаляет значение с использованием переданной сессии"""
        try:
            result = await session.execute(
                delete(StorageModel).where(StorageModel.key == key)
            )
            deleted = result.rowcount > 0
            if deleted:
                logger.debug(f"Удалено: {key}")
            return deleted

        except Exception as e:
            logger.error(f"Ошибка удаления {key}: {e}")
            return False

    # === Вспомогательные методы для удобства работы с типизированными объектами ===

    async def get_agent_config(self, agent_id: str) -> Optional[AgentConfig]:
        """Получает конфигурацию агента"""
        key = f"agent:{agent_id}"
        data = await self.get(key)
        if data:
            try:
                return AgentConfig.model_validate_json(data)
            except Exception as e:
                logger.error(f"Ошибка парсинга конфигурации агента {agent_id}: {e}")
                return None
        return None

    async def set_agent_config(self, config: AgentConfig) -> bool:
        """Сохраняет конфигурацию агента"""
        key = f"agent:{config.agent_id}"
        # Обновляем timestamp
        now = datetime.now(timezone.utc)
        config.updated_at = now
        if not config.created_at:
            config.created_at = now

        data = config.model_dump_json()
        return await self.set(key, data)

    async def delete_agent_config(self, agent_id: str) -> bool:
        """Удаляет конфигурацию агента"""
        key = f"agent:{agent_id}"
        return await self.delete(key)

    async def get_flow_config(self, flow_id: str) -> Optional[FlowConfig]:
        """Получает конфигурацию флоу"""
        key = f"flow:{flow_id}"
        data = await self.get(key)
        if data:
            try:
                return FlowConfig.model_validate_json(data)
            except Exception as e:
                logger.error(f"Ошибка парсинга конфигурации флоу {flow_id}: {e}")
                return None
        return None

    async def set_flow_config(self, config: FlowConfig) -> bool:
        """Сохраняет конфигурацию флоу"""
        key = f"flow:{config.flow_id}"
        # Обновляем timestamp
        now = datetime.now(timezone.utc)
        config.updated_at = now
        if not config.created_at:
            config.created_at = now

        data = config.model_dump_json()
        return await self.set(key, data)

    async def delete_flow_config(self, flow_id: str) -> bool:
        """Удаляет конфигурацию флоу"""
        key = f"flow:{flow_id}"
        return await self.delete(key)

    async def get_task_config(self, task_id: str) -> Optional[TaskConfig]:
        """Получает конфигурацию задачи"""
        key = f"task:{task_id}"
        data = await self.get(key)
        if data:
            try:
                return TaskConfig.model_validate_json(data)
            except Exception as e:
                logger.error(f"Ошибка парсинга конфигурации задачи {task_id}: {e}")
                return None
        return None

    async def set_task_config(self, config: TaskConfig) -> bool:
        """Сохраняет конфигурацию задачи"""
        key = f"task:{config.task_id}"
        # Обновляем timestamp при изменении статуса
        now = datetime.now(timezone.utc)
        if config.status.value == "processing" and not config.started_at:
            config.started_at = now
        elif config.status.value in ["completed", "failed"] and not config.completed_at:
            config.completed_at = now

        data = config.model_dump_json()
        return await self.set(key, data)

    async def delete_task_config(self, task_id: str) -> bool:
        """Удаляет конфигурацию задачи"""
        key = f"task:{task_id}"
        return await self.delete(key)

    async def get_session_config(self, session_id: str) -> Optional[SessionConfig]:
        """Получает конфигурацию сессии"""
        key = f"session:{session_id}"
        data = await self.get(key)
        if data:
            try:
                return SessionConfig.model_validate_json(data)
            except Exception as e:
                logger.error(f"Ошибка парсинга конфигурации сессии {session_id}: {e}")
                return None
        return None

    async def set_session_config(self, config: SessionConfig) -> bool:
        """Сохраняет конфигурацию сессии"""
        # Используем простой формат ключа: session:{session_id}
        key = f"session:{config.session_id}"
        # Обновляем timestamp активности
        now = datetime.now(timezone.utc)
        config.last_activity = now
        if not config.created_at:
            config.created_at = now

        data = config.model_dump_json()
        return await self.set(key, data)

    async def delete_session_config(self, session_id: str) -> bool:
        """Удаляет конфигурацию сессии"""
        key = f"session:{session_id}"
        return await self.delete(key)

    async def find_active_sessions(
        self, platform: str, user_id: str, flow_id: str
    ) -> List[SessionConfig]:
        """Находит активные сессии пользователя"""
        # Ищем все сессии с префиксом session:
        prefix = "session:"
        keys = await self.list_by_prefix(prefix)

        sessions = []
        for key in keys:
            session_json = await self.get(key)
            if session_json:
                session = SessionConfig.model_validate_json(session_json)
                # Фильтруем по платформе, пользователю и flow
                if (
                    session.platform == platform
                    and session.user_id == user_id
                    and session.flow_id == flow_id
                    and session.status
                    in [SessionStatus.ACTIVE, SessionStatus.PROCESSING]
                ):
                    sessions.append(session)

        return sessions

    # === Методы для поиска (пока заглушки, потом можно добавить индексы) ===

    async def list_by_prefix(self, prefix: str, limit: int = 100, force_global: bool = False) -> List[str]:
        """
        Получает список ключей по префиксу.

        Args:
            prefix: Префикс для поиска (например, "agent:" или "flow:")
            limit: Максимальное количество результатов
            force_global: Принудительно использовать глобальный поиск без префикса компании

        Returns:
            Список ключей
        """
        # Применяем логику компании к префиксу
        final_prefix = self._get_company_key(prefix, force_global)
        
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(StorageModel.key)
                .where(StorageModel.key.like(f"{final_prefix}%"))
                .limit(limit)
            )
            return [row.key for row in result]

    async def get_pending_tasks(self, limit: int = 10) -> List[TaskConfig]:
        """
        Получает список задач в статусе pending.
        Это специальный метод для воркера.
        """
        async with AsyncSessionLocal() as session:
            # Запрос с фильтрацией по JSON полю status - ищем во ВСЕХ компаниях
            result = await session.execute(
                select(StorageModel.key, StorageModel.value)
                .where(StorageModel.key.like("%task:%"))
                .where(StorageModel.value["status"].astext == "pending")
                .limit(limit)
            )

            tasks = []
            for row in result:
                try:
                    task_data = json.dumps(row.value)
                    task = TaskConfig.model_validate_json(task_data)
                    tasks.append(task)
                except Exception as e:
                    logger.error(f"Ошибка парсинга задачи {row.key}: {e}")
                    continue

            return tasks

    async def find_interrupted_task(
        self, session_id: str, flow_id: str
    ) -> Optional[TaskConfig]:
        """
        Находит прерванную задачу (в статусе waiting_for_input) для указанной сессии и флоу.
        """
        async with AsyncSessionLocal() as session:
            # Ищем задачу в статусе waiting_for_input для данной сессии и флоу - во ВСЕХ компаниях
            result = await session.execute(
                select(StorageModel.key, StorageModel.value)
                .where(StorageModel.key.like("%task:%"))
                .where(StorageModel.value["status"].astext == "waiting_for_input")
                .where(StorageModel.value["session_id"].astext == session_id)
                .where(StorageModel.value["flow_id"].astext == flow_id)
                .limit(1)  # Берем только одну - самую свежую
            )

            row = result.fetchone()
            if row:
                task_data = row[1]
                return TaskConfig(**task_data)

            return None

