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
    FieldDefinition,
)

logger = logging.getLogger(__name__)


SYSTEM_ENTITY_TYPES = [
    {
        "type_id": "person",
        "name": "People",
        "description": "Физическое лицо, человек, контакт",
        "prompt": "Персона - это любое физическое лицо, упомянутое в тексте.",
        "required_fields": {
            "name": {
                "label": "Имя",
                "type": "str",
                "category": "main",
                "prompt": "Извлекай полное имя человека (ФИО или часть)",
                "icon": "ti-user",
            },
        },
        "optional_fields": {
            "email": {
                "label": "Email",
                "type": "email",
                "category": "main",
                "prompt": "Извлекай email адреса",
                "icon": "ti-mail",
                "placeholder": "email@example.com",
            },
            "phone": {
                "label": "Телефон",
                "type": "phone",
                "category": "main",
                "prompt": "Извлекай номера телефонов",
                "icon": "ti-phone",
                "placeholder": "+7 999 123-45-67",
            },
            "position": {
                "label": "Должность",
                "type": "str",
                "category": "optional",
                "prompt": "Извлекай должность/роль человека",
                "icon": "ti-briefcase",
            },
            "company": {
                "label": "Компания",
                "type": "str",
                "category": "optional",
                "prompt": "Извлекай название компании где работает",
                "icon": "ti-building",
            },
            "linkedin": {
                "label": "LinkedIn",
                "type": "link",
                "category": "optional",
                "prompt": "Извлекай ссылку на LinkedIn профиль",
                "icon": "ti-brand-linkedin",
                "placeholder": "https://linkedin.com/in/...",
            },
            "location": {
                "label": "Локация",
                "type": "str",
                "category": "optional",
                "prompt": "Извлекай город/страну проживания",
                "icon": "ti-map-pin",
            },
        },
        "icon": "ti-user",
        "color": "#4A90E2",
        "is_system": True,
        "is_event": False,
        "check_duplicates": True,
        "is_filtered": False,
        "weight_coefficient": 1.2,
    },
    {
        "type_id": "organization",
        "name": "Organizations",
        "description": "Организация, компания, партнер, клиент",
        "prompt": "Организация - это компания, предприятие, фирма, партнер, клиент.",
        "required_fields": {
            "name": {
                "label": "Название",
                "type": "str",
                "category": "main",
                "prompt": "Извлекай название организации",
                "icon": "ti-building",
            },
        },
        "optional_fields": {
            "industry": {
                "label": "Отрасль",
                "type": "str",
                "category": "optional",
                "prompt": "Извлекай отрасль/сферу деятельности",
                "icon": "ti-category",
            },
            "website": {
                "label": "Сайт",
                "type": "link",
                "category": "main",
                "prompt": "Извлекай URL сайта компании",
                "icon": "ti-world",
                "placeholder": "https://example.com",
            },
            "address": {
                "label": "Адрес",
                "type": "str",
                "category": "optional",
                "prompt": "Извлекай адрес офиса",
                "icon": "ti-map-pin",
            },
            "inn": {
                "label": "ИНН",
                "type": "str",
                "category": "optional",
                "prompt": "Извлекай ИНН организации",
                "icon": "ti-id",
            },
            "phone": {
                "label": "Телефон",
                "type": "phone",
                "category": "main",
                "prompt": "Извлекай телефон организации",
                "icon": "ti-phone",
            },
            "email": {
                "label": "Email",
                "type": "email",
                "category": "main",
                "prompt": "Извлекай email организации",
                "icon": "ti-mail",
            },
        },
        "icon": "ti-building",
        "color": "#8A2BE2",
        "is_system": True,
        "is_event": False,
        "check_duplicates": True,
        "is_filtered": False,
        "weight_coefficient": 1.1,
    },
    {
        "type_id": "project",
        "name": "Projects",
        "description": "Проект или инициатива",
        "prompt": "Проект - это проект, крупная задача, инициатива, кампания.",
        "required_fields": {
            "name": {
                "label": "Название",
                "type": "str",
                "category": "main",
                "prompt": "Извлекай название проекта",
                "icon": "ti-folder",
            }
        },
        "optional_fields": {
            "deadline": {
                "label": "Дедлайн",
                "type": "date",
                "category": "main",
                "prompt": "Извлекай дату дедлайна проекта",
                "icon": "ti-calendar",
            },
            "status": {
                "label": "Статус",
                "type": "str",
                "category": "optional",
                "prompt": "Извлекай текущий статус проекта",
                "icon": "ti-chart-dots",
            },
            "budget": {
                "label": "Бюджет",
                "type": "str",
                "category": "optional",
                "prompt": "Извлекай бюджет проекта",
                "icon": "ti-currency-dollar",
            },
            "description": {
                "label": "Описание",
                "type": "textarea",
                "category": "optional",
                "prompt": "Извлекай описание проекта",
                "icon": "ti-file-text",
            },
        },
        "icon": "ti-folder",
        "color": "#FF6B6B",
        "is_system": True,
        "is_event": False,
        "check_duplicates": True,
        "is_filtered": False,
        "weight_coefficient": 1.0,
    },
    {
        "type_id": "task",
        "name": "Tasks",
        "description": "Задача или дело",
        "prompt": "Задача - это конкретное действие, которое нужно выполнить.",
        "required_fields": {
            "name": {
                "label": "Название",
                "type": "str",
                "category": "main",
                "prompt": "Извлекай что нужно сделать",
                "icon": "ti-checklist",
            }
        },
        "optional_fields": {
            "assignee": {
                "label": "Исполнитель",
                "type": "str",
                "category": "optional",
                "prompt": "Извлекай кому назначена задача",
                "icon": "ti-user",
            },
            "due_date": {
                "label": "Срок",
                "type": "date",
                "category": "main",
                "prompt": "Извлекай срок выполнения",
                "icon": "ti-calendar",
            },
            "priority": {
                "label": "Приоритет",
                "type": "str",
                "category": "optional",
                "prompt": "Извлекай приоритет задачи (низкий, средний, высокий, срочный)",
                "icon": "ti-flag",
            },
        },
        "icon": "ti-checklist",
        "color": "#FFA500",
        "is_system": True,
        "is_event": False,
        "check_duplicates": False,
        "is_filtered": False,
        "weight_coefficient": 0.8,
    },
    # Event types
    {
        "type_id": "meeting",
        "name": "Meetings",
        "description": "Встреча, совещание, переговоры",
        "prompt": "Встреча - это запланированное мероприятие с участниками: совещание, переговоры, конференция.",
        "required_fields": {
            "name": {
                "label": "Название",
                "type": "str",
                "category": "main",
                "prompt": "Извлекай название или тему встречи",
                "icon": "ti-users",
            }
        },
        "optional_fields": {
            "date": {
                "label": "Дата",
                "type": "date",
                "category": "main",
                "prompt": "Извлекай дату проведения встречи",
                "icon": "ti-calendar",
            },
            "location": {
                "label": "Место",
                "type": "str",
                "category": "optional",
                "prompt": "Извлекай место проведения встречи",
                "icon": "ti-map-pin",
            },
            "duration": {
                "label": "Длительность",
                "type": "str",
                "category": "optional",
                "prompt": "Извлекай длительность встречи",
                "icon": "ti-clock",
            },
            "summary": {
                "label": "Резюме",
                "type": "textarea",
                "category": "optional",
                "prompt": "Извлекай краткое резюме встречи",
                "icon": "ti-file-text",
            },
        },
        "icon": "ti-users",
        "color": "#10B981",
        "is_system": True,
        "is_event": True,
        "check_duplicates": False,
        "is_filtered": True,
        "weight_coefficient": 0.9,
    },
    {
        "type_id": "call",
        "name": "Calls",
        "description": "Телефонный звонок, видеозвонок",
        "prompt": "Звонок - это телефонный или видео разговор с собеседниками.",
        "required_fields": {
            "name": {
                "label": "Тема",
                "type": "str",
                "category": "main",
                "prompt": "Извлекай тему или цель звонка",
                "icon": "ti-phone",
            }
        },
        "optional_fields": {
            "date": {
                "label": "Дата",
                "type": "date",
                "category": "main",
                "prompt": "Извлекай дату звонка",
                "icon": "ti-calendar",
            },
            "duration": {
                "label": "Длительность",
                "type": "str",
                "category": "optional",
                "prompt": "Извлекай длительность звонка",
                "icon": "ti-clock",
            },
            "summary": {
                "label": "Резюме",
                "type": "textarea",
                "category": "optional",
                "prompt": "Извлекай краткое резюме звонка",
                "icon": "ti-file-text",
            },
        },
        "icon": "ti-phone",
        "color": "#3B82F6",
        "is_system": True,
        "is_event": True,
        "check_duplicates": False,
        "is_filtered": True,
        "weight_coefficient": 0.9,
    },
    {
        "type_id": "email",
        "name": "Emails",
        "description": "Электронное письмо, переписка",
        "prompt": "Письмо - это электронное сообщение, email переписка.",
        "required_fields": {
            "name": {
                "label": "Тема",
                "type": "str",
                "category": "main",
                "prompt": "Извлекай тему письма",
                "icon": "ti-mail",
            }
        },
        "optional_fields": {
            "date": {
                "label": "Дата",
                "type": "date",
                "category": "main",
                "prompt": "Извлекай дату отправки письма",
                "icon": "ti-calendar",
            },
            "summary": {
                "label": "Резюме",
                "type": "textarea",
                "category": "optional",
                "prompt": "Извлекай краткое содержание письма",
                "icon": "ti-file-text",
            },
        },
        "icon": "ti-mail",
        "color": "#F59E0B",
        "is_system": True,
        "is_event": True,
        "check_duplicates": False,
        "is_filtered": True,
        "weight_coefficient": 0.9,
    },
]


class EntityTypeService:
    """
    Сервис для работы с типами сущностей.
    
    Типы делятся на:
    - Системные (is_system=True) - person, organization, project, task
    - Кастомные (company_id != None) - создаются пользователями
    
    Системные типы можно редактировать (промпты, поля), но нельзя удалять.
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
                required_fields=type_data["required_fields"],
                optional_fields=type_data["optional_fields"],
                icon=type_data["icon"],
                color=type_data["color"],
                is_system=True,
                is_event=type_data.get("is_event", False),
                weight_coefficient=type_data.get("weight_coefficient", 1.0),
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
        
        # Конвертируем FieldDefinition в dict для JSONB
        required_fields = {
            k: v.model_dump() for k, v in data.required_fields.items()
        }
        optional_fields = {
            k: v.model_dump() for k, v in data.optional_fields.items()
        }
        
        entity_type = EntityType(
            type_id=data.type_id,
            company_id=company_id,
            name=data.name,
            description=data.description,
            prompt=data.prompt,
            required_fields=required_fields,
            optional_fields=optional_fields,
            icon=data.icon,
            color=data.color,
            is_system=False,
            is_event=data.is_event,
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
        """
        Обновляет тип сущности.
        
        Системные типы можно редактировать (промпты, поля, иконки),
        но нельзя удалять или менять type_id.
        """
        company_id = company_id or self._get_company_id()
        
        entity_type = await self._repo.get_by_company(company_id, type_id)
        if not entity_type:
            return None
        
        if data.name is not None:
            entity_type.name = data.name
        if data.description is not None:
            entity_type.description = data.description
        if data.prompt is not None:
            entity_type.prompt = data.prompt
        if data.required_fields is not None:
            entity_type.required_fields = {
                k: v.model_dump() for k, v in data.required_fields.items()
            }
        if data.optional_fields is not None:
            entity_type.optional_fields = {
                k: v.model_dump() for k, v in data.optional_fields.items()
            }
        if data.icon is not None:
            entity_type.icon = data.icon
        if data.color is not None:
            entity_type.color = data.color
        if data.check_duplicates is not None:
            entity_type.check_duplicates = data.check_duplicates
        if data.is_filtered is not None:
            entity_type.is_filtered = data.is_filtered
        if data.is_event is not None:
            entity_type.is_event = data.is_event
        
        await self._repo.update(entity_type)
        logger.info(f"Обновлен тип: {type_id}")
        
        return self._to_response(entity_type)
    
    async def delete_type(
        self, 
        type_id: str,
        company_id: Optional[str] = None
    ) -> bool:
        """Удаляет кастомный тип сущности. Системные типы удалить нельзя."""
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
        # Конвертируем dict из JSONB в FieldDefinition
        required_fields = {
            k: FieldDefinition(**v) 
            for k, v in (entity_type.required_fields or {}).items()
        }
        optional_fields = {
            k: FieldDefinition(**v) 
            for k, v in (entity_type.optional_fields or {}).items()
        }
        
        return EntityTypeResponse(
            type_id=entity_type.type_id,
            company_id=entity_type.company_id,
            name=entity_type.name,
            description=entity_type.description,
            prompt=entity_type.prompt,
            required_fields=required_fields,
            optional_fields=optional_fields,
            icon=entity_type.icon,
            color=entity_type.color,
            is_system=entity_type.is_system,
            is_event=entity_type.is_event,
            check_duplicates=entity_type.check_duplicates,
            is_filtered=entity_type.is_filtered,
            created_at=entity_type.created_at,
        )
