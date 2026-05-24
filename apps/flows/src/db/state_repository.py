"""
Репозиторий для хранения состояния агентов.
Поддерживает блокировку state для многоинстансности.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Mapping, Sequence
from datetime import datetime
from typing import Protocol, TypeAlias, cast, override

from a2a.types import FilePart, Message, Part, Role, TextPart
from pydantic import BaseModel
from sqlalchemy import text

from apps.flows.src.models import SessionConfig, SessionStatus
from core.context import get_context
from core.db import Storage
from core.logging import get_logger
from core.state import ExecutionState
from core.types import JsonObject, parse_json_object, require_json_object

logger = get_logger(__name__)

StateQueryParam: TypeAlias = str | int | datetime
StateStorageValue: TypeAlias = str | JsonObject
StateRowValue: TypeAlias = str | int | datetime | JsonObject | None
StateSearchRow: TypeAlias = Mapping[str, StateRowValue]


class StateTransactionConnection(Protocol):
    """Минимальный контракт asyncpg-соединения, используемый state-репозиторием."""

    def fetchrow(
        self,
        query: str,
        *args: StateQueryParam,
    ) -> Awaitable[Mapping[str, StateStorageValue] | None]: ...

    def execute(
        self,
        query: str,
        *args: StateQueryParam,
    ) -> Awaitable[str]: ...


def _execution_state_from_storage_dict(data: JsonObject) -> ExecutionState:
    """Убирает устаревший ключ flow_config из JSON, переносит version в flow_config_version."""
    payload: JsonObject = dict(data)
    flow_config = payload.pop("flow_config", None)
    if isinstance(flow_config, Mapping):
        raw_version = flow_config.get("version")
        if raw_version and not payload.get("flow_config_version"):
            payload["flow_config_version"] = str(raw_version)
    return ExecutionState.model_validate(payload)


def _execution_state_for_storage(
    state: ExecutionState | JsonObject,
) -> ExecutionState:
    """Сериализация без тяжёлого flow_config (раньше писался в states)."""
    model = ExecutionState.model_validate(state) if isinstance(state, dict) else state
    payload = require_json_object(
        model.model_dump(mode="json", exclude_none=False),
        "ExecutionState",
    )
    _ = payload.pop("flow_config", None)
    return ExecutionState.model_validate(payload)


class StateData(BaseModel):
    """Модель для хранения state сессии."""

    session_id: str
    data: ExecutionState


def _state_data_from_storage_value(value: StateStorageValue) -> StateData:
    payload = parse_json_object(value, "state row value") if isinstance(value, str) else value
    return StateData.model_validate(payload)


class BaseStateRepository(ABC):
    """Базовый интерфейс для StateRepository (для InMemory реализации)."""

    @abstractmethod
    async def get(self, session_id: str) -> ExecutionState | None:
        """Получает состояние сессии."""
        raise NotImplementedError

    @abstractmethod
    async def set(
        self, session_id: str, state: ExecutionState | JsonObject
    ) -> bool:
        """Сохраняет состояние сессии (ExecutionState или dict для границы тестов/репозитория)."""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, session_id: str) -> bool:
        """Удаляет состояние сессии."""
        raise NotImplementedError

    @abstractmethod
    async def resolve_session_id_by_flow_and_identifier(
        self, flow_id: str, lookup_id: str
    ) -> str | None:
        """По ``task_id`` или ``context_id`` возвращает ``session_id`` вида ``flow_id:context_id``."""
        raise NotImplementedError

    async def get_for_update(
        self, session_id: str, conn: StateTransactionConnection
    ) -> ExecutionState | None:
        """Получает состояние с блокировкой."""
        _ = conn
        return await self.get(session_id)

    async def set_in_transaction(
        self,
        session_id: str,
        state: ExecutionState | JsonObject,
        conn: StateTransactionConnection,
    ) -> bool:
        """Сохраняет состояние в рамках транзакции."""
        _ = conn
        return await self.set(session_id, state)


class DatabaseStateRepository(BaseStateRepository):
    """
    Репозиторий для хранения состояния агентов в БД.
    States изолированы по компаниям.
    """

    is_global: bool = False
    owner_service: str = "flows"

    def __init__(self, storage: Storage):
        self._storage: Storage = storage

    def _get_key(self, entity_id: str) -> str:
        return f"state:{entity_id}"

    def _get_prefix(self) -> str:
        return "state:"

    def _get_table_name(self) -> str:
        return "states"

    def _get_table(self) -> str:
        return "states"

    def _extract_entity_id(self, entity: StateData) -> str:
        return entity.session_id

    def _build_final_key(self, key: str) -> str:
        if self.is_global:
            return key
        context = get_context()
        if not context or not context.active_company:
            raise ValueError(
                f"Репозиторий {self.__class__.__name__} требует активную компанию в контексте "
                + "(is_global=False)"
            )
        company_identifier = context.active_company.subdomain or context.active_company.company_id
        return f"company:{company_identifier}:{key}"

    def _build_final_prefix(self) -> str | None:
        if self.is_global:
            return None
        context = get_context()
        if not context or not context.active_company:
            return None
        company_identifier = context.active_company.subdomain or context.active_company.company_id
        return f"company:{company_identifier}:{self._get_prefix()}"

    @override
    async def get(self, session_id: str) -> ExecutionState | None:
        """
        Получает состояние сессии.

        Args:
            session_id: ID сессии

        Returns:
            ExecutionState или None
        """
        final_key = self._build_final_key(self._get_key(session_id))
        data = await self._storage.get_with_session_and_table(final_key, self._get_table())
        if data is None:
            return None
        entity = _state_data_from_storage_value(data)
        raw = require_json_object(
            entity.data.model_dump(mode="json", exclude_none=False),
            "ExecutionState",
        )
        return _execution_state_from_storage_dict(raw)

    @override
    async def set(
        self, session_id: str, state: ExecutionState | JsonObject
    ) -> bool:
        """
        Сохраняет состояние сессии.

        Args:
            session_id: ID сессии
            state: ExecutionState или dict (как после model_dump)

        Returns:
            True если успешно
        """
        to_store = _execution_state_for_storage(state)
        entity = StateData(session_id=session_id, data=to_store)
        final_key = self._build_final_key(self._get_key(session_id))
        return await self._storage.set_with_table(
            final_key,
            entity.model_dump_json(),
            self._get_table(),
        )

    @override
    async def delete(self, session_id: str) -> bool:
        """Удаляет состояние сессии."""
        final_key = self._build_final_key(self._get_key(session_id))
        return await self._storage.delete_with_table(final_key, self._get_table())

    @override
    async def get_for_update(
        self, session_id: str, conn: StateTransactionConnection
    ) -> ExecutionState | None:
        """
        Получает состояние с блокировкой строки (FOR UPDATE).

        Args:
            session_id: ID сессии
            conn: Активное соединение (должно быть в транзакции)

        Returns:
            ExecutionState или None
        """
        final_key = self._build_final_key(self._get_key(session_id))
        row = await conn.fetchrow(
            f"SELECT value FROM {self._get_table()} WHERE key = $1 FOR UPDATE",
            final_key,
        )
        if row is None:
            return None
        entity = _state_data_from_storage_value(row["value"])
        raw = require_json_object(
            entity.data.model_dump(mode="json", exclude_none=False),
            "ExecutionState",
        )
        return _execution_state_from_storage_dict(raw)

    @override
    async def set_in_transaction(
        self,
        session_id: str,
        state: ExecutionState | JsonObject,
        conn: StateTransactionConnection,
    ) -> bool:
        """
        Сохраняет состояние в рамках транзакции.

        Args:
            session_id: ID сессии
            state: ExecutionState или dict
            conn: Активное соединение

        Returns:
            True если успешно
        """
        final_key = self._build_final_key(self._get_key(session_id))
        to_store = _execution_state_for_storage(state)
        entity = StateData(session_id=session_id, data=to_store)
        data = entity.model_dump_json()
        _ = await conn.execute(
            f"""
            INSERT INTO {self._get_table()} (key, value, created_at, updated_at)
            VALUES ($1, $2::jsonb, NOW(), NOW())
            ON CONFLICT (key) DO UPDATE SET
                value = EXCLUDED.value,
                updated_at = NOW()
            """,
            final_key,
            data,
        )
        return True

    @override
    async def resolve_session_id_by_flow_and_identifier(
        self, flow_id: str, lookup_id: str
    ) -> str | None:
        if self._storage.session_factory is None:
            raise RuntimeError("Storage не подключен")

        company_state_key_prefix = self._build_final_prefix()
        if not company_state_key_prefix:
            raise ValueError(
                "resolve_session_id_by_flow_and_identifier requires company-scoped repository"
            )

        table = self._get_table()
        async with self._storage.get_session() as session:
            query = text(f"""
                SELECT key FROM {table}
                WHERE key LIKE :company_state_key_prefix
                  AND key LIKE :flow_pattern
                  AND (
                      (value->'data'->>'task_id') = :lookup_id
                      OR (value->'data'->>'context_id') = :lookup_id
                  )
                ORDER BY COALESCE(updated_at, created_at, '1970-01-01'::timestamptz) DESC, key DESC
                LIMIT 1
            """)
            result = await session.execute(
                query,
                {
                    "company_state_key_prefix": f"{company_state_key_prefix}%",
                    "flow_pattern": f"%{flow_id}:%",
                    "lookup_id": lookup_id,
                },
            )
            row = result.mappings().first()
            if row is None:
                return None

            row_mapping = cast(Mapping[str, str], row)
            raw_id = row_mapping["key"]
            session_id = raw_id
            if session_id.startswith(company_state_key_prefix):
                session_id = session_id[len(company_state_key_prefix) :]

            sp = self._get_prefix()
            if session_id.startswith(sp):
                session_id = session_id[len(sp) :]

            if session_id == "":
                raise ValueError("state key resolved to empty session_id")
            return session_id

    async def search_sessions(
        self,
        user_id: str | None = None,
        flow_id: str | None = None,
        branch_id: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[SessionConfig], int]:
        """
        Поиск сессий с фильтрами.

        Args:
            user_id: Фильтр по пользователю
            flow_id: Фильтр по агенту
            date_from: Начало периода
            date_to: Конец периода
            limit: Максимум записей
            offset: Смещение

        Returns:
            Кортеж (список сессий, общее количество)
        """
        if self._storage.session_factory is None:
            raise RuntimeError("Storage не подключен")

        conditions: list[str] = []
        params: dict[str, StateQueryParam] = {}
        param_idx = 1

        company_state_key_prefix = self._build_final_prefix()
        if company_state_key_prefix:
            param_name = f"param{param_idx}"
            conditions.append(f"key LIKE :{param_name}")
            params[param_name] = f"{company_state_key_prefix}%"
            param_idx += 1

        if user_id:
            param_name = f"param{param_idx}"
            conditions.append(f"(value->'data'->>'user_id') = :{param_name}")
            params[param_name] = user_id
            param_idx += 1

        if flow_id:
            param_name = f"param{param_idx}"
            conditions.append(f"key LIKE :{param_name}")
            params[param_name] = f"%{flow_id}:%"
            param_idx += 1

        if branch_id:
            param_name = f"param{param_idx}"
            conditions.append(f"(value->'data'->>'branch_id') = :{param_name}")
            params[param_name] = branch_id
            param_idx += 1

        if date_from:
            param_name = f"param{param_idx}"
            conditions.append(f"created_at >= :{param_name}")
            params[param_name] = date_from
            param_idx += 1

        if date_to:
            param_name = f"param{param_idx}"
            conditions.append(f"created_at <= :{param_name}")
            params[param_name] = date_to
            param_idx += 1

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        table = self._get_table()

        async with self._storage.get_session() as session:
            count_query = text(f"SELECT COUNT(*) FROM {table} WHERE {where_clause}")
            count_result = await session.execute(count_query, params)
            total = cast(int, count_result.scalar_one())

            query = text(f"""
                SELECT key, value, created_at, updated_at FROM {table}
                WHERE {where_clause}
                ORDER BY COALESCE(created_at, '1970-01-01'::timestamptz) DESC, key DESC
                LIMIT :limit OFFSET :offset
            """)
            query_params: dict[str, StateQueryParam] = {
                **params,
                "limit": limit,
                "offset": offset,
            }

            result = await session.execute(query, query_params)
            rows = cast(Sequence[StateSearchRow], result.mappings().all())

            sessions: list[SessionConfig] = []
            for row in rows:
                raw_session_key = row["key"]
                if not isinstance(raw_session_key, str):
                    raise TypeError("state row key must be str")

                raw_storage_value = row["value"]
                if not isinstance(raw_storage_value, str | dict):
                    raise TypeError("state row value must be StateData JSON")

                state_data = _state_data_from_storage_value(raw_storage_value)
                execution_state = state_data.data

                session_id = raw_session_key
                if company_state_key_prefix and session_id.startswith(company_state_key_prefix):
                    session_id = session_id[len(company_state_key_prefix) :]
                state_key_prefix = self._get_prefix()
                if session_id.startswith(state_key_prefix):
                    session_id = session_id[len(state_key_prefix) :]

                session_parts = session_id.split(":")

                if len(session_parts) == 2:
                    flow_id_from_session = session_parts[0]
                    context_id_from_session = session_parts[1]
                elif len(session_parts) >= 3 and session_parts[0] == "eval":
                    flow_id_from_session = session_parts[1]
                    context_id_from_session = session_parts[2]
                else:
                    raise ValueError(f"state session_id must be flow_id:context_id, got: {session_id}")

                created_at = row["created_at"]
                if created_at is not None and not isinstance(created_at, datetime):
                    raise TypeError("state row created_at must be datetime")
                updated_at = row["updated_at"]
                if updated_at is not None and not isinstance(updated_at, datetime):
                    raise TypeError("state row updated_at must be datetime")

                session = SessionConfig(
                    session_id=session_id,
                    channel="a2a",
                    user_id=execution_state.user_id,
                    flow_id=flow_id_from_session,
                    context_id=context_id_from_session,
                    status=SessionStatus.ACTIVE,
                    message_count=len(execution_state.messages),
                    first_message=self._extract_first_message(execution_state.messages),
                    created_at=created_at,
                    last_activity=updated_at,
                )
                sessions.append(session)

            return sessions, total

    def _extract_first_message(self, messages: Sequence[Message]) -> str | None:
        """Извлекает первое сообщение пользователя."""
        for message in messages:
            if message.role != Role.user:
                continue
            content_parts: list[str] = []
            for part in message.parts:
                text_content = self._extract_text_from_part(part)
                if text_content:
                    content_parts.append(text_content)
            if content_parts:
                return " ".join(content_parts)
        return None

    def _extract_text_from_part(self, part: Part) -> str | None:
        """Извлекает текст из part сообщения."""
        root = part.root
        if isinstance(root, TextPart):
            return root.text
        if isinstance(root, FilePart):
            file_name = root.file.name
            return f"[File: {file_name}]" if file_name else "[File]"
        return root.model_dump_json()


class InMemoryStateRepository(BaseStateRepository):
    """
    In-memory репозиторий для хранения состояния агентов.
    Используется для внешних агентов без БД.
    """

    def __init__(self):
        self._storage: dict[str, ExecutionState] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, session_id: str) -> asyncio.Lock:
        """Получает или создает блокировку для сессии."""
        if session_id not in self._locks:
            self._locks[session_id] = asyncio.Lock()
        return self._locks[session_id]

    @override
    async def get(self, session_id: str) -> ExecutionState | None:
        """Получает состояние сессии."""
        async with self._get_lock(session_id):
            return self._storage.get(session_id)

    @override
    async def set(
        self, session_id: str, state: ExecutionState | JsonObject
    ) -> bool:
        """Сохраняет состояние сессии."""
        async with self._get_lock(session_id):
            self._storage[session_id] = _execution_state_for_storage(state)
            return True

    @override
    async def delete(self, session_id: str) -> bool:
        """Удаляет состояние сессии."""
        async with self._get_lock(session_id):
            if session_id in self._storage:
                del self._storage[session_id]
                if session_id in self._locks:
                    del self._locks[session_id]
                return True
            return False

    @override
    async def resolve_session_id_by_flow_and_identifier(
        self, flow_id: str, lookup_id: str
    ) -> str | None:
        prefix = f"{flow_id}:"
        for sid, state in tuple(self._storage.items()):
            if not sid.startswith(prefix):
                continue
            if state.task_id == lookup_id or state.context_id == lookup_id:
                return sid
        return None
