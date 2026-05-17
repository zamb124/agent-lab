"""
CRMContainer - DI контейнер для CRM сервиса.

Наследуется от BaseContainer для получения user_repository, company_repository и других базовых сервисов.
Добавляет CRM-специфичные репозитории и сервисы.
"""

from __future__ import annotations

from apps.crm.config import get_crm_settings
from apps.crm.db.base import CRMDatabase
from apps.crm.db.repositories.access_grant_repository import AccessGrantRepository
from apps.crm.db.repositories.access_request_repository import AccessRequestRepository
from apps.crm.db.repositories.company_mapping_repository import CompanyMappingRepository
from apps.crm.db.repositories.entity_repository import EntityRepository
from apps.crm.db.repositories.entity_type_repository import EntityTypeRepository
from apps.crm.db.repositories.namespace_template_repository import NamespaceTemplateRepository
from apps.crm.db.repositories.relationship_repository import RelationshipRepository
from apps.crm.db.repositories.relationship_type_repository import RelationshipTypeRepository
from apps.crm.db.repositories.suggest_repository import SuggestRepository
from apps.crm.db.repositories.task_repository import TaskRepository
from apps.crm.integrations.amocrm.connector import AmoCRMConnector
from apps.crm.integrations.registry import IntegrationRegistry
from apps.crm.services.access_control_service import AccessControlService
from apps.crm.services.access_grant_service import AccessGrantService
from apps.crm.services.access_request_service import AccessRequestService
from apps.crm.services.attachment_service import AttachmentService
from apps.crm.services.company_init_service import CompanyInitService
from apps.crm.services.daily_summary_artifact_service import DailySummaryArtifactService
from apps.crm.services.daily_summary_cache_service import DailySummaryCacheService
from apps.crm.services.entity_service import EntityService
from apps.crm.services.graph_service import GraphService
from apps.crm.services.integration_auto_sync_service import IntegrationAutoSyncService
from apps.crm.services.lara_workspace_service import LaraWorkspaceService
from apps.crm.services.namespace_template_service import NamespaceTemplateService
from apps.crm.services.note_markdown_format_schedule import schedule_note_markdown_format
from apps.crm.services.note_processing_service import NoteProcessingService
from apps.crm.services.suggest_service import SuggestService
from apps.crm.services.task_service import TaskService
from apps.crm.services.user_person_service import UserPersonService
from core.clients.a2a_client import A2AClient
from core.config import get_settings
from core.container import BaseContainer, lazy
from core.logging import get_logger

logger = get_logger(__name__)


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

    def __init__(self, db_url: str, shared_db_url: str | None = None):
        super().__init__(db_url=db_url, shared_db_url=shared_db_url)
        self._crm_db_url: str = db_url

    # === CRM Database ===

    @lazy
    def crm_db(self) -> CRMDatabase:
        return CRMDatabase(self._crm_db_url)

    # === Репозитории (crm_db - реляционные) ===

    @lazy
    def entity_type_repository(self) -> EntityTypeRepository:
        return EntityTypeRepository(db=self.crm_db)

    @lazy
    def relationship_type_repository(self) -> RelationshipTypeRepository:
        return RelationshipTypeRepository(db=self.crm_db)

    @lazy
    def relationship_repository(self) -> RelationshipRepository:
        return RelationshipRepository(db=self.crm_db)

    @lazy
    def namespace_template_repository(self) -> NamespaceTemplateRepository:
        return NamespaceTemplateRepository(db=self.crm_db)

    @lazy
    def entity_repository(self) -> EntityRepository:
        return EntityRepository(db=self.crm_db, rag_repository=self.rag_repository)

    @lazy
    def company_mapping_repository(self) -> CompanyMappingRepository:
        return CompanyMappingRepository(db=self.crm_db)

    @lazy
    def access_request_repository(self) -> AccessRequestRepository:
        return AccessRequestRepository(db=self.crm_db)

    @lazy
    def access_grant_repository(self) -> AccessGrantRepository:
        return AccessGrantRepository(db=self.crm_db)

    @lazy
    def suggest_repository(self) -> SuggestRepository:
        return SuggestRepository(db=self.crm_db)

    # === Сервисы ===

    @lazy
    def attachment_service(self) -> AttachmentService:
        return AttachmentService(
            entity_repository=self.entity_repository,
            access_grant_repository=self.access_grant_repository,
            company_repository=self.company_repository,
            file_repository=self.file_repository,
            note_markdown_format_scheduler=self.schedule_note_markdown_format,
        )

    @lazy
    def daily_summary_cache_service(self) -> DailySummaryCacheService:
        settings = get_settings()
        return DailySummaryCacheService(redis_url=settings.database.redis_url)

    @lazy
    def daily_summary_artifact_service(self) -> DailySummaryArtifactService:
        return DailySummaryArtifactService()

    @lazy
    def company_init_service(self) -> CompanyInitService:
        return CompanyInitService(
            entity_type_repo=self.entity_type_repository,
            relationship_type_repo=self.relationship_type_repository,
            namespace_template_repo=self.namespace_template_repository,
            entity_repo=self.entity_repository,
            company_repo=self.company_repository,
            relationship_repo=self.relationship_repository,
            company_mapping_repo=self.company_mapping_repository,
        )

    @lazy
    def namespace_template_service(self) -> NamespaceTemplateService:
        return NamespaceTemplateService(
            template_repo=self.namespace_template_repository,
            entity_type_repo=self.entity_type_repository,
            namespace_repo=self.namespace_repository,
            entity_repo=self.entity_repository,
            company_init_service=self.company_init_service,
        )

    @lazy
    def user_person_service(self) -> UserPersonService:
        return UserPersonService(
            entity_repo=self.entity_repository,
            entity_type_repo=self.entity_type_repository,
            user_repository=self.user_repository,
            relationship_repo=self.relationship_repository,
        )

    @lazy
    def suggest_service(self) -> SuggestService:
        return SuggestService(
            repository=self.suggest_repository,
            entity_service=self.entity_service,
            note_processing_service=self.note_processing_service,
            entity_repository=self.entity_repository,
            entity_type_repository=self.entity_type_repository,
        )

    @lazy
    def entity_service(self) -> EntityService:
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
            note_markdown_format_scheduler=self.schedule_note_markdown_format,
        )

    @lazy
    def access_control_service(self) -> AccessControlService:
        return AccessControlService(
            grant_repo=self.access_grant_repository, entity_type_repo=self.entity_type_repository
        )

    @lazy
    def access_grant_service(self) -> AccessGrantService:
        return AccessGrantService(
            grant_repo=self.access_grant_repository, entity_repo=self.entity_repository
        )

    @lazy
    def access_request_service(self) -> AccessRequestService:
        return AccessRequestService(
            access_request_repo=self.access_request_repository,
            entity_repo=self.entity_repository,
            relationship_repo=self.relationship_repository,
        )

    @lazy
    def graph_service(self) -> GraphService:
        return GraphService(
            relationship_repo=self.relationship_repository,
            relationship_type_repo=self.relationship_type_repository,
            entity_repo=self.entity_repository,
            access_control=self.access_control_service,
        )

    @lazy
    def note_processing_service(self) -> NoteProcessingService:
        return NoteProcessingService(entity_service=self.entity_service)

    @lazy
    def task_repository(self) -> TaskRepository:
        return TaskRepository(db=self.crm_db)

    @lazy
    def task_service(self) -> TaskService:
        return TaskService(
            task_repo=self.task_repository,
            entity_service=self.entity_service,
            relationship_repo=self.relationship_repository,
            file_repository=self.file_repository,
            company_repository=self.company_repository,
        )

    async def schedule_note_markdown_format(
        self,
        *,
        note_id: str,
        company_id: str,
        namespace: str,
        expected_updated_at_iso: str,
    ) -> bool:
        return await schedule_note_markdown_format(
            task_service=self.task_service,
            entity_repository=self.entity_repository,
            company_repository=self.company_repository,
            access_grant_repository=self.access_grant_repository,
            note_id=note_id,
            company_id=company_id,
            namespace=namespace,
            expected_updated_at_iso=expected_updated_at_iso,
        )

    @lazy
    def lara_workspace_service(self) -> LaraWorkspaceService:
        return LaraWorkspaceService(
            task_repo=self.task_repository,
            entity_repo=self.entity_repository,
        )

    @lazy
    def integration_registry(self) -> IntegrationRegistry:
        return IntegrationRegistry(
            [
                AmoCRMConnector(
                    oauth_service=self.oauth_service,
                    entity_repository=self.entity_repository,
                    entity_type_repository=self.entity_type_repository,
                    relationship_repository=self.relationship_repository,
                    entity_service=self.entity_service,
                    namespace_repository=self.namespace_repository,
                    task_service=self.task_service,
                    integration_external_author=self.integration_external_author_service,
                    namespace_template_service=self.namespace_template_service,
                )
            ]
        )

    @lazy
    def integration_auto_sync_service(self) -> IntegrationAutoSyncService:
        return IntegrationAutoSyncService(
            namespace_repository=self.namespace_repository,
            integration_registry=self.integration_registry,
            oauth_service=self.oauth_service,
            scheduler_client=self.scheduler_client,
        )


# === Глобальный контейнер ===

_crm_container: CRMContainer | None = None


def get_crm_container() -> CRMContainer:
    """Получает контейнер (создает при первом вызове)"""
    global _crm_container
    if _crm_container is None:
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
