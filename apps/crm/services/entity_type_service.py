"""
EntityTypeService - управление типами сущностей CRM.
"""

import logging
from typing import List, Optional
from datetime import datetime, timezone

from core.context import get_context
from apps.crm.db.models import EntityType
from apps.crm.db.repositories.entity_type_repository import EntityTypeRepository
from apps.crm.models.entity_type_models import (
    EntityTypeCreate,
    EntityTypeUpdate,
    EntityTypeResponse,
)

logger = logging.getLogger(__name__)


SYSTEM_ENTITY_TYPES = [
    {
        "type_id": "person",
        "name": "People",
        "description": "Физическое лицо, человек, контакт",
        "prompt": """Персона - это любое физическое лицо, упомянутое в тексте.
Извлекай: имя (полное или частичное), должность, email, телефон, компанию где работает.
Примеры: "Иван Петров", "CEO Acme Corp", "менеджер Мария".""",
        "required_attributes": ["name"],
        "optional_attributes": ["email", "phone", "position", "company"],
        "icon": "ti-user",
        "color": "#4A90E2",
        "is_system": True,
        "check_duplicates": True,
        "is_filtered": False,
    },
    {
        "type_id": "organization",
        "name": "Organizations",
        "description": "Организация, компания, партнер, клиент",
        "prompt": """Организация - это компания, предприятие, фирма, партнер, клиент.
Извлекай: название компании, отрасль, адрес, сайт.
Примеры: "Google", "ООО Рога и Копыта", "банк ВТБ".""",
        "required_attributes": ["name"],
        "optional_attributes": ["industry", "website", "address", "inn"],
        "icon": "ti-building",
        "color": "#8A2BE2",
        "is_system": True,
        "check_duplicates": True,
        "is_filtered": False,
    },
    {
        "type_id": "project",
        "name": "Projects",
        "description": "Проект или инициатива",
        "prompt": """Проект - это проект, крупная задача, инициатива, кампания.
Извлекай: название проекта, дедлайн, статус, участники.
Примеры: "запуск нового сайта", "рекламная кампания Q4", "интеграция с CRM".""",
        "required_attributes": ["name"],
        "optional_attributes": ["deadline", "status", "budget"],
        "icon": "ti-folder",
        "color": "#FF6B6B",
        "is_system": True,
        "check_duplicates": True,
        "is_filtered": False,
    },
    {
        "type_id": "task",
        "name": "Tasks",
        "description": "Задача или дело",
        "prompt": """Задача - это конкретное действие, которое нужно выполнить.
Извлекай: что сделать, кому назначено, срок, приоритет.
Примеры: "позвонить клиенту", "отправить КП до пятницы", "срочно проверить отчет".""",
        "required_attributes": ["name"],
        "optional_attributes": ["assignee", "due_date", "priority"],
        "icon": "ti-checklist",
        "color": "#FFA500",
        "is_system": True,
        "check_duplicates": False,
        "is_filtered": False,
    },
]


class EntityTypeService:
    """
    Сервис для работы с типами сущностей.
    
    Типы делятся на:
    - Системные (is_system=True) - person, organization, project, task
    - Кастомные (company_id != None) - создаются пользователями
    """
    
    def __init__(self, entity_type_repository: EntityTypeRepository):
        self._repo = entity_type_repository
    
    def _get_company_id(self) -> str:
        """Получает company_id из контекста"""
        context = get_context()
        if not context or not context.active_company:
            raise ValueError("Нет активной компании в контексте")
        return context.active_company.company_id
    
    async def init_system_types(self) -> List[EntityType]:
        """Инициализирует системные типы сущностей"""
        created = []
        
        for type_data in SYSTEM_ENTITY_TYPES:
            existing = await self._repo.get(type_data["type_id"])
            if existing:
                continue
            
            entity_type = EntityType(
                type_id=type_data["type_id"],
                company_id=None,
                name=type_data["name"],
                description=type_data["description"],
                prompt=type_data["prompt"],
                required_attributes=type_data["required_attributes"],
                optional_attributes=type_data["optional_attributes"],
                icon=type_data["icon"],
                color=type_data["color"],
                is_system=True,
                check_duplicates=type_data["check_duplicates"],
                is_filtered=type_data["is_filtered"],
                created_at=datetime.now(timezone.utc),
            )
            
            await self._repo.create(entity_type)
            created.append(entity_type)
            logger.info(f"Создан системный тип: {type_data['type_id']}")
        
        return created
    
    async def get_all_types(self, company_id: Optional[str] = None) -> List[EntityTypeResponse]:
        """Получает все типы для компании (системные + кастомные)"""
        company_id = company_id or self._get_company_id()
        
        types = await self._repo.get_all_for_company(company_id)
        return [self._to_response(t) for t in types]
    
    async def get_type(
        self, 
        type_id: str, 
        company_id: Optional[str] = None
    ) -> Optional[EntityTypeResponse]:
        """Получает тип по ID"""
        company_id = company_id or self._get_company_id()
        
        entity_type = await self._repo.get_by_company(company_id, type_id)
        if not entity_type:
            return None
        return self._to_response(entity_type)
    
    async def create_type(
        self, 
        data: EntityTypeCreate,
        company_id: Optional[str] = None
    ) -> EntityTypeResponse:
        """Создает кастомный тип сущности"""
        company_id = company_id or self._get_company_id()
        
        existing = await self._repo.exists(data.type_id, company_id)
        if existing:
            raise ValueError(f"Тип '{data.type_id}' уже существует")
        
        entity_type = EntityType(
            type_id=data.type_id,
            company_id=company_id,
            name=data.name,
            description=data.description,
            prompt=data.prompt,
            required_attributes=data.required_attributes,
            optional_attributes=data.optional_attributes,
            icon=data.icon,
            color=data.color,
            is_system=False,
            check_duplicates=data.check_duplicates,
            is_filtered=data.is_filtered,
            created_at=datetime.now(timezone.utc),
        )
        
        await self._repo.create(entity_type)
        logger.info(f"Создан кастомный тип: {data.type_id} (company={company_id})")
        
        return self._to_response(entity_type)
    
    async def update_type(
        self, 
        type_id: str,
        data: EntityTypeUpdate,
        company_id: Optional[str] = None
    ) -> Optional[EntityTypeResponse]:
        """Обновляет тип сущности (только кастомные)"""
        company_id = company_id or self._get_company_id()
        
        entity_type = await self._repo.get_by_company(company_id, type_id)
        if not entity_type:
            return None
        
        if entity_type.is_system:
            raise ValueError("Системные типы нельзя редактировать")
        
        if data.name is not None:
            entity_type.name = data.name
        if data.description is not None:
            entity_type.description = data.description
        if data.prompt is not None:
            entity_type.prompt = data.prompt
        if data.required_attributes is not None:
            entity_type.required_attributes = data.required_attributes
        if data.optional_attributes is not None:
            entity_type.optional_attributes = data.optional_attributes
        if data.icon is not None:
            entity_type.icon = data.icon
        if data.color is not None:
            entity_type.color = data.color
        if data.check_duplicates is not None:
            entity_type.check_duplicates = data.check_duplicates
        if data.is_filtered is not None:
            entity_type.is_filtered = data.is_filtered
        
        await self._repo.update(entity_type)
        logger.info(f"Обновлен тип: {type_id}")
        
        return self._to_response(entity_type)
    
    async def delete_type(
        self, 
        type_id: str,
        company_id: Optional[str] = None
    ) -> bool:
        """Удаляет кастомный тип сущности"""
        company_id = company_id or self._get_company_id()
        
        entity_type = await self._repo.get_by_company(company_id, type_id)
        if not entity_type:
            return False
        
        if entity_type.is_system:
            raise ValueError("Системные типы нельзя удалять")
        
        success = await self._repo.delete(type_id)
        if success:
            logger.info(f"Удален тип: {type_id}")
        return success
    
    def _to_response(self, entity_type: EntityType) -> EntityTypeResponse:
        """Конвертирует модель в response"""
        return EntityTypeResponse(
            type_id=entity_type.type_id,
            company_id=entity_type.company_id,
            name=entity_type.name,
            description=entity_type.description,
            prompt=entity_type.prompt,
            required_attributes=entity_type.required_attributes or [],
            optional_attributes=entity_type.optional_attributes or [],
            icon=entity_type.icon,
            color=entity_type.color,
            is_system=entity_type.is_system,
            check_duplicates=entity_type.check_duplicates,
            is_filtered=entity_type.is_filtered,
            created_at=entity_type.created_at,
        )

