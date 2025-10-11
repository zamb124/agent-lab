"""
Storage - простой key-value storage для всех сущностей платформы.
Поддержка маршрутизации по таблицам на основе префикса ключа и компании.
"""

import logging
import json
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, delete, Table, MetaData, text
from sqlalchemy.dialects.postgresql import insert

from app.models import AgentConfig, FlowConfig, TaskConfig, SessionConfig, SessionStatus
from app.db.database import AsyncSessionLocal
from app.db.models import Storage as StorageModel, Users as UsersModel, Variables as VariablesModel
from app.core.context import get_context

logger = logging.getLogger(__name__)

TABLE_ROUTING = {
    "user:": {"table": "users", "company_specific": False},
    "user_providers:": {"table": "users", "company_specific": False},
    "auth_session:": {"table": "users", "company_specific": False},
    "auth_state:": {"table": "users", "company_specific": False},
    "var:": {"table": "variables", "company_specific": False},
    
    "_default": {"table": "storage", "company_specific": False}
}


class Storage:
    """
    Key-value storage с поддержкой маршрутизации по таблицам.
    Поддерживает глобальные таблицы и таблицы специфичные для компаний.
    """
    def __init__(self):
        self.session_factory = None
        self._table_cache = {}
        self._metadata = MetaData()
    
    def _get_table_name(self, key: str, company_id: Optional[str] = None) -> str:
        """
        Определяет имя таблицы на основе префикса ключа и компании.
        
        Args:
            key: Ключ (например, "user:yandex:123" или "task:abc")
            company_id: ID компании (если есть)
            
        Returns:
            Имя таблицы (например, "users", "storage", "acme_tasks")
        """
        # Убираем company prefix если есть для проверки маршрута
        check_key = key
        if key.startswith("company:") and ":" in key[8:]:
            parts = key.split(":", 2)
            if len(parts) >= 3:
                check_key = parts[2]
        
        for prefix, config in TABLE_ROUTING.items():
            if prefix == "_default":
                continue
            if check_key.startswith(prefix):
                table_name = config["table"]
                if config["company_specific"] and company_id:
                    return f"{company_id}_{table_name}"
                return table_name
        
        default_config = TABLE_ROUTING["_default"]
        table_name = default_config["table"]
        if default_config["company_specific"] and company_id:
            return f"{company_id}_{table_name}"
        return table_name
    
    def _get_table_model(self, table_name: str):
        """
        Возвращает SQLAlchemy модель таблицы.
        """
        if table_name in self._table_cache:
            return self._table_cache[table_name]
        
        if table_name == "storage":
            self._table_cache[table_name] = StorageModel
            return StorageModel
        
        if table_name == "users":
            self._table_cache[table_name] = UsersModel
            return UsersModel
        
        if table_name == "variables":
            self._table_cache[table_name] = VariablesModel
            return VariablesModel
        
        table = Table(
            table_name,
            self._metadata,
            *StorageModel.__table__.columns,
            extend_existing=True,
            autoload_with=None
        )
        self._table_cache[table_name] = table
        return table

    def _get_company_key(self, key: str, force_global: bool = False) -> tuple[str, Optional[str]]:
        """
        Добавляет префикс компании к ключу если нужно.
        
        Returns:
            Кортеж (final_key, company_id)
        """
        if force_global:
            return key, None
            
        global_prefixes = [
            'company:', 'subdomain:', 
            'auth_session:', 'auth_state:',
            'web_notification:', 'media_group:'
        ]
        
        if any(key.startswith(prefix) for prefix in global_prefixes):
            return key, None
        
        context = get_context()
        if context and context.active_company:
            company_id = context.active_company.company_id
            return f"company:{company_id}:{key}", company_id
        
        return key, None

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
        final_key, company_id = self._get_company_key(key, force_global)
        table_name = self._get_table_name(key, company_id)
        
        if db_session:
            return await self._get_with_session(final_key, table_name, db_session)

        session_factory = self.session_factory or AsyncSessionLocal
        async with session_factory() as session:
            return await self._get_with_session(final_key, table_name, session)

    async def _get_with_session(self, key: str, table_name: str, session) -> Optional[str]:
        """Получает значение с использованием переданной сессии"""
        table_model = self._get_table_model(table_name)
        
        if table_name == "storage":
            result = await session.execute(
                select(StorageModel.value).where(StorageModel.key == key)
            )
        elif table_name == "users":
            result = await session.execute(
                select(UsersModel.value).where(UsersModel.key == key)
            )
        elif table_name == "variables":
            result = await session.execute(
                select(VariablesModel.value).where(VariablesModel.key == key)
            )
        else:
            query = text(f"SELECT value FROM {table_name} WHERE key = :key")
            result = await session.execute(query, {"key": key})
        
        row = result.first()
        if row:
            value = row.value if hasattr(row, 'value') else row[0]
            # JSONB поля уже dict, просто сериализуем в строку
            if isinstance(value, dict):
                return json.dumps(value)
            elif isinstance(value, str):
                return value
            else:
                return json.dumps(value)
        return None

    async def set(
        self, key: str, value: str, ttl: Optional[int] = None, db_session=None, force_global: bool = False, nx: bool = False
    ) -> bool:
        """
        Сохраняет значение по ключу с опциональным TTL.

        Args:
            key: Ключ для сохранения
            value: JSON строка для сохранения
            ttl: Время жизни в секундах (по умолчанию 5 дней = 432000 сек)
            db_session: Сессия БД (если не передана, создается новая)
            force_global: Принудительно использовать глобальный ключ без префикса компании
            nx: Set if Not eXists - устанавливает только если ключ не существует (для блокировок)

        Returns:
            True, если сохранение успешно; False если nx=True и ключ уже существует
        """
        final_key, company_id = self._get_company_key(key, force_global)
        table_name = self._get_table_name(key, company_id)
        
        if db_session:
            return await self._set_with_session(final_key, value, ttl, table_name, db_session, nx)

        session_factory = self.session_factory or AsyncSessionLocal
        async with session_factory() as session:
            result = await self._set_with_session(final_key, value, ttl, table_name, session, nx)
            await session.commit()
            return result

    async def _set_with_session(
        self, key: str, value: str, ttl: Optional[int], table_name: str, session, nx: bool = False
    ) -> bool:
        """Сохраняет значение с использованием переданной сессии"""
        json_value = json.loads(value)

        expired_at = None
        if ttl is not None:
            expired_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
        else:
            permanent_prefixes = [
                'company:', 'subdomain:', 'user:', 
                'auth_session:', 'auth_state:', 'token:'
            ]
            
            if any(key.startswith(prefix) for prefix in permanent_prefixes):
                expired_at = None
            else:
                expired_at = datetime.now(timezone.utc) + timedelta(days=5)

        if table_name == "storage":
            if nx:
                # Режим NX - вставка только если ключа не существует
                from sqlalchemy import select
                existing = await session.execute(
                    select(StorageModel).where(StorageModel.key == key)
                )
                if existing.scalar_one_or_none():
                    return False
                
                stmt = insert(StorageModel).values(
                    key=key, value=json_value, expired_at=expired_at
                )
            else:
                # Обычный режим - вставка с обновлением при конфликте
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
        elif table_name == "users":
            if nx:
                from sqlalchemy import select
                existing = await session.execute(
                    select(UsersModel).where(UsersModel.key == key)
                )
                if existing.scalar_one_or_none():
                    return False
                
                stmt = insert(UsersModel).values(
                    key=key, value=json_value, expired_at=expired_at
                )
            else:
                stmt = insert(UsersModel).values(
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
        elif table_name == "variables":
            if nx:
                from sqlalchemy import select
                existing = await session.execute(
                    select(VariablesModel).where(VariablesModel.key == key)
                )
                if existing.scalar_one_or_none():
                    return False
                
                stmt = insert(VariablesModel).values(
                    key=key, value=json_value, expired_at=expired_at
                )
            else:
                stmt = insert(VariablesModel).values(
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
        else:
            if nx:
                query = text(f"""
                    INSERT INTO {table_name} (key, value, expired_at, created_at, updated_at)
                    VALUES (:key, :value, :expired_at, :created_at, :updated_at)
                    ON CONFLICT (key) DO NOTHING
                    RETURNING key
                """)
                now = datetime.now(timezone.utc)
                result = await session.execute(query, {
                    "key": key,
                    "value": json.dumps(json_value),
                    "expired_at": expired_at,
                    "created_at": now,
                    "updated_at": now
                })
                if not result.fetchone():
                    return False
            else:
                query = text(f"""
                    INSERT INTO {table_name} (key, value, expired_at, created_at, updated_at)
                    VALUES (:key, :value, :expired_at, :created_at, :updated_at)
                    ON CONFLICT (key) DO UPDATE SET
                        value = EXCLUDED.value,
                        updated_at = EXCLUDED.updated_at,
                        expired_at = EXCLUDED.expired_at
                """)
                now = datetime.now(timezone.utc)
                await session.execute(query, {
                    "key": key,
                    "value": json.dumps(json_value),
                    "expired_at": expired_at,
                    "created_at": now,
                    "updated_at": now
                })

        logger.debug(f"Сохранено: {key} в таблицу {table_name}")
        return True

    async def delete(self, key: str, db_session=None, force_global: bool = False) -> bool:
        """
        Удаляет значение по ключу.

        Args:
            key: Ключ для удаления
            db_session: Сессия БД (если не передана, создается новая)
            force_global: Принудительно использовать глобальный ключ без префикса компании

        Returns:
            True, если удаление успешно
        """
        final_key, company_id = self._get_company_key(key, force_global)
        table_name = self._get_table_name(key, company_id)
        
        if db_session:
            return await self._delete_with_session(final_key, table_name, db_session)

        async with AsyncSessionLocal() as session:
            result = await self._delete_with_session(final_key, table_name, session)
            await session.commit()
            return result

    async def _delete_with_session(self, key: str, table_name: str, session) -> bool:
        """Удаляет значение с использованием переданной сессии"""
        if table_name == "storage":
            result = await session.execute(
                delete(StorageModel).where(StorageModel.key == key)
            )
        elif table_name == "users":
            result = await session.execute(
                delete(UsersModel).where(UsersModel.key == key)
            )
        else:
            query = text(f"DELETE FROM {table_name} WHERE key = :key")
            result = await session.execute(query, {"key": key})
        
        deleted = result.rowcount > 0
        if deleted:
            logger.debug(f"Удалено: {key} из таблицы {table_name}")
        return deleted

    # === Вспомогательные методы для удобства работы с типизированными объектами ===

    async def get_agent_config(self, agent_id: str) -> Optional[AgentConfig]:
        """Получает конфигурацию агента"""
        key = f"agent:{agent_id}"
        data = await self.get(key)
        if data is None:
            return None
        return AgentConfig.model_validate_json(data)

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
        final_prefix, company_id = self._get_company_key(prefix, force_global)
        table_name = self._get_table_name(prefix, company_id)
        
        async with AsyncSessionLocal() as session:
            if table_name == "storage":
                result = await session.execute(
                    select(StorageModel.key)
                    .where(StorageModel.key.like(f"{final_prefix}%"))
                    .limit(limit)
                )
                return [row.key for row in result]
            elif table_name == "users":
                result = await session.execute(
                    select(UsersModel.key)
                    .where(UsersModel.key.like(f"{final_prefix}%"))
                    .limit(limit)
                )
                return [row.key for row in result]
            elif table_name == "variables":
                result = await session.execute(
                    select(VariablesModel.key)
                    .where(VariablesModel.key.like(f"{final_prefix}%"))
                    .limit(limit)
                )
                return [row.key for row in result]
            else:
                query = text(f"SELECT key FROM {table_name} WHERE key LIKE :prefix LIMIT :limit")
                result = await session.execute(query, {"prefix": f"{final_prefix}%", "limit": limit})
                return [row[0] for row in result]

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

    async def find_pending_task(
        self, session_id: str, flow_id: str
    ) -> Optional[TaskConfig]:
        """
        Находит pending задачу для указанной сессии и флоу.
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

