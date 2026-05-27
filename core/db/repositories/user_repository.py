"""
Репозиторий для работы с User.
Использует shared БД, is_global=True (не изолирован по компаниям).
"""

from typing import ClassVar, override

from sqlalchemy import select, text

from core.db.base_repository import BaseRepository
from core.db.models import Users as UsersModel
from core.db.storage import Storage
from core.logging import get_logger
from core.models.identity_models import User

logger = get_logger(__name__)


class UserRepository(BaseRepository[User]):
    """
    Репозиторий для работы с пользователями.
    is_global=True - пользователи не изолированы по компаниям.
    """

    is_global: ClassVar[bool] = True

    def __init__(self, storage: Storage):
        super().__init__(storage=storage, model_class=User)

    @override
    def _get_key(self, user_id: str) -> str:
        return f"user:{user_id}"

    @override
    def _get_prefix(self) -> str:
        return "user:"

    @override
    def _get_table_name(self) -> str:
        return "users"

    @override
    def _extract_entity_id(self, entity: User) -> str:
        return entity.user_id

    async def find_by_email(self, email: str) -> User | None:
        """Поиск пользователя по email (JSONB containment по полю emails)."""
        async with self._storage.get_session() as session:
            result = await session.execute(
                select(UsersModel.value)
                .where(
                    UsersModel.key.like("user:%"),
                    text("(users.value->'emails') @> jsonb_build_array(CAST(:email AS text))"),
                )
                .limit(1),
                {"email": email},
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return User.model_validate(row)

    async def find_all_by_email_ci(self, email: str) -> list[User]:
        """Все пользователи, у которых в emails есть адрес без учёта регистра."""
        norm = email.strip().lower()
        if not norm:
            raise ValueError("email для поиска не может быть пустым")
        async with self._storage.get_session() as session:
            result = await session.execute(
                select(UsersModel.value)
                .where(
                    UsersModel.key.like("user:%"),
                    text(
                        """
                        EXISTS (
                            SELECT 1
                            FROM jsonb_array_elements_text(users.value->'emails') AS e(elt)
                            WHERE lower(e.elt) = :norm
                        )
                        """
                    ),
                )
                .order_by(UsersModel.key),
                {"norm": norm},
            )
            out: list[User] = []
            for row in result.scalars():
                out.append(User.model_validate(row))
            return out

    async def search_by_query(self, query: str, limit: int = 20) -> list[User]:
        """Поиск пользователей по email или имени (ILIKE по JSONB полям)."""
        pattern = f"%{query}%"
        async with self._storage.get_session() as session:
            result = await session.execute(
                select(UsersModel.value)
                .where(
                    UsersModel.key.like("user:%"),
                    text(
                        """
                        (
                            users.value->>'name' ILIKE :pattern
                            OR EXISTS (
                                SELECT 1
                                FROM jsonb_array_elements_text(users.value->'emails') AS e(elt)
                                WHERE e.elt ILIKE :pattern
                            )
                        )
                        """
                    ),
                )
                .limit(limit),
                {"pattern": pattern},
            )
            users: list[User] = []
            for row in result.scalars():
                users.append(User.model_validate(row))
            return users
