"""
CRMContainer - DI контейнер для CRM сервиса.

Наследуется от BaseContainer для получения user_repository, company_repository и других базовых сервисов.
Добавляет CRM-специфичные репозитории и сервисы.
"""

import logging
from typing import Optional

from core.container import BaseContainer, lazy

logger = logging.getLogger(__name__)


class CRMContainer(BaseContainer):
    """
    Контейнер для CRM сервиса.
    
    Наследуется от BaseContainer для получения:
    - user_repository, company_repository (из shared БД)
    - auth_service, variables_service
    
    Добавляет CRM-специфичные:
    - CRMDatabase для реляционных данных (relationships, notes, tasks)
    - ChromaDB для сущностей с embeddings
    
    Пример:
        container = get_crm_container()
        notes = await container.note_repository.get_by_date(company_id, date.today())
    """
    
    def __init__(self, db_url: str, shared_db_url: Optional[str] = None):
        super().__init__(db_url=db_url, shared_db_url=shared_db_url)
        self._crm_db_url = db_url
    
    # === CRM Database ===
    
    @lazy
    def crm_db(self):
        from apps.crm.db.base import CRMDatabase
        return CRMDatabase(self._crm_db_url)
    
    # === Репозитории (crm_db - реляционные) ===
    
    @lazy
    def entity_type_repository(self):
        from apps.crm.db.repositories.entity_type_repository import EntityTypeRepository
        return EntityTypeRepository(db=self.crm_db)
    
    @lazy
    def relationship_repository(self):
        from apps.crm.db.repositories.relationship_repository import RelationshipRepository
        return RelationshipRepository(db=self.crm_db)
    
    @lazy
    def note_repository(self):
        from apps.crm.db.repositories.note_repository import NoteRepository
        return NoteRepository(db=self.crm_db)
    
    @lazy
    def task_repository(self):
        from apps.crm.db.repositories.task_repository import TaskRepository
        return TaskRepository(db=self.crm_db)
    
    @lazy
    def company_mapping_repository(self):
        from apps.crm.db.repositories.company_mapping_repository import CompanyMappingRepository
        return CompanyMappingRepository(db=self.crm_db)
    
    @lazy
    def access_request_repository(self):
        from apps.crm.db.repositories.access_request_repository import AccessRequestRepository
        return AccessRequestRepository(db=self.crm_db)
    
    @lazy
    def profile_repository(self):
        from apps.crm.db.repositories.profile_repository import ProfileRepository
        return ProfileRepository(db=self.crm_db)
    
    # === Сервисы ===
    
    @lazy
    def rag_repository(self):
        """RAGRepository для работы с ChromaDB (сущности с embeddings)"""
        from core.rag import RAGRepository
        return RAGRepository()
    
    @lazy
    def entity_service(self):
        from apps.crm.services.entity_service import EntityService
        return EntityService(
            rag_repository=self.rag_repository,
            entity_type_repository=self.entity_type_repository,
            relationship_repository=self.relationship_repository,
        )
    
    @lazy
    def entity_type_service(self):
        from apps.crm.services.entity_type_service import EntityTypeService
        return EntityTypeService(
            entity_type_repository=self.entity_type_repository
        )
    
    @lazy
    def relationship_service(self):
        from apps.crm.services.relationship_service import RelationshipService
        return RelationshipService(
            relationship_repository=self.relationship_repository,
            entity_service=self.entity_service,
        )
    
    @lazy
    def note_service(self):
        from apps.crm.services.note_service import NoteService
        return NoteService(
            note_repository=self.note_repository,
            entity_service=self.entity_service,
            agents_client=self.agents_client,
        )
    
    @lazy
    def task_service(self):
        from apps.crm.services.task_service import TaskService
        return TaskService(
            task_repository=self.task_repository,
            entity_service=self.entity_service,
        )
    
    @lazy
    def agents_client(self):
        from apps.crm.services.agents_client import AgentsClient
        from apps.crm.config import get_crm_settings
        settings = get_crm_settings()
        return AgentsClient(agents_base_url=settings.agents_service_url)
    
    @lazy
    def graph_service(self):
        from apps.crm.services.graph_service import GraphService
        return GraphService(
            entity_service=self.entity_service,
            relationship_service=self.relationship_service,
        )
    
    @lazy
    def access_request_service(self):
        from apps.crm.services.access_request_service import AccessRequestService
        return AccessRequestService(
            access_request_repository=self.access_request_repository,
            note_repository=self.note_repository,
        )
    
    @lazy
    def profile_service(self):
        from apps.crm.services.profile_service import ProfileService
        return ProfileService(
            profile_repository=self.profile_repository,
            note_repository=self.note_repository,
            task_repository=self.task_repository,
        )
    
    async def init_db(self):
        """Инициализация БД - создание таблиц"""
        await self.crm_db.create_tables()
        logger.info("CRM БД инициализирована")


# === Глобальный контейнер ===

_crm_container: Optional[CRMContainer] = None


def get_crm_container() -> CRMContainer:
    """Получает контейнер (создает при первом вызове)"""
    global _crm_container
    if _crm_container is None:
        from core.config import get_settings
        settings = get_settings()
        
        crm_db_url = settings.database.crm_url or settings.database.url
        
        _crm_container = CRMContainer(
            db_url=crm_db_url,
            shared_db_url=settings.database.shared_url
        )
        logger.info(f"CRMContainer инициализирован с БД: {crm_db_url[:50]}...")
    return _crm_container


def set_crm_container(container: CRMContainer):
    """Устанавливает контейнер (для тестов)"""
    global _crm_container
    _crm_container = container


def reset_crm_container():
    """Сбрасывает контейнер (для тестов)"""
    global _crm_container
    _crm_container = None


get_container = get_crm_container
