"""
Storage - простой key-value storage для всех сущностей платформы.
Одна таблица, три метода: get, set, delete.
"""
import logging
import json
from typing import Optional, Any, Dict, List
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert

from app.core.models import AgentConfig, FlowConfig, TaskConfig, SessionConfig
from app.db.database import AsyncSessionLocal, engine
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
    
    # === Базовые методы key-value storage ===
    
    async def get(self, key: str, db_session=None) -> Optional[str]:
        """
        Получает значение по ключу.
        
        Args:
            key: Ключ для поиска
            db_session: Сессия БД (если не передана, создается новая)
            
        Returns:
            JSON строка или None, если не найдено
        """
        if db_session:
            return await self._get_with_session(key, db_session)
        
        session_factory = self.session_factory or AsyncSessionLocal
        async with session_factory() as session:
            return await self._get_with_session(key, session)
    
    async def _get_with_session(self, key: str, session) -> Optional[str]:
        """Получает значение с использованием переданной сессии"""
        result = await session.execute(
            select(StorageModel.value).where(StorageModel.key == key)
        )
        row = result.first()
        if row:
            return json.dumps(row.value) if row.value is not None else None
        return None
    
    async def set(self, key: str, value: str, ttl: Optional[int] = None, db_session=None) -> bool:
        """
        Сохраняет значение по ключу с опциональным TTL.
        
        Args:
            key: Ключ для сохранения
            value: JSON строка для сохранения
            ttl: Время жизни в секундах (по умолчанию 5 дней = 432000 сек)
            db_session: Сессия БД (если не передана, создается новая)
            
        Returns:
            True, если сохранение успешно
        """
        if db_session:
            return await self._set_with_session(key, value, ttl, db_session)
        
        session_factory = self.session_factory or AsyncSessionLocal
        async with session_factory() as session:
            result = await self._set_with_session(key, value, ttl, session)
            await session.commit()
            return result
    
    async def _set_with_session(self, key: str, value: str, ttl: Optional[int], session) -> bool:
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
                key=key,
                value=json_value,
                expired_at=expired_at
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=['key'],
                set_=dict(
                    value=stmt.excluded.value,
                    updated_at=stmt.excluded.updated_at,
                    expired_at=stmt.excluded.expired_at
                )
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
        config.updated_at = datetime.now(timezone.utc).isoformat()
        if not config.created_at:
            config.created_at = config.updated_at
        
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
        config.updated_at = datetime.now(timezone.utc).isoformat()
        if not config.created_at:
            config.created_at = config.updated_at
            
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
        if config.status.value == "processing" and not config.started_at:
            config.started_at = datetime.now(timezone.utc).isoformat()
        elif config.status.value in ["completed", "failed"] and not config.completed_at:
            config.completed_at = datetime.now(timezone.utc).isoformat()
            
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
        # session_id = "telegram_94434940_weather_flow_f7f6e3ca"
        # Нужно: session:telegram:94434940:weather_flow:f7f6e3ca
        parts = config.session_id.rsplit('_', 1)  # Разделяем только последний _
        main_part = parts[0]  # "telegram_94434940_weather_flow" 
        unique_id = parts[1]  # "f7f6e3ca"
        
        # Теперь разбираем main_part
        main_parts = main_part.split('_', 2)  # platform_user_flow
        key = f"session:{main_parts[0]}:{main_parts[1]}:{main_parts[2]}:{unique_id}"
        # Обновляем timestamp активности
        config.last_activity = datetime.now(timezone.utc).isoformat()
        if not config.created_at:
            config.created_at = config.last_activity
            
        data = config.model_dump_json()
        return await self.set(key, data)
    
    async def delete_session_config(self, session_id: str) -> bool:
        """Удаляет конфигурацию сессии"""
        key = f"session:{session_id}"
        return await self.delete(key)
    
    async def find_active_sessions(self, platform: str, user_id: str, flow_id: str) -> List[SessionConfig]:
        """Находит активные сессии пользователя"""
        from app.core.models import SessionConfig, SessionStatus
        
        # Формируем префикс для поиска
        prefix = f"session:{platform}:{user_id}:{flow_id}"
        
        # Получаем все ключи с префиксом
        keys = await self.list_by_prefix(prefix)
        
        sessions = []
        for key in keys:
            session_json = await self.get(key)
            if session_json:
                session = SessionConfig.model_validate_json(session_json)
                # Возвращаем только активные сессии
                if session.status == SessionStatus.ACTIVE:
                    sessions.append(session)
        
        return sessions
    
    # === Методы для поиска (пока заглушки, потом можно добавить индексы) ===
    
    async def list_by_prefix(self, prefix: str, limit: int = 100) -> List[str]:
        """
        Получает список ключей по префиксу.
        
        Args:
            prefix: Префикс для поиска (например, "agent:" или "flow:")
            limit: Максимальное количество результатов
            
        Returns:
            Список ключей
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(StorageModel.key)
                .where(StorageModel.key.like(f"{prefix}%"))
                .limit(limit)
            )
            return [row.key for row in result]
    
    async def get_pending_tasks(self, limit: int = 10) -> List[TaskConfig]:
        """
        Получает список задач в статусе pending.
        Это специальный метод для воркера.
        """
        async with AsyncSessionLocal() as session:
            # Запрос с фильтрацией по JSON полю status
            result = await session.execute(
                select(StorageModel.key, StorageModel.value)
                .where(StorageModel.key.like("task:%"))
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
    
    async def find_interrupted_task(self, session_id: str, flow_id: str) -> Optional[TaskConfig]:
        """
        Находит прерванную задачу (в статусе waiting_for_input) для указанной сессии и флоу.
        """
        async with AsyncSessionLocal() as session:
            # Ищем задачу в статусе waiting_for_input для данной сессии и флоу
            result = await session.execute(
                select(StorageModel.key, StorageModel.value)
                .where(StorageModel.key.like("task:%"))
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
    
    async def cleanup_expired(self) -> int:
        """
        Удаляет истекшие записи из БД и связанные S3 файлы.
        
        Returns:
            Количество удаленных записей
        """
        async with AsyncSessionLocal() as session:
            now = datetime.now(timezone.utc)
            
            # Сначала находим истекшие записи для проверки S3 файлов
            select_stmt = select(StorageModel.key, StorageModel.value).where(
                StorageModel.expired_at.is_not(None),
                StorageModel.expired_at < now
            )
            
            result = await session.execute(select_stmt)
            expired_records = result.fetchall()
            
            s3_files_deleted = 0
            
            # Проверяем каждую запись на наличие S3 файлов
            for key, value in expired_records:
                if key.startswith("s3:") and isinstance(value, dict):
                    # Это файловая запись в формате s3:provider:file_id - удаляем из S3
                    s3_key = value.get("s3_key")
                    s3_bucket = value.get("s3_bucket")
                    provider = value.get("provider")
                    
                    if s3_key and s3_bucket:
                        try:
                            # Импортируем S3 клиент локально чтобы избежать циклических импортов
                            from app.core.core_clients.s3_client import S3ClientFactory
                            
                            s3_client = S3ClientFactory.create_client_for_bucket(s3_bucket)
                            await s3_client.delete_object(s3_key)
                            s3_files_deleted += 1
                            logger.debug(f"🗑️ Удален S3 файл: {s3_bucket}/{s3_key} (provider: {provider})")
                            
                        except Exception as e:
                            logger.warning(f"❌ Не удалось удалить S3 файл {s3_bucket}/{s3_key}: {e}")
            
            # Теперь удаляем записи из БД
            delete_stmt = delete(StorageModel).where(
                StorageModel.expired_at.is_not(None),
                StorageModel.expired_at < now
            )
            
            result = await session.execute(delete_stmt)
            deleted_count = result.rowcount
            await session.commit()
            
            if deleted_count > 0:
                logger.info(f"🧹 Очищено {deleted_count} истекших записей из Storage")
                if s3_files_deleted > 0:
                    logger.info(f"🗑️ Удалено {s3_files_deleted} S3 файлов")
            
            return deleted_count