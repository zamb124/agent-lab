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
    - CRMDatabase для реляционных данных (relationships, entity types, relationships)
    - семантика сущностей через ``rag_repository`` (наследуется от ``BaseContainer``)
    
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
    def relationship_type_repository(self):
        from apps.crm.db.repositories.relationship_type_repository import RelationshipTypeRepository
        return RelationshipTypeRepository(db=self.crm_db)
    
    @lazy
    def relationship_repository(self):
        from apps.crm.db.repositories.relationship_repository import RelationshipRepository
        return RelationshipRepository(db=self.crm_db)

    @lazy
    def namespace_template_repository(self):
        from apps.crm.db.repositories.namespace_template_repository import NamespaceTemplateRepository
        return NamespaceTemplateRepository(db=self.crm_db)
    
    @lazy
    def entity_repository(self):
        from apps.crm.db.repositories.entity_repository import EntityRepository

        return EntityRepository(db=self.crm_db, rag_repository=self.rag_repository)
    
    @lazy
    def company_mapping_repository(self):
        from apps.crm.db.repositories.company_mapping_repository import CompanyMappingRepository
        return CompanyMappingRepository(db=self.crm_db)
    
    @lazy
    def access_request_repository(self):
        from apps.crm.db.repositories.access_request_repository import AccessRequestRepository
        return AccessRequestRepository(db=self.crm_db)
    
    @lazy
    def access_grant_repository(self):
        from apps.crm.db.repositories.access_grant_repository import AccessGrantRepository
        return AccessGrantRepository(db=self.crm_db)
    
    # === Сервисы ===
    
    @lazy
    def attachment_service(self):
        from apps.crm.services.attachment_service import AttachmentService
        return AttachmentService(entity_repository=self.entity_repository)

    @lazy
    def daily_summary_cache_service(self):
        from core.config import get_settings
        from apps.crm.services.daily_summary_cache_service import DailySummaryCacheService

        settings = get_settings()
        return DailySummaryCacheService(redis_url=settings.database.redis_url)

    @lazy
    def daily_summary_artifact_service(self):
        from apps.crm.services.daily_summary_artifact_service import DailySummaryArtifactService

        return DailySummaryArtifactService()
    
    @lazy
    def company_init_service(self):
        from apps.crm.services.company_init_service import CompanyInitService
        return CompanyInitService(
            entity_type_repo=self.entity_type_repository,
            relationship_type_repo=self.relationship_type_repository,
            namespace_template_repo=self.namespace_template_repository,
            entity_repo=self.entity_repository,
            company_repo=self.company_repository,
            relationship_repo=self.relationship_repository,
        )

    @lazy
    def namespace_template_service(self):
        from apps.crm.services.namespace_template_service import NamespaceTemplateService
        return NamespaceTemplateService(
            template_repo=self.namespace_template_repository,
            entity_type_repo=self.entity_type_repository,
            namespace_repo=self.namespace_repository,
            entity_repo=self.entity_repository,
            company_init_service=self.company_init_service,
        )

    @lazy
    def user_person_service(self):
        from apps.crm.services.user_person_service import UserPersonService
        return UserPersonService(
            entity_repo=self.entity_repository,
            entity_type_repo=self.entity_type_repository,
            user_repository=self.user_repository,
            relationship_repo=self.relationship_repository,
        )
    
    @lazy
    def entity_service(self):
        from apps.crm.services.entity_service import EntityService
        from core.clients.a2a_client import A2AClient
        return EntityService(
            entity_repo=self.entity_repository,
            entity_type_repo=self.entity_type_repository,
            relationship_type_repo=self.relationship_type_repository,
            relationship_repo=self.relationship_repository,
            namespace_repo=self.namespace_repository,
            attachment_service=self.attachment_service,
            a2a_client=A2AClient(timeout=300.0),
            daily_summary_cache_service=self.daily_summary_cache_service,
            daily_summary_artifact_service=self.daily_summary_artifact_service,
            user_person_service=self.user_person_service,
            access_grant_repo=self.access_grant_repository,
            access_request_repo=self.access_request_repository,
            company_mapping_repo=self.company_mapping_repository,
            company_repo=self.company_repository,
            access_control=self.access_control_service,
            task_repository=self.task_repository,
        )
    
    @lazy
    def access_control_service(self):
        from apps.crm.services.access_control_service import AccessControlService
        return AccessControlService(
            grant_repo=self.access_grant_repository,
            entity_type_repo=self.entity_type_repository
        )
    
    @lazy
    def access_grant_service(self):
        from apps.crm.services.access_grant_service import AccessGrantService
        return AccessGrantService(
            grant_repo=self.access_grant_repository,
            entity_repo=self.entity_repository
        )
    
    @lazy
    def access_request_service(self):
        from apps.crm.services.access_request_service import AccessRequestService
        return AccessRequestService(
            access_request_repo=self.access_request_repository,
            entity_repo=self.entity_repository,
            relationship_repo=self.relationship_repository
        )
    
    @lazy
    def graph_service(self):
        from apps.crm.services.graph_service import GraphService
        return GraphService(
            relationship_repo=self.relationship_repository,
            relationship_type_repo=self.relationship_type_repository,
            entity_repo=self.entity_repository,
            access_control=self.access_control_service
        )

    @lazy
    def note_processing_service(self):
        from apps.crm.services.note_processing_service import NoteProcessingService
        return NoteProcessingService(entity_service=self.entity_service)

    @lazy
    def task_repository(self):
        from apps.crm.db.repositories.task_repository import TaskRepository

        return TaskRepository(db=self.crm_db)

    @lazy
    def task_service(self):
        from apps.crm.services.task_service import TaskService

        return TaskService(
            task_repo=self.task_repository,
            entity_service=self.entity_service,
            relationship_repo=self.relationship_repository,
        )

    @lazy
    def lara_workspace_service(self):
        from apps.crm.services.lara_workspace_service import LaraWorkspaceService

        return LaraWorkspaceService(
            task_repo=self.task_repository,
            entity_repo=self.entity_repository,
        )


# === Глобальный контейнер ===

_crm_container: Optional[CRMContainer] = None


def get_crm_container() -> CRMContainer:
    """Получает контейнер (создает при первом вызове)"""
    global _crm_container
    if _crm_container is None:
        from apps.crm.config import get_crm_settings

        settings = get_crm_settings()
        
        if not settings.database.crm_url:
            raise ValueError("database.crm_url не задан")
        if not settings.database.shared_url:
            raise ValueError("database.shared_url не задан")

        _crm_container = CRMContainer(
            db_url=settings.database.crm_url,
            shared_db_url=settings.database.shared_url,
        )
        logger.info(f"CRMContainer инициализирован с БД: {settings.database.crm_url[:50]}...")
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
