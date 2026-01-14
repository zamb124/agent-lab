"""
Сервис проверки доступа через AccessGrants.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from apps.crm.models.entity import ChromaDBEntity
from apps.crm.db.models import AccessGrant
from apps.crm.db.repositories.access_grant_repository import AccessGrantRepository
from apps.crm.db.repositories.entity_type_repository import EntityTypeRepository
from core.logging import get_logger

logger = get_logger(__name__)


class AccessControlService:
    """Единая точка проверки доступа через AccessGrants"""
    
    def __init__(
        self,
        grant_repo: AccessGrantRepository,
        entity_type_repo: EntityTypeRepository
    ):
        self._grant_repo = grant_repo
        self._entity_type_repo = entity_type_repo
    
    async def can_read_entity(
        self,
        entity: ChromaDBEntity,
        user_id: Optional[str],
        company_id: Optional[str]
    ) -> bool:
        """Проверка доступа к entity"""
        
        # 1. Владелец всегда может
        if user_id and entity.user_id == user_id:
            return True
        
        # 2. Same company + same namespace
        if user_id and company_id == entity.company_id:
            user_ns = await self._get_user_namespace(user_id)
            if user_ns == entity.namespace:
                return True
        
        # 3. AccessGrants для ENTITY
        entity_grants = await self._grant_repo.find_by_resource(
            resource_type="entity",
            resource_id=entity.entity_id
        )
        
        for grant in entity_grants:
            if await self._check_grant(grant, user_id, company_id):
                return True
        
        # 4. AccessGrants для NAMESPACE
        namespace_grants = await self._grant_repo.find_by_resource(
            "namespace",
            entity.namespace,
            entity.company_id
        )
        
        for grant in namespace_grants:
            if await self._check_grant(grant, user_id, company_id):
                return True
        
        return False
    
    async def can_write_entity(
        self,
        entity: ChromaDBEntity,
        user_id: str,
        company_id: str
    ) -> bool:
        """Проверка прав на редактирование"""
        
        # Владелец
        if entity.user_id == user_id:
            return True
        
        # Same namespace
        if company_id == entity.company_id:
            user_ns = await self._get_user_namespace(user_id)
            if user_ns == entity.namespace:
                return True
        
        # Grants с ролью editor/admin
        grants = await self._grant_repo.find_by_resource("entity", entity.entity_id, entity.company_id)
        grants += await self._grant_repo.find_by_resource("namespace", entity.namespace, entity.company_id)
        
        for grant in grants:
            if grant.role in ["editor", "admin"]:
                if await self._check_grant(grant, user_id, company_id):
                    return True
        
        return False
    
    async def filter_fields(
        self,
        entity: ChromaDBEntity,
        user_id: Optional[str],
        company_id: Optional[str]
    ) -> Dict[str, Any]:
        """Фильтрация полей для публичного доступа"""
        
        # Проверяем ПОЛНЫЙ доступ (owner, same company+namespace, grants с ролью)
        has_full_access = await self._has_full_access(entity, user_id, company_id)
        if has_full_access:
            return entity.model_dump()
        
        # Проверяем публичные гранты
        entity_grants = await self._grant_repo.find_by_resource("entity", entity.entity_id, entity.company_id)
        namespace_grants = await self._grant_repo.find_by_resource("namespace", entity.namespace, entity.company_id)
        
        # Если есть хоть один public grant
        for grant in entity_grants + namespace_grants:
            if grant.grant_type == "public":
                # Expired?
                if grant.expires_at and grant.expires_at < datetime.now(timezone.utc):
                    continue
                return await self._filter_public_fields(entity)
        
        raise PermissionError("Access denied")
    
    async def _filter_public_fields(
        self,
        entity: ChromaDBEntity
    ) -> Dict[str, Any]:
        """Фильтрация по EntityType.public_fields"""
        
        entity_type = await self._entity_type_repo.get(entity.entity_type)
        
        # Возвращаем ТОЛЬКО публичные поля
        result = {
            "entity_id": entity.entity_id,
            "entity_type": entity.entity_type,
        }
        
        # Добавляем поля из public_fields
        if entity_type and entity_type.public_fields:
            for field_path in entity_type.public_fields:
                value = self._get_nested_value(entity, field_path)
                if value is not None:
                    self._set_nested_value(result, field_path, value)
        
        return result
    
    async def _has_full_access(
        self,
        entity: ChromaDBEntity,
        user_id: Optional[str],
        company_id: Optional[str]
    ) -> bool:
        """Проверка ПОЛНОГО доступа (без учета публичных грантов)"""
        
        # Владелец
        if user_id and entity.user_id == user_id:
            return True
        
        # Same company + namespace
        if company_id and company_id == entity.company_id:
            user_ns = await self._get_user_namespace(user_id)
            if user_ns == entity.namespace:
                return True
        
        # Гранты с ролью (НЕ публичные)
        grants = await self._grant_repo.find_by_resource("entity", entity.entity_id, entity.company_id)
        grants += await self._grant_repo.find_by_resource("namespace", entity.namespace, entity.company_id)
        
        for grant in grants:
            # Пропускаем публичные гранты - они дают ограниченный доступ
            if grant.grant_type == "public":
                continue
            
            # User/Company гранты с ролью viewer+
            if grant.role in ["viewer", "editor", "admin"]:
                if await self._check_grant(grant, user_id, company_id):
                    return True
        
        return False
    
    async def _check_grant(
        self,
        grant: AccessGrant,
        user_id: Optional[str],
        company_id: Optional[str]
    ) -> bool:
        """Проверить конкретный grant"""
        
        # Expired?
        if grant.expires_at and grant.expires_at < datetime.now(timezone.utc):
            return False
        
        # Public
        if grant.grant_type == "public":
            return True
        
        # User
        if grant.grant_type == "user" and user_id:
            return user_id == grant.target_user_id
        
        # Company
        if grant.grant_type == "company" and company_id:
            return company_id == grant.target_company_id
        
        return False
    
    def _get_nested_value(self, obj: Any, path: str) -> Any:
        """Получить значение по пути (attributes.position)"""
        keys = path.split(".")
        value = obj
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            elif hasattr(value, key):
                value = getattr(value, key)
            else:
                return None
        return value
    
    def _set_nested_value(self, obj: Dict, path: str, value: Any):
        """Установить значение по пути"""
        keys = path.split(".")
        for key in keys[:-1]:
            if key not in obj:
                obj[key] = {}
            obj = obj[key]
        obj[keys[-1]] = value
    
    async def _get_user_namespace(self, user_id: str) -> str:
        """Получить namespace пользователя (по умолчанию 'default')"""
        # TODO: из UserProfile
        return "default"

