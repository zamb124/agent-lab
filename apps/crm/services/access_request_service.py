"""
AccessRequestService - управление запросами на доступ к скрытым ресурсам.
"""

import logging
import uuid
from typing import List, Optional

from core.context import get_context

from apps.crm.db.repositories.access_request_repository import AccessRequestRepository
from apps.crm.db.repositories.note_repository import NoteRepository
from apps.crm.db.models import AccessRequest
from apps.crm.models.access_request_models import (
    AccessRequestCreate,
    AccessRequestResponse,
    AccessRequestStatus,
)

logger = logging.getLogger(__name__)


class AccessRequestService:
    """
    Сервис для работы с запросами на доступ.
    
    Позволяет:
    - Запрашивать доступ к приватным ресурсам
    - Одобрять/отклонять запросы
    - Автоматически обновлять shared_with при одобрении
    """
    
    def __init__(
        self,
        access_request_repository: AccessRequestRepository,
        note_repository: NoteRepository,
    ):
        self._repo = access_request_repository
        self._note_repo = note_repository
    
    def _get_user_id(self) -> str:
        """Получает ID текущего пользователя"""
        context = get_context()
        if not context or not context.user:
            raise ValueError("Нет пользователя в контексте")
        return context.user.user_id
    
    def _get_company_id(self) -> str:
        """Получает ID текущей компании"""
        context = get_context()
        if not context or not context.active_company:
            raise ValueError("Нет активной компании в контексте")
        return context.active_company.company_id
    
    async def create_request(
        self,
        data: AccessRequestCreate
    ) -> AccessRequestResponse:
        """
        Создает запрос на доступ к ресурсу.
        
        При создании определяет владельца ресурса автоматически.
        """
        user_id = self._get_user_id()
        company_id = self._get_company_id()
        
        # Определяем владельца ресурса
        owner_id = await self._get_resource_owner(data.resource_type, data.resource_id)
        
        if owner_id == user_id:
            raise ValueError("Нельзя запрашивать доступ к своим ресурсам")
        
        # Проверяем нет ли уже активного запроса
        exists = await self._repo.exists(
            requester_id=user_id,
            resource_type=data.resource_type,
            resource_id=data.resource_id
        )
        if exists:
            raise ValueError("Запрос на доступ к этому ресурсу уже отправлен")
        
        # Создаем запрос
        request = AccessRequest(
            request_id=str(uuid.uuid4()),
            company_id=company_id,
            requester_id=user_id,
            owner_id=owner_id,
            resource_type=data.resource_type,
            resource_id=data.resource_id,
            message=data.message,
            status="pending"
        )
        
        request = await self._repo.create(request)
        logger.info(f"Создан запрос на доступ {request.request_id} к {data.resource_type}:{data.resource_id}")
        
        return await self._to_response(request)
    
    async def _get_resource_owner(self, resource_type: str, resource_id: str) -> str:
        """Определяет владельца ресурса"""
        if resource_type == "note":
            note = await self._note_repo.get(resource_id)
            if not note:
                raise ValueError("Заметка не найдена")
            return note.user_id
        else:
            # Для entities - пока не поддерживаем
            raise ValueError(f"Неподдерживаемый тип ресурса: {resource_type}")
    
    async def get_incoming_requests(
        self,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[AccessRequestResponse]:
        """Получает входящие запросы (для владельца ресурсов)"""
        user_id = self._get_user_id()
        requests = await self._repo.get_by_owner(user_id, status, limit)
        return [await self._to_response(r) for r in requests]
    
    async def get_outgoing_requests(
        self,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[AccessRequestResponse]:
        """Получает исходящие запросы (отправленные пользователем)"""
        user_id = self._get_user_id()
        requests = await self._repo.get_by_requester(user_id, status, limit)
        return [await self._to_response(r) for r in requests]
    
    async def get_pending_count(self) -> int:
        """Подсчитывает количество ожидающих входящих запросов"""
        user_id = self._get_user_id()
        return await self._repo.get_pending_count(user_id)
    
    async def approve_request(self, request_id: str) -> AccessRequestResponse:
        """
        Одобряет запрос на доступ.
        
        При одобрении автоматически добавляет пользователя в shared_with ресурса.
        """
        user_id = self._get_user_id()
        
        request = await self._repo.get(request_id)
        if not request:
            raise ValueError("Запрос не найден")
        
        if request.owner_id != user_id:
            raise ValueError("Только владелец может одобрить запрос")
        
        if request.status != "pending":
            raise ValueError(f"Запрос уже обработан: {request.status}")
        
        # Обновляем статус
        request = await self._repo.update_status(request_id, "approved")
        
        # Добавляем пользователя в shared_with
        await self._grant_access(request.resource_type, request.resource_id, request.requester_id)
        
        logger.info(f"Запрос {request_id} одобрен, доступ предоставлен {request.requester_id}")
        
        return await self._to_response(request)
    
    async def reject_request(self, request_id: str) -> AccessRequestResponse:
        """Отклоняет запрос на доступ"""
        user_id = self._get_user_id()
        
        request = await self._repo.get(request_id)
        if not request:
            raise ValueError("Запрос не найден")
        
        if request.owner_id != user_id:
            raise ValueError("Только владелец может отклонить запрос")
        
        if request.status != "pending":
            raise ValueError(f"Запрос уже обработан: {request.status}")
        
        request = await self._repo.update_status(request_id, "rejected")
        logger.info(f"Запрос {request_id} отклонен")
        
        return await self._to_response(request)
    
    async def _grant_access(self, resource_type: str, resource_id: str, user_id: str):
        """Предоставляет доступ к ресурсу"""
        if resource_type == "note":
            note = await self._note_repo.get(resource_id)
            if note:
                shared_with = list(note.shared_with or [])
                if user_id not in shared_with:
                    shared_with.append(user_id)
                    note.shared_with = shared_with
                    await self._note_repo.update(note)
    
    async def _to_response(self, request: AccessRequest) -> AccessRequestResponse:
        """Конвертирует модель в response"""
        # Получаем название ресурса
        resource_title = None
        if request.resource_type == "note":
            note = await self._note_repo.get(request.resource_id)
            if note:
                resource_title = note.title
        
        return AccessRequestResponse(
            request_id=request.request_id,
            company_id=request.company_id,
            requester_id=request.requester_id,
            owner_id=request.owner_id,
            resource_type=request.resource_type,
            resource_id=request.resource_id,
            message=request.message,
            status=request.status,
            created_at=request.created_at,
            updated_at=request.updated_at,
            resource_title=resource_title,
        )

