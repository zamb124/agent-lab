"""
Сервис для cross-company копирования через AccessRequests.
"""

import uuid
from datetime import UTC, datetime

from apps.crm.db.models import AccessRequest, CRMEntity, Relationship
from apps.crm.db.repositories.access_request_repository import AccessRequestRepository
from apps.crm.db.repositories.entity_repository import EntityRepository
from apps.crm.db.repositories.relationship_repository import RelationshipRepository
from apps.crm.services.crm_entity_access_service import CrmEntityAccessService
from core.authz.models import AuthzObject
from core.authz.service import AuthzService
from core.authz.types import AuthzRelation, AuthzSubjectKind
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError
from core.logging import get_logger
from core.types import JsonObject
from core.websocket.publisher import Notification, NotificationType, notify_user

logger = get_logger(__name__)


class AccessRequestService:
    """Управление запросами доступа между компаниями"""

    def __init__(
        self,
        access_request_repo: AccessRequestRepository,
        entity_repo: EntityRepository,
        relationship_repo: RelationshipRepository,
        authz: AuthzService,
        entity_access: CrmEntityAccessService,
    ) -> None:
        self._access_request_repo: AccessRequestRepository = access_request_repo
        self._entity_repo: EntityRepository = entity_repo
        self._relationship_repo: RelationshipRepository = relationship_repo
        self._authz: AuthzService = authz
        self._entity_access: CrmEntityAccessService = entity_access

    async def _require_can_share_entity(self, entity_id: str, user_id: str) -> None:
        await self._authz.require_can_share(
            AuthzObject.crm_entity(entity_id), user_id=user_id
        )

    async def _notify_can_share_holders(
        self,
        *,
        entity: CRMEntity,
        access_request: AccessRequest,
        requester_user_id: str,
        requester_company_id: str,
    ) -> None:
        holders = await self._authz.list_users(
            AuthzObject.crm_entity(entity.entity_id),
            AuthzRelation.CAN_SHARE,
        )
        notified: set[str] = set()
        for subject in holders:
            if subject.kind is not AuthzSubjectKind.USER:
                continue
            if subject.value in notified:
                continue
            notified.add(subject.value)
            await notify_user(
                user_id=subject.value,
                notification=Notification(
                    type=NotificationType.ACCESS_REQUEST,
                    title="Новый запрос доступа",
                    message=(
                        f"Запрос доступа к '{entity.name}' "
                        f"от пользователя {requester_user_id}"
                    ),
                    service="crm",
                    priority="high",
                    action_url=(
                        f"/crm/access-requests/{access_request.access_request_id}"
                    ),
                    data={
                        "access_request_id": access_request.access_request_id,
                        "entity_id": entity.entity_id,
                        "entity_name": entity.name,
                        "requester_id": requester_user_id,
                        "requester_company_id": requester_company_id,
                    },
                ),
            )

    async def create_access_request(
        self,
        entity_id: str,
        requester_user_id: str,
        requester_company_id: str,
        message: str | None = None,
        include_dependencies: bool = False,
        max_depth: int = 1,
    ) -> AccessRequest:
        """Запрос доступа к entity (внутри компании или cross-company)"""

        # Получаем entity
        entity = await self._entity_repo.get(entity_id)
        if not entity:
            raise PlatformNotFoundError("Entity not found")

        # Создаем запрос
        access_request = AccessRequest(
            access_request_id=str(uuid.uuid4()),
            company_id=entity.company_id,  # Компания владельца
            requester_id=requester_user_id,
            requester_company_id=requester_company_id,
            owner_id=entity.user_id,
            resource_type="entity",
            resource_id=entity_id,
            message=message,
            status="pending",
            include_dependencies=include_dependencies,
            max_depth=max_depth,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        access_request = await self._access_request_repo.create(access_request)
        logger.info(
            f"Access request created: {access_request.access_request_id} for entity {entity_id}"
        )

        await self._notify_can_share_holders(
            entity=entity,
            access_request=access_request,
            requester_user_id=requester_user_id,
            requester_company_id=requester_company_id,
        )

        return access_request

    async def approve_access_request(
        self,
        access_request_id: str,
        owner_user_id: str,
    ) -> AccessRequest:
        """Одобрить = скопировать entity в компанию запросившего"""

        access_request = await self._access_request_repo.get(access_request_id)
        if not access_request:
            raise PlatformNotFoundError("Request not found")

        await self._require_can_share_entity(access_request.resource_id, owner_user_id)

        if access_request.status != "pending":
            raise PlatformConflictError(f"Request already {access_request.status}")

        original = await self._entity_repo.get(access_request.resource_id)
        if not original:
            raise PlatformNotFoundError("Original entity not found")

        # Копируем entity
        if access_request.include_dependencies:
            # Полное копирование с relationships
            copy = await self._copy_with_dependencies(
                original=original,
                target_company_id=access_request.requester_company_id,
                target_user_id=access_request.requester_id,
                max_depth=access_request.max_depth,
            )
        else:
            # Поверхностное копирование с metadata
            copy = await self._copy_shallow(
                original=original,
                target_company_id=access_request.requester_company_id,
                target_user_id=access_request.requester_id,
            )

        # Обновляем запрос
        access_request.status = "approved"
        access_request.created_entity_id = copy.entity_id
        access_request.updated_at = datetime.now(UTC)
        access_request = await self._access_request_repo.update(access_request)

        logger.info(
            f"Access request {access_request_id} approved, created entity {copy.entity_id}"
        )

        # Уведомление запросившему об одобрении
        await notify_user(
            user_id=access_request.requester_id,
            notification=Notification(
                type=NotificationType.ACCESS_REQUEST,
                title="Запрос доступа одобрен",
                message=f"Ваш запрос доступа к '{original.name}' был одобрен",
                service="crm",
                priority="normal",
                action_url=f"/crm/entities/{copy.entity_id}",
                data={
                    "access_request_id": access_request.access_request_id,
                    "entity_id": copy.entity_id,
                    "original_entity_id": original.entity_id,
                    "status": "approved",
                },
            ),
        )

        return access_request

    async def _copy_shallow(
        self,
        original: CRMEntity,
        target_company_id: str,
        target_user_id: str,
    ) -> CRMEntity:
        """Поверхностное копирование — entity и metadata relationships"""

        # Получаем relationships оригинала
        relationships = await self._relationship_repo.get_by_entity(original.entity_id)

        # Преобразуем в metadata (без ID, только имена)
        external_rels: list[JsonObject] = []
        for rel in relationships:
            target_entity = await self._entity_repo.get(rel.target_entity_id)
            if target_entity:
                external_rels.append(
                    {
                        "type": rel.relationship_type,
                        "direction": "outgoing",
                        "target_name": target_entity.name,
                        "target_type": target_entity.entity_type,
                        # НЕТ target_entity_id - это другая компания!
                    }
                )

        copy_attributes = dict(original.attributes) if original.attributes else {}
        if external_rels:
            copy_attributes["external_relationships"] = external_rels

        copy = CRMEntity(
            entity_id=str(uuid.uuid4()),
            company_id=target_company_id,
            namespace="default",
            entity_type=original.entity_type,
            entity_subtype=original.entity_subtype,
            name=original.name,
            description=original.description,
            status=original.status,
            tags=list(original.tags) if original.tags else [],
            attributes=copy_attributes,
            note_date=original.note_date,
            attachment_ids=[],
            source_entity_id=original.entity_id,
            source_company_id=original.company_id,
            user_id=target_user_id,
            relevance=original.relevance,
        )

        copy = await self._entity_repo.create(copy)
        try:
            await self._entity_access.sync_entity_created(copy)
        except Exception:
            _ = await self._entity_repo.delete(copy.entity_id)
            raise
        logger.info(f"Shallow copy created: {copy.entity_id} from {original.entity_id}")

        return copy

    async def _copy_with_dependencies(
        self,
        original: CRMEntity,
        target_company_id: str,
        target_user_id: str,
        max_depth: int,
        _current_depth: int = 0,
        _copied_map: dict[str, str] | None = None,
    ) -> CRMEntity:
        """Полное копирование — рекурсивное копирование с relationships"""

        if _copied_map is None:
            _copied_map = {}  # original_id -> copy_id

        # Ограничение глубины
        if _current_depth >= max_depth:
            return await self._copy_shallow(original, target_company_id, target_user_id)

        copy = CRMEntity(
            entity_id=str(uuid.uuid4()),
            company_id=target_company_id,
            namespace="default",
            entity_type=original.entity_type,
            entity_subtype=original.entity_subtype,
            name=original.name,
            description=original.description,
            status=original.status,
            tags=list(original.tags) if original.tags else [],
            attributes=dict(original.attributes) if original.attributes else {},
            note_date=original.note_date,
            attachment_ids=[],
            source_entity_id=original.entity_id,
            source_company_id=original.company_id,
            user_id=target_user_id,
            relevance=original.relevance,
        )

        copy = await self._entity_repo.create(copy)
        try:
            await self._entity_access.sync_entity_created(copy)
        except Exception:
            _ = await self._entity_repo.delete(copy.entity_id)
            raise
        _copied_map[original.entity_id] = copy.entity_id

        # Получаем relationships
        relationships = await self._relationship_repo.get_by_entity(original.entity_id)

        # Рекурсивно копируем связанные entities
        for rel in relationships:
            target_entity = await self._entity_repo.get(rel.target_entity_id)
            if not target_entity:
                continue

            # Если уже скопирована - используем существующую
            if rel.target_entity_id in _copied_map:
                target_copy_id = _copied_map[rel.target_entity_id]
            else:
                # Рекурсия
                target_copy = await self._copy_with_dependencies(
                    original=target_entity,
                    target_company_id=target_company_id,
                    target_user_id=target_user_id,
                    max_depth=max_depth,
                    _current_depth=_current_depth + 1,
                    _copied_map=_copied_map,
                )
                target_copy_id = target_copy.entity_id

            # Создаем relationship в новой компании

            new_rel = Relationship(
                relationship_id=str(uuid.uuid4()),
                company_id=copy.company_id,
                namespace=rel.namespace,
                source_entity_id=copy.entity_id,
                target_entity_id=target_copy_id,
                relationship_type=rel.relationship_type,
                weight=rel.weight,
                confidence=rel.confidence,
                attributes=rel.attributes,
            )
            new_rel = await self._relationship_repo.create(new_rel)

        logger.info(
            f"Deep copy created: {copy.entity_id} from {original.entity_id} (depth={_current_depth})"
        )

        return copy

    async def reject_access_request(
        self,
        access_request_id: str,
        owner_user_id: str,
        reason: str | None = None,
    ) -> AccessRequest:
        """Отклонить запрос"""

        access_request = await self._access_request_repo.get(access_request_id)
        if not access_request:
            raise PlatformNotFoundError("Request not found")

        await self._require_can_share_entity(access_request.resource_id, owner_user_id)

        access_request.status = "rejected"
        access_request.updated_at = datetime.now(UTC)
        access_request = await self._access_request_repo.update(access_request)

        logger.info(f"Access request {access_request_id} rejected by {owner_user_id}")

        # Уведомление запросившему об отклонении
        entity = await self._entity_repo.get(access_request.resource_id)
        if entity is None:
            raise PlatformNotFoundError("Original entity not found")
        entity_name = entity.name

        await notify_user(
            user_id=access_request.requester_id,
            notification=Notification(
                type=NotificationType.ACCESS_REQUEST,
                title="Запрос доступа отклонен",
                message=f"Ваш запрос доступа к '{entity_name}' был отклонен",
                service="crm",
                priority="low",
                data={
                    "access_request_id": access_request.access_request_id,
                    "entity_id": access_request.resource_id,
                    "status": "rejected",
                    "reason": reason,
                },
            ),
        )

        return access_request

    async def get_access_request(self, access_request_id: str) -> AccessRequest | None:
        """Получить запрос по ID"""
        return await self._access_request_repo.get(access_request_id)

    async def list_access_requests(
        self,
        company_id: str,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AccessRequest]:
        if status:
            return await self._access_request_repo.list_by_company_and_status(
                company_id, status, limit=limit, offset=offset
            )
        return await self._access_request_repo.list_by_company(
            company_id, limit=limit, offset=offset
        )

    async def count_access_requests(
        self,
        company_id: str,
        status: str | None = None,
    ) -> int:
        return await self._access_request_repo.count_by_company(company_id, status=status)
