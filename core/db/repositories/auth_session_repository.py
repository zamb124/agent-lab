"""
Репозиторий для работы с AuthSession.
Использует shared БД, is_global=True (не изолирован по компаниям).
"""

import logging

from core.db.base_repository import BaseRepository
from core.db.storage import Storage
from core.models.identity_models import AuthSession

logger = logging.getLogger(__name__)


class AuthSessionRepository(BaseRepository[AuthSession]):
    """
    Репозиторий для работы с сессиями аутентификации.
    is_global=True - сессии аутентификации не изолированы по компаниям.
    """
    
    is_global = True

    def __init__(self, storage: Storage):
        super().__init__(storage=storage, model_class=AuthSession)

    def _get_key(self, session_id: str) -> str:
        return f"auth_session:{session_id}"

    def _get_prefix(self) -> str:
        return "auth_session:"

    def _get_table_name(self) -> str:
        return "users"

    def _extract_entity_id(self, entity: AuthSession) -> str:
        return entity.session_id
