"""
Сервис управления грантами доступа.
"""

import uuid
from typing import List, Optional

from apps.crm.db.models import AccessGrant
from apps.crm.db.repositories.access_grant_repository import AccessGrantRepository
from apps.crm.db.repositories.entity_repository import EntityChromaRepository
from core.logging import get_logger

logger = get_logger(__name__)


class AccessGrantService:
    """Управление грантами доступа"""
    
    def __init__(
        self,
        grant_repo: AccessGrantRepository,
        entity_repo: EntityChromaRepository
    ):
        self._grant_repo = grant_repo
        self._entity_repo = entity_repo
    
    # === ENTITY GRANTS ===
    
    async def grant_entity_public(
        self,
        entity_id: str,
        created_by: str
    ) -> AccessGrant:
        """Сделать entity публичной"""
        
        entity = await self._entity_repo.get(entity_id)
        if not entity:
            raise ValueError("Entity not found")
        
        # Проверка прав: только владелец может делать public
        if not entity.user_id:
            raise ValueError("Entity has no owner (user_id not set)")
        
        if entity.user_id != created_by:
            raise PermissionError("Only owner can make public")
        
        grant = AccessGrant(
            grant_id=str(uuid.uuid4()),
            company_id=entity.company_id,
            created_by=created_by,
            resource_type="entity",
            resource_id=entity_id,
            grant_type="public",
            role="viewer"
        )
        
        await self._grant_repo.create(grant)
        logger.info(f"Entity {entity_id} made public by {created_by}")
        return grant
    
    async def grant_entity_to_user(
        self,
        entity_id: str,
        target_user_id: str,
        role: str,
        created_by: str
    ) -> AccessGrant:
        """Пошерить entity конкретному user"""
        
        entity = await self._entity_repo.get(entity_id)
        if not entity:
            raise ValueError("Entity not found")
        
        if not entity.user_id:
            raise ValueError("Entity has no owner (user_id not set)")
        
        if entity.user_id != created_by:
            raise PermissionError("Only owner can share")
        
        grant = AccessGrant(
            grant_id=str(uuid.uuid4()),
            company_id=entity.company_id,
            created_by=created_by,
            resource_type="entity",
            resource_id=entity_id,
            grant_type="user",
            target_user_id=target_user_id,
            role=role
        )
        
        await self._grant_repo.create(grant)
        logger.info(f"Entity {entity_id} shared with user {target_user_id} (role={role})")
        return grant
    
    async def grant_entity_to_company(
        self,
        entity_id: str,
        target_company_id: str,
        role: str,
        created_by: str
    ) -> AccessGrant:
        """Пошерить entity целой компании"""
        
        entity = await self._entity_repo.get(entity_id)
        if not entity:
            raise ValueError("Entity not found")
        
        if not entity.user_id:
            raise ValueError("Entity has no owner (user_id not set)")
        
        if entity.user_id != created_by:
            raise PermissionError("Only owner can share")
        
        grant = AccessGrant(
            grant_id=str(uuid.uuid4()),
            company_id=entity.company_id,
            created_by=created_by,
            resource_type="entity",
            resource_id=entity_id,
            grant_type="company",
            target_company_id=target_company_id,
            role=role
        )
        
        await self._grant_repo.create(grant)
        logger.info(f"Entity {entity_id} shared with company {target_company_id} (role={role})")
        return grant
    
    # === NAMESPACE GRANTS ===
    
    async def grant_namespace_public(
        self,
        namespace: str,
        company_id: str,
        created_by: str
    ) -> AccessGrant:
        """Сделать весь namespace публичным"""
        
        grant = AccessGrant(
            grant_id=str(uuid.uuid4()),
            company_id=company_id,
            created_by=created_by,
            resource_type="namespace",
            resource_id=namespace,
            grant_type="public",
            role="viewer"
        )
        
        await self._grant_repo.create(grant)
        logger.info(f"Namespace {namespace} made public by {created_by}")
        return grant
    
    async def grant_namespace_to_user(
        self,
        namespace: str,
        company_id: str,
        target_user_id: str,
        role: str,
        created_by: str
    ) -> AccessGrant:
        """Пошерить namespace конкретному user"""
        
        grant = AccessGrant(
            grant_id=str(uuid.uuid4()),
            company_id=company_id,
            created_by=created_by,
            resource_type="namespace",
            resource_id=namespace,
            grant_type="user",
            target_user_id=target_user_id,
            role=role
        )
        
        await self._grant_repo.create(grant)
        logger.info(f"Namespace {namespace} shared with user {target_user_id} (role={role})")
        return grant
    
    async def grant_namespace_to_company(
        self,
        namespace: str,
        company_id: str,
        target_company_id: str,
        role: str,
        created_by: str
    ) -> AccessGrant:
        """Пошерить namespace целой компании"""
        
        grant = AccessGrant(
            grant_id=str(uuid.uuid4()),
            company_id=company_id,
            created_by=created_by,
            resource_type="namespace",
            resource_id=namespace,
            grant_type="company",
            target_company_id=target_company_id,
            role=role
        )
        
        await self._grant_repo.create(grant)
        logger.info(f"Namespace {namespace} shared with company {target_company_id} (role={role})")
        return grant
    
    # === УПРАВЛЕНИЕ ===
    
    async def revoke_grant(
        self,
        grant_id: str,
        user_id: str
    ) -> bool:
        """Отозвать grant"""
        
        grant = await self._grant_repo.get(grant_id)
        if not grant:
            raise ValueError("Grant not found")
        
        if grant.created_by != user_id:
            raise PermissionError("Only creator can revoke")
        
        await self._grant_repo.delete(grant_id)
        logger.info(f"Grant {grant_id} revoked by {user_id}")
        return True
    
    async def list_grants(
        self,
        resource_type: str,
        resource_id: str,
        resource_company_id: Optional[str] = None
    ) -> List[AccessGrant]:
        """Список всех grants для ресурса"""
        
        return await self._grant_repo.find_by_resource(resource_type, resource_id, resource_company_id)
    
    async def get_grant(self, grant_id: str) -> AccessGrant:
        """Получить grant по ID"""
        grant = await self._grant_repo.get(grant_id)
        if not grant:
            raise ValueError("Grant not found")
        return grant

