"""
Репозиторий для работы с User.
Использует shared БД, is_global=True (не изолирован по компаниям).
"""

import json
import logging
from typing import Optional

from sqlalchemy import select, cast, text
from sqlalchemy.dialects.postgresql import JSONB

from core.db.base_repository import BaseRepository
from core.db.models import Users as UsersModel
from core.db.storage import Storage
from core.models.identity_models import User

logger = logging.getLogger(__name__)


class UserRepository(BaseRepository[User]):
    """
    Репозиторий для работы с пользователями.
    is_global=True - пользователи не изолированы по компаниям.
    """
    
    is_global = True

    def __init__(self, storage: Storage):
        super().__init__(storage=storage, model_class=User)

    def _get_key(self, user_id: str) -> str:
        return f"user:{user_id}"

    def _get_prefix(self) -> str:
        return "user:"

    def _get_table_name(self) -> str:
        return "users"

    def _extract_entity_id(self, entity: User) -> str:
        return entity.user_id

    async def find_by_email(self, email: str) -> Optional[User]:
        """Поиск пользователя по email (JSONB containment по полю emails)."""
        async with self._storage._get_session() as session:
            emails_json = cast(json.dumps([email]), JSONB)
            result = await session.execute(
                select(UsersModel.value)
                .where(
                    UsersModel.key.like("user:%"),
                    UsersModel.value["emails"].contains(emails_json),
                )
                .limit(1)
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            raw = json.dumps(row) if isinstance(row, dict) else row
            return User.model_validate_json(raw)

    async def find_all_by_email_ci(self, email: str) -> list[User]:
        """Все пользователи, у которых в emails есть адрес без учёта регистра."""
        norm = email.strip().lower()
        if not norm:
            raise ValueError("email для поиска не может быть пустым")
        q = text("""
            SELECT u.value FROM users u
            WHERE u.key LIKE 'user:%'
            AND EXISTS (
                SELECT 1
                FROM jsonb_array_elements_text(u.value->'emails') AS e(elt)
                WHERE lower(e.elt) = :norm
            )
            ORDER BY u.key
        """)
        async with self._storage._get_session() as session:
            result = await session.execute(q, {"norm": norm})
            out: list[User] = []
            for row in result.scalars():
                raw = json.dumps(row) if isinstance(row, dict) else row
                out.append(User.model_validate_json(raw))
            return out

    async def search_by_query(self, query: str, limit: int = 20) -> list[User]:
        """Поиск пользователей по email или имени (ILIKE по JSONB полям)."""
        pattern = f"%{query}%"
        async with self._storage._get_session() as session:
            result = await session.execute(
                select(UsersModel.value)
                .where(
                    UsersModel.key.like("user:%"),
                    (
                        UsersModel.value["name"].astext.ilike(pattern)
                        | UsersModel.value["emails"].astext.ilike(pattern)
                    ),
                )
                .limit(limit)
            )
            users: list[User] = []
            for row in result.scalars():
                raw = json.dumps(row) if isinstance(row, dict) else row
                users.append(User.model_validate_json(raw))
            return users
