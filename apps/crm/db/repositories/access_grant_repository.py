"""
Репозиторий для AccessGrants.
"""

from typing import List, Optional, Type
from sqlalchemy import select

from apps.crm.db.models import AccessGrant
from apps.crm.db.base import BaseCRMRepository, CRMDatabase
from core.context import get_context


class AccessGrantRepository(BaseCRMRepository[AccessGrant]):
    """Репозиторий для работы с AccessGrants"""
    
    def __init__(self, db: CRMDatabase):
        super().__init__(db)
    
    @property
    def model_class(self) -> Type[AccessGrant]:
        return AccessGrant
    
    @property
    def id_field(self) -> str:
        return "grant_id"
    
    async def find_by_resource(
        self,
        resource_type: str,
        resource_id: str,
        resource_company_id: Optional[str] = None
    ) -> List[AccessGrant]:
        """
        Найти все grants для ресурса.
        
        Args:
            resource_company_id: Company ID ресурса (не запрашивающего пользователя!)
                                Если None, ищет во всех компаниях
        """
        async with self._db.session() as session:
            query = (
                select(AccessGrant)
                .where(AccessGrant.resource_type == resource_type)
                .where(AccessGrant.resource_id == resource_id)
            )
            
            if resource_company_id:
                query = query.where(AccessGrant.company_id == resource_company_id)
            
            result = await session.execute(query)
            return list(result.scalars().all())
    
    async def find_by_user(
        self,
        user_id: str
    ) -> List[AccessGrant]:
        """Найти все grants для user"""
        async with self._db.session() as session:
            result = await session.execute(
                select(AccessGrant)
                .where(AccessGrant.grant_type == "user")
                .where(AccessGrant.target_user_id == user_id)
            )
            return list(result.scalars().all())
    
    async def find_by_company(
        self,
        company_id: str
    ) -> List[AccessGrant]:
        """Найти все grants для company"""
        async with self._db.session() as session:
            result = await session.execute(
                select(AccessGrant)
                .where(AccessGrant.grant_type == "company")
                .where(AccessGrant.target_company_id == company_id)
            )
            return list(result.scalars().all())

