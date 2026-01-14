"""
Репозиторий для запросов на доступ.
"""

from typing import List, Optional, Type

from sqlalchemy import select

from apps.crm.db.base import BaseCRMRepository, CRMDatabase
from apps.crm.db.models import AccessRequest


class AccessRequestRepository(BaseCRMRepository[AccessRequest]):
    """
    Репозиторий для работы с запросами на доступ.
    """
    
    def __init__(self, db: CRMDatabase):
        super().__init__(db)
    
    @property
    def model_class(self) -> Type[AccessRequest]:
        return AccessRequest
    
    @property
    def id_field(self) -> str:
        return "request_id"
    
    async def get_by_owner(
        self,
        owner_id: str,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[AccessRequest]:
        """Получает запросы, направленные владельцу ресурсов"""
        async with self._db.session() as session:
            stmt = select(AccessRequest).where(
                AccessRequest.owner_id == owner_id
            )
            
            if status:
                stmt = stmt.where(AccessRequest.status == status)
            
            stmt = stmt.order_by(AccessRequest.created_at.desc()).limit(limit)
            
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def get_by_requester(
        self,
        requester_id: str,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[AccessRequest]:
        """Получает запросы, отправленные пользователем"""
        async with self._db.session() as session:
            stmt = select(AccessRequest).where(
                AccessRequest.requester_id == requester_id
            )
            
            if status:
                stmt = stmt.where(AccessRequest.status == status)
            
            stmt = stmt.order_by(AccessRequest.created_at.desc()).limit(limit)
            
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def get_by_resource(
        self,
        resource_type: str,
        resource_id: str
    ) -> List[AccessRequest]:
        """Получает все запросы на конкретный ресурс"""
        async with self._db.session() as session:
            stmt = select(AccessRequest).where(
                AccessRequest.resource_type == resource_type,
                AccessRequest.resource_id == resource_id
            ).order_by(AccessRequest.created_at.desc())
            
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def get_pending_count(self, owner_id: str) -> int:
        """Подсчитывает количество ожидающих запросов для владельца"""
        async with self._db.session() as session:
            from sqlalchemy import func
            
            stmt = select(func.count(AccessRequest.request_id)).where(
                AccessRequest.owner_id == owner_id,
                AccessRequest.status == "pending"
            )
            
            result = await session.execute(stmt)
            return result.scalar() or 0
    
    async def exists(
        self,
        requester_id: str,
        resource_type: str,
        resource_id: str,
        status: str = "pending"
    ) -> bool:
        """Проверяет существует ли уже запрос"""
        async with self._db.session() as session:
            stmt = select(AccessRequest.request_id).where(
                AccessRequest.requester_id == requester_id,
                AccessRequest.resource_type == resource_type,
                AccessRequest.resource_id == resource_id,
                AccessRequest.status == status
            ).limit(1)
            
            result = await session.execute(stmt)
            return result.scalar_one_or_none() is not None
    
    async def create(self, request: AccessRequest) -> AccessRequest:
        """Создает запрос на доступ"""
        async with self._db.session() as session:
            session.add(request)
            await session.commit()
            await session.refresh(request)
            return request
    
    async def update_status(
        self,
        request_id: str,
        status: str
    ) -> Optional[AccessRequest]:
        """Обновляет статус запроса"""
        async with self._db.session() as session:
            stmt = select(AccessRequest).where(
                AccessRequest.request_id == request_id
            )
            result = await session.execute(stmt)
            request = result.scalar_one_or_none()
            
            if not request:
                return None
            
            request.status = status
            await session.commit()
            await session.refresh(request)
            return request
    
    async def list_by_company(
        self,
        company_id: str,
        limit: int = 100
    ) -> List[AccessRequest]:
        """Получает все запросы для компании"""
        async with self._db.session() as session:
            stmt = select(AccessRequest).where(
                AccessRequest.company_id == company_id
            ).order_by(AccessRequest.created_at.desc()).limit(limit)
            
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def list_by_company_and_status(
        self,
        company_id: str,
        status: str,
        limit: int = 100
    ) -> List[AccessRequest]:
        """Получает запросы для компании с фильтром по статусу"""
        async with self._db.session() as session:
            stmt = select(AccessRequest).where(
                AccessRequest.company_id == company_id,
                AccessRequest.status == status
            ).order_by(AccessRequest.created_at.desc()).limit(limit)
            
            result = await session.execute(stmt)
            return list(result.scalars().all())

