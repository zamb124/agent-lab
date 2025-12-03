"""
Storage - key-value storage для всех сущностей платформы.
Поддержка маршрутизации по таблицам на основе префикса ключа.

ВАЖНО: Может работать с несколькими БД:
- service БД (по умолчанию) - для сущностей сервиса
- shared БД - для общих данных (users, files, companies)

Маршрутизация определяется через TABLE_ROUTING.
"""

import logging
import json
from typing import Optional, List
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, delete, Table, MetaData, text
from sqlalchemy.dialects.postgresql import insert

from core.db.database import get_session_factory
from core.db.models import (
    Storage as StorageModel,
    Users as UsersModel,
    Variables as VariablesModel,
    OtelSpans as OtelSpansModel
)

logger = logging.getLogger(__name__)

TABLE_MODELS = {
    "storage": StorageModel,
    "users": UsersModel,
    "variables": VariablesModel,
    "otel_spans": OtelSpansModel,
}

TABLE_ROUTING = {
    "user:": {"table": "users", "company_specific": False},
    "user_providers:": {"table": "users", "company_specific": False},
    "auth_session:": {"table": "users", "company_specific": False},
    "auth_state:": {"table": "users", "company_specific": False},
    "var:": {"table": "variables", "company_specific": False},
    "otel:": {"table": "otel_spans", "company_specific": False},
    "_default": {"table": "storage", "company_specific": False}
}


class _SessionContextManager:
    """Асинхронный контекстный менеджер для сессий БД"""

    def __init__(self, storage: "Storage"):
        self.storage = storage
        self.session = None

    async def __aenter__(self):
        if self.storage.session_factory is None:
            self.storage.session_factory = await get_session_factory(self.storage.db_url)
            logger.debug("Session factory инициализирован в Storage")

        self.session = self.storage.session_factory()
        return await self.session.__aenter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            return await self.session.__aexit__(exc_type, exc_val, exc_tb)


class Storage:
    """
    Key-value storage с поддержкой маршрутизации по таблицам.
    
    Args:
        db_url: URL базы данных (опционально, по умолчанию из settings)
        get_context_func: Функция для получения контекста (опционально)
    """
    def __init__(self, db_url: Optional[str] = None, get_context_func=None):
        self.session_factory = None
        self.db_url = db_url
        self.get_context_func = get_context_func
        self._table_cache = {}
        self._metadata = MetaData()

    def _get_session(self):
        """Возвращает асинхронный контекстный менеджер для сессии БД"""
        return _SessionContextManager(self)

    def _get_table_name(self, key: str, company_id: Optional[str] = None) -> str:
        """
        Определяет имя таблицы на основе префикса ключа и компании.

        Args:
            key: Ключ (например, "user:yandex:123" или "task:abc")
            company_id: ID компании (если есть)

        Returns:
            Имя таблицы (например, "users", "storage", "acme_tasks")
        """
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
        """Возвращает SQLAlchemy модель таблицы."""
        if table_name in self._table_cache:
            return self._table_cache[table_name]

        if table_name in TABLE_MODELS:
            model = TABLE_MODELS[table_name]
            self._table_cache[table_name] = model
            return model

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
            'web_notification:', 'media_group:',
        ]

        if any(key.startswith(prefix) for prefix in global_prefixes):
            return key, None

        if self.get_context_func:
            context = self.get_context_func()
            if context and context.active_company:
                company_id = context.active_company.company_id
                return f"company:{company_id}:{key}", company_id

        return key, None

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

        async with self._get_session() as session:
            return await self._get_with_session(final_key, table_name, session)

    async def _get_with_session(self, key: str, table_name: str, session) -> Optional[str]:
        """Получает значение с использованием переданной сессии"""
        model = self._get_table_model(table_name)
        
        if model in TABLE_MODELS.values():
            result = await session.execute(
                select(model.value).where(model.key == key)
            )
        else:
            query = text(f"SELECT value FROM {table_name} WHERE key = :key")
            result = await session.execute(query, {"key": key})

        row = result.first()
        if row:
            value = row.value if hasattr(row, 'value') else row[0]
            if isinstance(value, dict):
                return json.dumps(value)
            elif isinstance(value, str):
                return value
            else:
                return json.dumps(value)
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
        final_key, company_id = self._get_company_key(key, force_global)
        table_name = self._get_table_name(key, company_id)
        
        if db_session:
            return await self._set_with_session(final_key, value, ttl, table_name, db_session)

        async with self._get_session() as session:
            result = await self._set_with_session(final_key, value, ttl, table_name, session)
            await session.commit()
            await session.flush()  # Убеждаемся что изменения видны
            return result

    async def _set_with_session(
        self, key: str, value: str, ttl: Optional[int], table_name: str, session
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

        model = self._get_table_model(table_name)
        
        if model in TABLE_MODELS.values():
            # Используем правильный синтаксис для ON CONFLICT с primary key
            now = datetime.now(timezone.utc)
            stmt = insert(model).values(
                key=key, value=json_value, expired_at=expired_at, updated_at=now
            )
            # Для primary key используем index_elements - это работает для primary key
            stmt = stmt.on_conflict_do_update(
                index_elements=["key"],
                set_=dict(
                    value=stmt.excluded.value,
                    updated_at=now,
                    expired_at=stmt.excluded.expired_at,
                ),
            )
            await session.execute(stmt)
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

        async with self._get_session() as session:
            result = await self._delete_with_session(final_key, table_name, session)
            await session.commit()
            await session.flush()  # Убеждаемся что изменения видны
            return result

    async def _delete_with_session(self, key: str, table_name: str, session) -> bool:
        """Удаляет значение с использованием переданной сессии"""
        model = self._get_table_model(table_name)
        
        if model in TABLE_MODELS.values():
            result = await session.execute(
                delete(model).where(model.key == key)
            )
        else:
            query = text(f"DELETE FROM {table_name} WHERE key = :key")
            result = await session.execute(query, {"key": key})

        deleted = result.rowcount > 0
        if deleted:
            logger.debug(f"Удалено: {key} из таблицы {table_name}")
        return deleted

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

        async with self._get_session() as session:
            model = self._get_table_model(table_name)
            
            if model in TABLE_MODELS.values():
                result = await session.execute(
                    select(model.key)
                    .where(model.key.like(f"{final_prefix}%"))
                    .limit(limit)
                )
                return [row.key for row in result]
            else:
                query = text(f"SELECT key FROM {table_name} WHERE key LIKE :prefix LIMIT :limit")
                result = await session.execute(query, {"prefix": f"{final_prefix}%", "limit": limit})
                return [row[0] for row in result]

    async def get_all_by_prefix(self, prefix: str, limit: int = 1000, force_global: bool = False) -> dict[str, str]:
        """
        Получает все данные по префиксу за один запрос (оптимизация N+1).

        Args:
            prefix: Префикс для поиска
            limit: Максимальное количество результатов
            force_global: Принудительно использовать глобальный поиск

        Returns:
            Словарь {key: value_json}
        """

        final_prefix, company_id = self._get_company_key(prefix, force_global)
        table_name = self._get_table_name(prefix, company_id)

        async with self._get_session() as session:
            model = self._get_table_model(table_name)
            
            if model in TABLE_MODELS.values():
                result = await session.execute(
                    select(model.key, model.value)
                    .where(model.key.like(f"{final_prefix}%"))
                    .limit(limit)
                )
            else:
                query = text(f"SELECT key, value FROM {table_name} WHERE key LIKE :prefix LIMIT :limit")
                result = await session.execute(query, {"prefix": f"{final_prefix}%", "limit": limit})

            data = {}
            for row in result:
                key = row.key if hasattr(row, 'key') else row[0]
                value = row.value if hasattr(row, 'value') else row[1]

                if isinstance(value, dict):
                    data[key] = json.dumps(value)
                elif isinstance(value, str):
                    data[key] = value
                else:
                    data[key] = json.dumps(value)

            return data

    async def get_many(self, keys: List[str], force_global: bool = False) -> dict[str, str]:
        """
        Получает множество значений по списку ключей за один запрос.

        Args:
            keys: Список ключей для получения
            force_global: Принудительно использовать глобальный поиск

        Returns:
            Словарь {key: value_json}
        """
        if not keys:
            return {}

        final_keys = []
        key_mapping = {}
        for key in keys:
            final_key, _ = self._get_company_key(key, force_global)
            final_keys.append(final_key)
            key_mapping[final_key] = key

        table_name = self._get_table_name(keys[0], None)

        async with self._get_session() as session:
            model = self._get_table_model(table_name)
            
            if model in TABLE_MODELS.values():
                result = await session.execute(
                    select(model.key, model.value)
                    .where(model.key.in_(final_keys))
                )
            else:
                placeholders = ','.join([f':key{i}' for i in range(len(final_keys))])
                query = text(f"SELECT key, value FROM {table_name} WHERE key IN ({placeholders})")
                params = {f'key{i}': k for i, k in enumerate(final_keys)}
                result = await session.execute(query, params)

            data = {}
            for row in result:
                final_key = row.key if hasattr(row, 'key') else row[0]
                value = row.value if hasattr(row, 'value') else row[1]

                original_key = key_mapping.get(final_key, final_key)

                if isinstance(value, dict):
                    data[original_key] = json.dumps(value)
                elif isinstance(value, str):
                    data[original_key] = value
                else:
                    data[original_key] = json.dumps(value)

            return data

    async def _get_with_session_and_table(self, key: str, table_name: str) -> Optional[str]:
        """
        Низкоуровневый метод для получения значения из конкретной таблицы.
        Используется BaseRepository.
        
        Args:
            key: Финальный ключ (с префиксом компании если нужно)
            table_name: Имя таблицы
            
        Returns:
            JSON строка или None
        """
        async with self._get_session() as session:
            return await self._get_with_session(key, table_name, session)

    async def _set_with_table(self, key: str, value: str, table_name: str, ttl: Optional[int] = None) -> bool:
        """
        Низкоуровневый метод для сохранения значения в конкретную таблицу.
        Используется BaseRepository.
        
        Args:
            key: Финальный ключ (с префиксом компании если нужно)
            value: JSON строка
            table_name: Имя таблицы
            ttl: Время жизни в секундах
            
        Returns:
            True если сохранение успешно
        """
        async with self._get_session() as session:
            result = await self._set_with_session(key, value, ttl, table_name, session)
            await session.commit()
            await session.flush()
            return result

    async def _delete_with_table(self, key: str, table_name: str) -> bool:
        """
        Низкоуровневый метод для удаления значения из конкретной таблицы.
        Используется BaseRepository.
        
        Args:
            key: Финальный ключ (с префиксом компании если нужно)
            table_name: Имя таблицы
            
        Returns:
            True если удаление успешно
        """
        async with self._get_session() as session:
            result = await self._delete_with_session(key, table_name, session)
            await session.commit()
            await session.flush()
            return result

    async def _get_all_by_prefix_and_table(
        self, prefix: str, table_name: str, limit: int = 1000
    ) -> dict[str, str]:
        """
        Низкоуровневый метод для получения всех значений по префиксу из конкретной таблицы.
        Используется BaseRepository.
        
        Args:
            prefix: Финальный префикс (с префиксом компании если нужно)
            table_name: Имя таблицы
            limit: Максимальное количество результатов
            
        Returns:
            Словарь {key: value_json}
        """
        async with self._get_session() as session:
            model = self._get_table_model(table_name)
            
            if model in TABLE_MODELS.values():
                result = await session.execute(
                    select(model.key, model.value)
                    .where(model.key.like(f"{prefix}%"))
                    .limit(limit)
                )
            else:
                query = text(f"SELECT key, value FROM {table_name} WHERE key LIKE :prefix LIMIT :limit")
                result = await session.execute(query, {"prefix": f"{prefix}%", "limit": limit})

            data = {}
            for row in result:
                key = row.key if hasattr(row, 'key') else row[0]
                value = row.value if hasattr(row, 'value') else row[1]

                if isinstance(value, dict):
                    data[key] = json.dumps(value)
                elif isinstance(value, str):
                    data[key] = value
                else:
                    data[key] = json.dumps(value)

            return data

    async def _get_many_with_table(self, keys: List[str], table_name: str) -> dict[str, str]:
        """
        Низкоуровневый метод для получения нескольких значений из конкретной таблицы.
        Используется BaseRepository.
        
        Args:
            keys: Список финальных ключей (с префиксом компании если нужно)
            table_name: Имя таблицы
            
        Returns:
            Словарь {key: value_json}
        """
        if not keys:
            return {}

        async with self._get_session() as session:
            model = self._get_table_model(table_name)
            
            if model in TABLE_MODELS.values():
                result = await session.execute(
                    select(model.key, model.value)
                    .where(model.key.in_(keys))
                )
            else:
                placeholders = ','.join([f':key{i}' for i in range(len(keys))])
                query = text(f"SELECT key, value FROM {table_name} WHERE key IN ({placeholders})")
                params = {f'key{i}': k for i, k in enumerate(keys)}
                result = await session.execute(query, params)

            data = {}
            for row in result:
                key = row.key if hasattr(row, 'key') else row[0]
                value = row.value if hasattr(row, 'value') else row[1]

                if isinstance(value, dict):
                    data[key] = json.dumps(value)
                elif isinstance(value, str):
                    data[key] = value
                else:
                    data[key] = json.dumps(value)

            return data

    async def _list_keys_by_prefix_and_table(
        self, prefix: str, table_name: str, limit: int = 10000
    ) -> List[str]:
        """
        Низкоуровневый метод для получения списка ключей по префиксу из конкретной таблицы.
        Используется для массового удаления данных компании.
        
        Args:
            prefix: Префикс ключей (например, "company:acme:agent:")
            table_name: Имя таблицы
            limit: Максимальное количество результатов
            
        Returns:
            Список ключей
        """
        async with self._get_session() as session:
            model = self._get_table_model(table_name)
            
            if model in TABLE_MODELS.values():
                result = await session.execute(
                    select(model.key)
                    .where(model.key.like(f"{prefix}%"))
                    .limit(limit)
                )
                return [row.key for row in result]
            else:
                query = text(f"SELECT key FROM {table_name} WHERE key LIKE :prefix LIMIT :limit")
                result = await session.execute(query, {"prefix": f"{prefix}%", "limit": limit})
                return [row[0] for row in result]
