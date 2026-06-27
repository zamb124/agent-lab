"""
Storage - key-value storage для всех сущностей платформы.
Поддержка маршрутизации по таблицам на основе префикса ключа.

ВАЖНО: Может работать с несколькими БД:
- service БД (по умолчанию) - для сущностей сервиса
- shared БД - для общих данных (users, files, companies)

Маршрутизация определяется через TABLE_ROUTING.
"""

import json
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from types import TracebackType
from typing import TypedDict, cast

from sqlalchemy import Column, DateTime, MetaData, String, Table, delete, select, text
from sqlalchemy import func as sa_func
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.db.database import get_session_factory
from core.db.models import (
    Namespaces as NamespacesModel,
)
from core.db.models import (
    Storage as StorageModel,
)
from core.db.models import (
    Usage as UsageModel,
)
from core.db.models import (
    Users as UsersModel,
)
from core.db.models import (
    Variables as VariablesModel,
)
from core.db.utils import get_rowcount
from core.logging import get_logger
from core.models.context_models import Context
from core.types import JsonValue, parse_json_value

logger = get_logger(__name__)


class TableRoute(TypedDict):
    table: str
    company_specific: bool


KNOWN_STORAGE_TABLES: Mapping[str, Table] = {
    "storage": cast(Table, StorageModel.__table__),
    "users": cast(Table, UsersModel.__table__),
    "variables": cast(Table, VariablesModel.__table__),
    "usage": cast(Table, UsageModel.__table__),
    "namespaces": cast(Table, NamespacesModel.__table__),
}

TABLE_ROUTING: Mapping[str, TableRoute] = {
    "user:": {"table": "users", "company_specific": False},
    "user_providers:": {"table": "users", "company_specific": False},
    "auth_session:": {"table": "users", "company_specific": False},
    "auth_state:": {"table": "users", "company_specific": False},
    "var:": {"table": "variables", "company_specific": False},
    "usage:": {"table": "usage", "company_specific": False},
    "namespace:": {"table": "namespaces", "company_specific": False},
    "_default": {"table": "storage", "company_specific": False},
}

ContextGetter = Callable[[], Context | None]


def _encode_storage_value(value: JsonValue) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value)


def _row_key(value: str) -> str:
    return value


class _SessionContextManager:
    """Асинхронный контекстный менеджер для сессий БД"""

    def __init__(self, storage: "Storage"):
        self._storage: Storage = storage
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> AsyncSession:
        if self._storage.session_factory is None:
            self._storage.session_factory = await get_session_factory(self._storage.db_url)
            logger.debug("Session factory инициализирован в Storage")

        session_factory = self._storage.session_factory
        self._session = session_factory()
        return await self._session.__aenter__()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool | None:
        if self._session is not None:
            return await self._session.__aexit__(exc_type, exc_val, exc_tb)
        return None


class Storage:
    """
    Хранилище ключ-значение с поддержкой маршрутизации по таблицам.

    Аргументы:
        db_url: URL базы данных (опционально, по умолчанию из settings)
        get_context_func: Функция для получения контекста (опционально)
    """

    def __init__(
        self,
        db_url: str | None = None,
        get_context_func: ContextGetter | None = None,
    ):
        self.session_factory: async_sessionmaker[AsyncSession] | None = None
        self.db_url: str | None = db_url
        self.get_context_func: ContextGetter | None = get_context_func
        self._table_cache: dict[str, Table] = {}
        self._metadata: MetaData = MetaData()

    def get_session(self) -> _SessionContextManager:
        """Возвращает асинхронный контекстный менеджер для сессии БД"""
        return _SessionContextManager(self)

    def _get_table_name(self, key: str, company_id: str | None = None) -> str:
        """
        Определяет имя таблицы на основе префикса ключа и компании.

        Аргументы:
            key: Ключ (например, "user:yandex:123" или "task:abc")
            company_id: ID компании (если есть)

        Возвращает:
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

    def _get_table(self, table_name: str) -> Table:
        """Возвращает SQLAlchemy Table для key-value хранилища."""
        if table_name in self._table_cache:
            return self._table_cache[table_name]

        known_table = KNOWN_STORAGE_TABLES.get(table_name)
        if known_table is not None:
            self._table_cache[table_name] = known_table
            return known_table

        table = Table(
            table_name,
            self._metadata,
            Column("key", String, primary_key=True, index=True),
            Column("value", JSONB, nullable=False),
            Column("expired_at", DateTime(timezone=True)),
            Column("created_at", DateTime(timezone=True)),
            Column("updated_at", DateTime(timezone=True)),
            extend_existing=True,
            autoload_with=None,
        )
        self._table_cache[table_name] = table
        return table

    def _get_company_key(self, key: str, force_global: bool = False) -> tuple[str, str | None]:
        """
        Добавляет префикс компании к ключу если нужно.

        Возвращает:
            Кортеж (final_key, company_id)
        """
        if force_global:
            return key, None

        global_prefixes = [
            "company:",
            "subdomain:",
            "auth_session:",
            "auth_state:",
            "web_notification:",
            "media_group:",
        ]

        if any(key.startswith(prefix) for prefix in global_prefixes):
            return key, None

        if self.get_context_func:
            context = self.get_context_func()
            if context and context.active_company:
                company_id = context.active_company.company_id
                return f"company:{company_id}:{key}", company_id

        return key, None

    async def get(
        self,
        key: str,
        db_session: AsyncSession | None = None,
        force_global: bool = False,
        for_update: bool = False,
    ) -> str | None:
        """
        Получает значение по ключу.

        Аргументы:
            key: Ключ для поиска
            db_session: Сессия БД (если не передана, создается новая)
            force_global: Принудительно использовать глобальный ключ без префикса компании

        Возвращает:
            JSON строка или None, если не найдено
        """
        final_key, company_id = self._get_company_key(key, force_global)
        table_name = self._get_table_name(key, company_id)

        if db_session:
            return await self._get_with_session(final_key, table_name, db_session, for_update=for_update)

        async with self.get_session() as session:
            return await self._get_with_session(final_key, table_name, session, for_update=for_update)

    async def _get_with_session(
        self,
        key: str,
        table_name: str,
        session: AsyncSession,
        *,
        for_update: bool = False,
    ) -> str | None:
        """Получает значение с использованием переданной сессии"""
        table = self._get_table(table_name)

        stmt = select(table.c["value"], table.c["expired_at"]).where(table.c["key"] == key)
        if for_update:
            stmt = stmt.with_for_update()
        result = await session.execute(stmt)

        row = result.first()
        if row:
            expired_at_raw = cast(datetime | None, row[1])
            if expired_at_raw is not None and expired_at_raw <= datetime.now(timezone.utc):
                return None
            return _encode_storage_value(cast(JsonValue, row[0]))
        return None

    async def insert_once(
        self,
        key: str,
        value: str,
        ttl: int | None = None,
        db_session: AsyncSession | None = None,
        force_global: bool = False,
    ) -> bool:
        """Создаёт storage-запись только если ключ ещё не существует."""
        final_key, company_id = self._get_company_key(key, force_global)
        table_name = self._get_table_name(key, company_id)

        if db_session is not None:
            return await self._insert_once_with_session(final_key, value, ttl, table_name, db_session)

        async with self.get_session() as session:
            created = await self._insert_once_with_session(final_key, value, ttl, table_name, session)
            await session.commit()
            await session.flush()
            return created

    async def _insert_once_with_session(
        self,
        key: str,
        value: str,
        ttl: int | None,
        table_name: str,
        session: AsyncSession,
    ) -> bool:
        json_value = parse_json_value(value)
        expired_at = None
        if ttl is not None:
            expired_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
        table = self._get_table(table_name)
        now = datetime.now(timezone.utc)
        stmt = insert(table).values(
            key=key,
            value=json_value,
            expired_at=expired_at,
            created_at=now,
            updated_at=now,
        )
        stmt = stmt.on_conflict_do_nothing(index_elements=["key"])
        result = await session.execute(stmt)
        return get_rowcount(result) > 0

    async def set(
        self,
        key: str,
        value: str,
        ttl: int | None = None,
        db_session: AsyncSession | None = None,
        force_global: bool = False,
    ) -> bool:
        """
        Сохраняет значение по ключу с опциональным TTL.

        Аргументы:
            key: Ключ для сохранения
            value: JSON строка для сохранения
            ttl: Время жизни в секундах (по умолчанию 5 дней = 432000 сек)
            db_session: Сессия БД (если не передана, создается новая)
            force_global: Принудительно использовать глобальный ключ без префикса компании

        Возвращает:
            True, если сохранение успешно
        """
        final_key, company_id = self._get_company_key(key, force_global)
        table_name = self._get_table_name(key, company_id)

        if db_session:
            return await self._set_with_session(final_key, value, ttl, table_name, db_session)

        async with self.get_session() as session:
            result = await self._set_with_session(final_key, value, ttl, table_name, session)
            await session.commit()
            await session.flush()  # Убеждаемся что изменения видны
            return result

    async def _set_with_session(
        self,
        key: str,
        value: str,
        ttl: int | None,
        table_name: str,
        session: AsyncSession,
    ) -> bool:
        """Сохраняет значение с использованием переданной сессии"""
        json_value = parse_json_value(value)

        expired_at = None
        if ttl is not None:
            expired_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
        else:
            permanent_prefixes = [
                "company:",
                "subdomain:",
                "user:",
                "auth_session:",
                "auth_state:",
                "token:",
            ]

            if any(key.startswith(prefix) for prefix in permanent_prefixes):
                expired_at = None
            else:
                expired_at = datetime.now(timezone.utc) + timedelta(days=5)

        table = self._get_table(table_name)
        now = datetime.now(timezone.utc)
        stmt = insert(table).values(
            key=key,
            value=json_value,
            expired_at=expired_at,
            created_at=now,
            updated_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["key"],
            set_=dict(
                value=stmt.excluded["value"],
                updated_at=now,
                expired_at=stmt.excluded["expired_at"],
            ),
        )
        _ = await session.execute(stmt)

        return True

    async def delete(
        self,
        key: str,
        db_session: AsyncSession | None = None,
        force_global: bool = False,
    ) -> bool:
        """
        Удаляет значение по ключу.

        Аргументы:
            key: Ключ для удаления
            db_session: Сессия БД (если не передана, создается новая)
            force_global: Принудительно использовать глобальный ключ без префикса компании

        Возвращает:
            True, если удаление успешно
        """
        final_key, company_id = self._get_company_key(key, force_global)
        table_name = self._get_table_name(key, company_id)

        if db_session:
            return await self._delete_with_session(final_key, table_name, db_session)

        async with self.get_session() as session:
            result = await self._delete_with_session(final_key, table_name, session)
            await session.commit()
            await session.flush()  # Убеждаемся что изменения видны
            return result

    async def _delete_with_session(
        self,
        key: str,
        table_name: str,
        session: AsyncSession,
    ) -> bool:
        """Удаляет значение с использованием переданной сессии"""
        table = self._get_table(table_name)

        result = await session.execute(delete(table).where(table.c["key"] == key))

        deleted = get_rowcount(result) > 0
        if deleted:
            logger.debug(f"Удалено: {key} из таблицы {table_name}")
        return deleted

    async def list_by_prefix(
        self, prefix: str, limit: int = 100, force_global: bool = False
    ) -> list[str]:
        """
        Получает список ключей по префиксу.

        Аргументы:
            prefix: Префикс для поиска (например, "agent:" или "flow:")
            limit: Максимальное количество результатов
            force_global: Принудительно использовать глобальный поиск без префикса компании

        Возвращает:
            Список ключей
        """
        final_prefix, company_id = self._get_company_key(prefix, force_global)
        table_name = self._get_table_name(prefix, company_id)

        async with self.get_session() as session:
            table = self._get_table(table_name)
            result = await session.execute(
                select(table.c["key"]).where(table.c["key"].like(f"{final_prefix}%")).limit(limit)
            )
            return [_row_key(cast(str, row[0])) for row in result]

    async def get_all_by_prefix(
        self, prefix: str, limit: int = 1000, force_global: bool = False
    ) -> dict[str, str]:
        """
        Получает все данные по префиксу за один запрос (оптимизация N+1).

        Аргументы:
            prefix: Префикс для поиска
            limit: Максимальное количество результатов
            force_global: Принудительно использовать глобальный поиск

        Возвращает:
            Словарь {key: value_json}
        """

        final_prefix, company_id = self._get_company_key(prefix, force_global)
        table_name = self._get_table_name(prefix, company_id)

        async with self.get_session() as session:
            table = self._get_table(table_name)
            result = await session.execute(
                select(table.c["key"], table.c["value"])
                .where(table.c["key"].like(f"{final_prefix}%"))
                .limit(limit)
            )

            data: dict[str, str] = {}
            for row in result:
                key = _row_key(cast(str, row[0]))
                data[key] = _encode_storage_value(cast(JsonValue, row[1]))

            return data

    async def get_many(self, keys: list[str], force_global: bool = False) -> dict[str, str]:
        """
        Получает множество значений по списку ключей за один запрос.

        Аргументы:
            keys: Список ключей для получения
            force_global: Принудительно использовать глобальный поиск

        Возвращает:
            Словарь {key: value_json}
        """
        if not keys:
            return {}

        final_keys: list[str] = []
        key_mapping: dict[str, str] = {}
        for key in keys:
            final_key, _ = self._get_company_key(key, force_global)
            final_keys.append(final_key)
            key_mapping[final_key] = key

        table_name = self._get_table_name(keys[0], None)

        async with self.get_session() as session:
            table = self._get_table(table_name)
            result = await session.execute(
                select(table.c["key"], table.c["value"]).where(table.c["key"].in_(final_keys))
            )

            data: dict[str, str] = {}
            for row in result:
                final_key = _row_key(cast(str, row[0]))
                original_key = key_mapping.get(final_key, final_key)
                data[original_key] = _encode_storage_value(cast(JsonValue, row[1]))

            return data

    async def get_with_session_and_table(self, key: str, table_name: str) -> str | None:
        """
        Низкоуровневый метод для получения значения из конкретной таблицы.
        Используется BaseRepository.

        Аргументы:
            key: Финальный ключ (с префиксом компании если нужно)
            table_name: Имя таблицы

        Возвращает:
            JSON строка или None
        """
        async with self.get_session() as session:
            return await self._get_with_session(key, table_name, session)

    async def set_with_table(
        self, key: str, value: str, table_name: str, ttl: int | None = None
    ) -> bool:
        """
        Низкоуровневый метод для сохранения значения в конкретную таблицу.
        Используется BaseRepository.

        Аргументы:
            key: Финальный ключ (с префиксом компании если нужно)
            value: JSON строка
            table_name: Имя таблицы
            ttl: Время жизни в секундах

        Возвращает:
            True если сохранение успешно
        """
        async with self.get_session() as session:
            result = await self._set_with_session(key, value, ttl, table_name, session)
            await session.commit()
            await session.flush()
            return result

    async def delete_with_table(self, key: str, table_name: str) -> bool:
        """
        Низкоуровневый метод для удаления значения из конкретной таблицы.
        Используется BaseRepository.

        Аргументы:
            key: Финальный ключ (с префиксом компании если нужно)
            table_name: Имя таблицы

        Возвращает:
            True если удаление успешно
        """
        async with self.get_session() as session:
            result = await self._delete_with_session(key, table_name, session)
            await session.commit()
            await session.flush()
            return result

    async def get_all_by_prefix_and_table_with_json_eq(
        self,
        prefix: str,
        table_name: str,
        *,
        json_field: str,
        json_value: str,
        limit: int = 1000,
        offset: int = 0,
    ) -> dict[str, str]:
        """
        Scan по prefix + точный фильтр по top-level JSON-полю на стороне БД.

        Нужен в случаях, когда вторичный индекс по ключу не подходит (один
        логический атрибут хранится внутри `value`, например `provider` у
        LLMModel). Раньше caller'ы делали полный list + Python-фильтр
        (`list(limit=10000)` + comprehension), что превращало `list_by_provider`
        в full scan. Здесь фильтр уходит в PostgreSQL: `value->>'<field>' = ?`.
        """
        if offset < 0:
            raise ValueError("offset должен быть >= 0")
        async with self.get_session() as session:
            table = self._get_table(table_name)
            value_column = table.c["value"]
            field_filter = text("value ->> :json_field = :json_value").bindparams(
                json_field=json_field,
                json_value=json_value,
            )
            result = await session.execute(
                select(table.c["key"], value_column)
                .where(table.c["key"].like(f"{prefix}%"))
                .where(field_filter)
                .order_by(table.c["updated_at"].desc())
                .offset(offset)
                .limit(limit)
            )
            data: dict[str, str] = {}
            for row in result:
                key = _row_key(cast(str, row[0]))
                data[key] = _encode_storage_value(cast(JsonValue, row[1]))
            return data

    async def get_all_by_prefix_and_table(
        self, prefix: str, table_name: str, limit: int = 1000, offset: int = 0
    ) -> dict[str, str]:
        """
        Низкоуровневый метод для получения всех значений по префиксу из конкретной таблицы.
        Используется BaseRepository.

        Аргументы:
            prefix: Финальный префикс (с префиксом компании если нужно)
            table_name: Имя таблицы
            limit: Максимальное количество результатов
            offset: Смещение (пагинация)

        Возвращает:
            Словарь {key: value_json}
        """
        if offset < 0:
            raise ValueError("offset должен быть >= 0")
        async with self.get_session() as session:
            table = self._get_table(table_name)
            result = await session.execute(
                select(table.c["key"], table.c["value"])
                .where(table.c["key"].like(f"{prefix}%"))
                .order_by(table.c["updated_at"].desc())
                .offset(offset)
                .limit(limit)
            )

            data: dict[str, str] = {}
            for row in result:
                key = _row_key(cast(str, row[0]))
                data[key] = _encode_storage_value(cast(JsonValue, row[1]))

            return data

    async def count_by_prefix_and_table(self, prefix: str, table_name: str) -> int:
        """Считает количество записей по префиксу в таблице. Используется BaseRepository."""
        async with self.get_session() as session:
            table = self._get_table(table_name)
            result = await session.execute(
                select(sa_func.count()).where(table.c["key"].like(f"{prefix}%"))
            )
            count = result.scalar_one()
            return int(count)

    async def get_many_with_table(self, keys: list[str], table_name: str) -> dict[str, str]:
        """
        Низкоуровневый метод для получения нескольких значений из конкретной таблицы.
        Используется BaseRepository.

        Аргументы:
            keys: Список финальных ключей (с префиксом компании если нужно)
            table_name: Имя таблицы

        Возвращает:
            Словарь {key: value_json}
        """
        if not keys:
            return {}

        async with self.get_session() as session:
            table = self._get_table(table_name)
            result = await session.execute(
                select(table.c["key"], table.c["value"]).where(table.c["key"].in_(keys))
            )

            data: dict[str, str] = {}
            for row in result:
                key = _row_key(cast(str, row[0]))
                data[key] = _encode_storage_value(cast(JsonValue, row[1]))

            return data

    async def _list_keys_by_prefix_and_table(
        self, prefix: str, table_name: str, limit: int = 10000
    ) -> list[str]:
        """
        Низкоуровневый метод для получения списка ключей по префиксу из конкретной таблицы.
        Используется для массового удаления данных компании.

        Аргументы:
            prefix: Префикс ключей (например, "company:acme:agent:")
            table_name: Имя таблицы
            limit: Максимальное количество результатов

        Возвращает:
            Список ключей
        """
        async with self.get_session() as session:
            table = self._get_table(table_name)
            result = await session.execute(
                select(table.c["key"]).where(table.c["key"].like(f"{prefix}%")).limit(limit)
            )
            return [_row_key(cast(str, row[0])) for row in result]
