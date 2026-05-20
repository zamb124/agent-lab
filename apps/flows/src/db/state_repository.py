"""
Репозиторий для хранения состояния агентов.
Поддерживает блокировку state для многоинстансности.
"""

from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel
from sqlalchemy import text

if TYPE_CHECKING:
    from asyncpg import Connection

from apps.flows.src.models import SessionConfig, SessionStatus
from core.context import get_context
from core.db import Storage
from core.logging import get_logger
from core.state import ExecutionState

logger = get_logger(__name__)


def _execution_state_from_storage_dict(data: dict[str, Any]) -> ExecutionState:
    """Убирает устаревший ключ flow_config из JSON, переносит version в flow_config_version."""
    fc = data.pop("flow_config", None)
    if isinstance(fc, dict) and fc.get("version") and not data.get("flow_config_version"):
        data["flow_config_version"] = str(fc["version"])
    return ExecutionState.model_validate(data)


def _execution_state_for_storage(
    state: ExecutionState | dict[str, Any],
) -> ExecutionState:
    """Сериализация без тяжёлого flow_config (раньше писался в states)."""
    model = (
        ExecutionState.model_validate(state) if isinstance(state, dict) else state
    )
    payload = model.model_dump(mode="json", exclude_none=False)
    payload.pop("flow_config", None)
    return ExecutionState.model_validate(payload)


class StateData(BaseModel):
    """Модель для хранения state сессии."""

    session_id: str
    data: ExecutionState


class BaseStateRepository(ABC):
    """Базовый интерфейс для StateRepository (для InMemory реализации)."""

    @abstractmethod
    async def get(self, session_id: str) -> ExecutionState | None:
        """Получает состояние сессии."""
        pass

    @abstractmethod
    async def set(
        self, session_id: str, state: ExecutionState | dict[str, Any]
    ) -> bool:
        """Сохраняет состояние сессии (ExecutionState или dict для границы тестов/репозитория)."""
        pass

    @abstractmethod
    async def delete(self, session_id: str) -> bool:
        """Удаляет состояние сессии."""
        pass

    @abstractmethod
    async def resolve_session_id_by_flow_and_identifier(
        self, flow_id: str, lookup_id: str
    ) -> str | None:
        """По ``task_id`` или ``context_id`` возвращает ``session_id`` вида ``flow_id:context_id``."""
        pass

    async def get_for_update(
        self, session_id: str, conn: Any
    ) -> ExecutionState | None:
        """Получает состояние с блокировкой."""
        return await self.get(session_id)

    async def set_in_transaction(
        self,
        session_id: str,
        state: ExecutionState | dict[str, Any],
        conn: Any,
    ) -> bool:
        """Сохраняет состояние в рамках транзакции."""
        return await self.set(session_id, state)


class DatabaseStateRepository(BaseStateRepository):
    """
    Репозиторий для хранения состояния агентов в БД.
    States изолированы по компаниям.
    """

    is_global = False
    owner_service = "flows"

    def __init__(self, storage: Storage):
        self._storage = storage

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
                f"(is_global=False)"
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
        entity = StateData.model_validate_json(data)
        raw = entity.data.model_dump(mode="json", exclude_none=False)
        return _execution_state_from_storage_dict(raw)

    async def set(
        self, session_id: str, state: ExecutionState | dict[str, Any]
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

    async def delete(self, session_id: str) -> bool:
        """Удаляет состояние сессии."""
        final_key = self._build_final_key(self._get_key(session_id))
        return await self._storage.delete_with_table(final_key, self._get_table())

    async def get_for_update(
        self, session_id: str, conn: "Connection"
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
        value = row["value"]
        data = value if isinstance(value, str) else json.dumps(value)
        entity = StateData.model_validate_json(data)
        raw = entity.data.model_dump(mode="json", exclude_none=False)
        return _execution_state_from_storage_dict(raw)

    async def set_in_transaction(
        self,
        session_id: str,
        state: ExecutionState | dict[str, Any],
        conn: "Connection",
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
        await conn.execute(
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

            raw_id: str = row["key"]
            session_id = raw_id
            if session_id.startswith(company_state_key_prefix):
                session_id = session_id[len(company_state_key_prefix) :]

            sp = self._get_prefix()
            if session_id.startswith(sp):
                session_id = session_id[len(sp) :]

            return session_id if session_id != "" else None

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
        params: dict[str, object] = {}
        param_idx = 1

        # Добавляем company-scope фильтр если не global
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
            total_raw = count_result.scalar_one()
            total = int(total_raw)

            query = text(f"""
                SELECT key, value, created_at, updated_at FROM {table}
                WHERE {where_clause}
                ORDER BY COALESCE(created_at, '1970-01-01'::timestamptz) DESC, key DESC
                LIMIT :limit OFFSET :offset
            """)
            query_params = params.copy()
            query_params.update({"limit": limit, "offset": offset})

            result = await session.execute(query, query_params)
            rows = result.mappings().all()

            sessions: list[SessionConfig] = []
            for row in rows:
                raw_id = str(row["key"])
                raw_data = row["value"]
                if isinstance(raw_data, str):
                    raw_data = json.loads(raw_data)
                if not isinstance(raw_data, dict):
                    raise ValueError("state row value must be a JSON object")

                # Извлекаем state.data (так как храним StateData)
                state_data = raw_data.get("data", raw_data)
                if not isinstance(state_data, dict):
                    raise ValueError("state row data must be a JSON object")

                # Убираем company-scope prefix из session_id
                session_id = raw_id
                if company_state_key_prefix and session_id.startswith(company_state_key_prefix):
                    session_id = session_id[len(company_state_key_prefix):]

                user_id_value = state_data.get("user_id", "")
                user_id_from_state = user_id_value if isinstance(user_id_value, str) else ""

                session_parts = session_id.split(":") if ":" in session_id else [session_id]

                if len(session_parts) >= 3 and session_parts[0] == "eval":
                    flow_id_from_session = session_parts[1]
                    context_id_from_session = session_parts[2]
                else:
                    flow_id_from_session = session_parts[0] if session_parts else ""
                    context_id_from_session = session_parts[-1] if len(session_parts) > 1 else session_id

                messages = state_data.get("messages", [])
                message_count = len(messages) if isinstance(messages, list) else 0

                first_message = self._extract_first_message(messages)

                session = SessionConfig(
                    session_id=session_id,
                    channel="a2a",
                    user_id=user_id_from_state,
                    flow_id=flow_id_from_session,
                    context_id=context_id_from_session,
                    status=SessionStatus.ACTIVE,
                    message_count=message_count,
                    first_message=first_message,
                    created_at=row.get("created_at"),
                    last_activity=row.get("updated_at"),
                )
                sessions.append(session)

            return sessions, total

    def _extract_first_message(self, messages: list[Any]) -> str | None:
        """Извлекает первое сообщение пользователя."""
        if not messages:
            return None

        for msg in messages:
            if isinstance(msg, dict):
                msg_role = msg.get("role", "")
            else:
                msg_role = getattr(msg, "role", "")

            if isinstance(msg_role, Enum):
                msg_role = msg_role.value
            msg_role = str(msg_role).lower()

            if msg_role == "user":
                content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", None)
                if content:
                    return str(content)

                parts = msg.get("parts", []) if isinstance(msg, dict) else getattr(msg, "parts", [])
                if parts:
                    content_parts = []
                    for part in parts:
                        text = self._extract_text_from_part(part)
                        if text:
                            content_parts.append(str(text))

                    if content_parts:
                        return " ".join(content_parts)

        return None

    def _extract_text_from_part(self, part: Any) -> str | None:
        """Извлекает текст из part сообщения."""
        if isinstance(part, dict):
            root = part.get("root", part)
            if isinstance(root, dict):
                if "text" in root:
                    return root["text"]
                elif "data" in root:
                    return str(root["data"])
                elif "file" in root:
                    file_info = root["file"]
                    if isinstance(file_info, dict):
                        file_name = file_info.get("name", "")
                    else:
                        file_name = getattr(file_info, "name", "") if file_info else ""
                    return f"[File: {file_name}]" if file_name else "[File]"

        elif hasattr(part, "root"):
            root = part.root
            if hasattr(root, "text"):
                return root.text
            elif hasattr(root, "data"):
                return str(root.data)
            elif hasattr(root, "file"):
                file_obj = root.file
                file_name = getattr(file_obj, "name", None) if file_obj else None
                return f"[File: {file_name}]" if file_name else "[File]"

        elif hasattr(part, "text"):
            return part.text

        return None


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

    async def get(self, session_id: str) -> ExecutionState | None:
        """Получает состояние сессии."""
        async with self._get_lock(session_id):
            return self._storage.get(session_id)

    async def set(
        self, session_id: str, state: ExecutionState | dict[str, Any]
    ) -> bool:
        """Сохраняет состояние сессии."""
        async with self._get_lock(session_id):
            self._storage[session_id] = _execution_state_for_storage(state)
            return True

    async def delete(self, session_id: str) -> bool:
        """Удаляет состояние сессии."""
        async with self._get_lock(session_id):
            if session_id in self._storage:
                del self._storage[session_id]
                if session_id in self._locks:
                    del self._locks[session_id]
                return True
            return False

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
