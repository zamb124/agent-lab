"""
Репозиторий для работы с AuthSession.
Использует shared БД, is_global=True (не изолирован по компаниям).
"""

from typing import ClassVar, override

from core.db.base_repository import BaseRepository
from core.db.storage import Storage
from core.logging import get_logger
from core.models.identity_models import AuthSession

logger = get_logger(__name__)


class AuthSessionRepository(BaseRepository[AuthSession]):
    """
    Репозиторий для работы с сессиями аутентификации.
    is_global=True - сессии аутентификации не изолированы по компаниям.
    """

    is_global: ClassVar[bool] = True

    def __init__(self, storage: Storage):
        super().__init__(storage=storage, model_class=AuthSession)

    @override
    def _get_key(self, session_id: str) -> str:
        return f"auth_session:{session_id}"

    @override
    def _get_prefix(self) -> str:
        return "auth_session:"

    @override
    def _get_table_name(self) -> str:
        return "users"

    @override
    def _extract_entity_id(self, entity: AuthSession) -> str:
        return entity.session_id
