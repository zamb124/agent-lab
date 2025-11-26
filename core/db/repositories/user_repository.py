"""
Репозиторий для работы с User.
Использует shared БД, is_global=True (не изолирован по компаниям).
"""

import logging
from typing import Optional

from core.db.base_repository import BaseRepository
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
