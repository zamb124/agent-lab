"""
Сервис для cross-company копирования через AccessRequests.
"""

import uuid
from typing import Optional, Dict, List
from datetime import datetime, timezone

from apps.crm.models.entity import ChromaDBEntity
from apps.crm.db.models import AccessRequest, Relationship
from apps.crm.db.repositories.access_request_repository import AccessRequestRepository
from apps.crm.db.repositories.entity_repository import EntityChromaRepository
from apps.crm.db.repositories.relationship_repository import RelationshipRepository
from core.websocket.publisher import notify_user, Notification, NotificationType
from core.logging import get_logger

logger = get_logger(__name__)


class AccessRequestService:
    """Управление запросами доступа между компаниями"""
    
    def __init__(
        self,
        access_request_repo: AccessRequestRepository,
        entity_repo: EntityChromaRepository,
        relationship_repo: RelationshipRepository
    ):
        self._request_repo = access_request_repo
        self._entity_repo = entity_repo
        self._relationship_repo = relationship_repo
    
    async def create_request(
        self,
        entity_id: str,
        requester_user_id: str,
        requester_company_id: str,
        message: Optional[str] = None,
        include_dependencies: bool = False,
        max_depth: int = 1
    ) -> AccessRequest:
        """Запрос доступа к entity (внутри компании или cross-company)"""
        
        # Получаем entity
        entity = await self._entity_repo.get(entity_id)
        if not entity:
            raise ValueError("Entity not found")
        
        # Создаем запрос
        request = AccessRequest(
            request_id=str(uuid.uuid4()),
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
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        
        await self._request_repo.create(request)
        logger.info(f"Access request created: {request.request_id} for entity {entity_id}")
        
        # Отправить уведомление владельцу entity
        await notify_user(
            user_id=entity.user_id,
            notification=Notification(
                type=NotificationType.ACCESS_REQUEST,
                title="Новый запрос доступа",
                message=f"Запрос доступа к '{entity.name}' от пользователя {requester_user_id}",
                service="crm",
                priority="high",
                action_url=f"/crm/access-requests/{request.request_id}",
                data={
                    "request_id": request.request_id,
                    "entity_id": entity_id,
                    "entity_name": entity.name,
                    "requester_id": requester_user_id,
                    "requester_company_id": requester_company_id,
                },
            ),
        )
        
        return request
    
    async def approve_request(
        self,
        request_id: str,
        owner_user_id: str
    ) -> ChromaDBEntity:
        """Одобрить = скопировать entity в компанию запросившего"""
        
        request = await self._request_repo.get(request_id)
        if not request:
            raise ValueError("Request not found")
        
        # Проверка прав
        if request.owner_id != owner_user_id:
            raise PermissionError("Only owner can approve")
        
        if request.status != "pending":
            raise ValueError(f"Request already {request.status}")
        
        # Получаем оригинал
        original = await self._entity_repo.get(request.resource_id)
        if not original:
            raise ValueError("Original entity not found")
        
        # Копируем entity
        if request.include_dependencies:
            # Deep copy с relationships
            copy = await self._copy_with_dependencies(
                original=original,
                target_company_id=request.requester_company_id,
                target_user_id=request.requester_id,
                max_depth=request.max_depth
            )
        else:
            # Shallow copy с metadata
            copy = await self._copy_shallow(
                original=original,
                target_company_id=request.requester_company_id,
                target_user_id=request.requester_id
            )
        
        # Обновляем запрос
        request.status = "approved"
        request.created_entity_id = copy.entity_id
        request.updated_at = datetime.now(timezone.utc)
        await self._request_repo.update(request)
        
        logger.info(f"Access request {request_id} approved, created entity {copy.entity_id}")
        
        # Уведомление запросившему об одобрении
        await notify_user(
            user_id=request.requester_id,
            notification=Notification(
                type=NotificationType.ACCESS_REQUEST,
                title="Запрос доступа одобрен",
                message=f"Ваш запрос доступа к '{original.name}' был одобрен",
                service="crm",
                priority="normal",
                action_url=f"/crm/entities/{copy.entity_id}",
                data={
                    "request_id": request.request_id,
                    "entity_id": copy.entity_id,
                    "original_entity_id": original.entity_id,
                    "status": "approved",
                },
            ),
        )
        
        return copy
    
    async def _copy_shallow(
        self,
        original: ChromaDBEntity,
        target_company_id: str,
        target_user_id: str
    ) -> ChromaDBEntity:
        """Shallow copy - entity + metadata relationships"""
        
        # Получаем relationships оригинала
        relationships = await self._relationship_repo.get_by_entity(original.entity_id)
        
        # Преобразуем в metadata (без ID, только имена)
        external_rels = []
        for rel in relationships:
            target_entity = await self._entity_repo.get(rel.target_entity_id)
            if target_entity:
                external_rels.append({
                    "type": rel.relationship_type,
                    "direction": "outgoing",
                    "target_name": target_entity.name,
                    "target_type": target_entity.entity_type,
                    # НЕТ target_entity_id - это другая компания!
                })
        
        # Создаем копию
        copy_data = original.model_dump(
            exclude={
                "entity_id", 
                "company_id", 
                "namespace",
                "user_id",
                "source_entity_id",  # Устанавливаем явно
                "source_company_id",  # Устанавливаем явно
                "external_relationships",  # Устанавливаем явно
                "created_at",
                "updated_at"
            }
        )
        
        copy = ChromaDBEntity(
            entity_id=str(uuid.uuid4()),
            company_id=target_company_id,
            namespace="default",  # В default namespace целевой компании
            source_entity_id=original.entity_id,
            source_company_id=original.company_id,
            external_relationships=external_rels,  # Metadata
            user_id=target_user_id,  # Новый владелец
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            **copy_data
        )
        
        await self._entity_repo.create(copy)
        logger.info(f"Shallow copy created: {copy.entity_id} from {original.entity_id}")
        
        return copy
    
    async def _copy_with_dependencies(
        self,
        original: ChromaDBEntity,
        target_company_id: str,
        target_user_id: str,
        max_depth: int,
        _current_depth: int = 0,
        _copied_map: Optional[Dict[str, str]] = None
    ) -> ChromaDBEntity:
        """Deep copy - рекурсивное копирование с relationships"""
        
        if _copied_map is None:
            _copied_map = {}  # original_id -> copy_id
        
        # Ограничение глубины
        if _current_depth >= max_depth:
            return await self._copy_shallow(original, target_company_id, target_user_id)
        
        # Копируем основную entity
        copy_data = original.model_dump(
            exclude={
                "entity_id", "company_id", "namespace", "user_id",
                "source_entity_id", "source_company_id", "external_relationships",
                "created_at", "updated_at"
            }
        )
        
        copy = ChromaDBEntity(
            entity_id=str(uuid.uuid4()),
            company_id=target_company_id,
            namespace="default",
            source_entity_id=original.entity_id,
            source_company_id=original.company_id,
            user_id=target_user_id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            **copy_data
        )
        
        await self._entity_repo.create(copy)
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
                    _copied_map=_copied_map
                )
                target_copy_id = target_copy.entity_id
            
            # Создаем relationship в новой компании
            
            new_rel = Relationship(
                relationship_id=str(uuid.uuid4()),
                company_id=copy.company_id,
                source_entity_id=copy.entity_id,
                target_entity_id=target_copy_id,
                relationship_type=rel.relationship_type,
                weight=rel.weight,
                attributes=rel.attributes
            )
            await self._relationship_repo.create(new_rel)
        
        logger.info(f"Deep copy created: {copy.entity_id} from {original.entity_id} (depth={_current_depth})")
        
        return copy
    
    async def reject_request(
        self,
        request_id: str,
        owner_user_id: str,
        reason: Optional[str] = None
    ) -> bool:
        """Отклонить запрос"""
        
        request = await self._request_repo.get(request_id)
        if not request:
            raise ValueError("Request not found")
        
        if request.owner_id != owner_user_id:
            raise PermissionError("Only owner can reject")
        
        request.status = "rejected"
        request.updated_at = datetime.now(timezone.utc)
        await self._request_repo.update(request)
        
        logger.info(f"Access request {request_id} rejected by {owner_user_id}")
        
        # Уведомление запросившему об отклонении
        entity = await self._entity_repo.get(request.resource_id)
        entity_name = entity.name if entity else "неизвестная сущность"
        
        await notify_user(
            user_id=request.requester_id,
            notification=Notification(
                type=NotificationType.ACCESS_REQUEST,
                title="Запрос доступа отклонен",
                message=f"Ваш запрос доступа к '{entity_name}' был отклонен",
                service="crm",
                priority="low",
                data={
                    "request_id": request.request_id,
                    "entity_id": request.resource_id,
                    "status": "rejected",
                    "reason": reason,
                },
            ),
        )
        
        return True
    
    async def get(self, request_id: str) -> Optional[AccessRequest]:
        """Получить запрос по ID"""
        return await self._request_repo.get(request_id)
    
    async def get_request(self, request_id: str) -> Optional[AccessRequest]:
        """Алиас для get"""
        return await self.get(request_id)
    
    async def list_pending_for_owner(self, owner_id: str) -> List[AccessRequest]:
        """Список pending запросов для владельца"""
        return await self._request_repo.list_by_owner_and_status(owner_id, "pending")
    
    async def list_requests(
        self,
        company_id: str,
        status: Optional[str] = None
    ) -> List[AccessRequest]:
        """Список запросов для компании с фильтром по статусу"""
        if status:
            return await self._request_repo.list_by_company_and_status(company_id, status)
        return await self._request_repo.list_by_company(company_id)

