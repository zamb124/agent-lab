"""
Дополнения optional_fields канонических типов при подключении AmoCRM к namespace.

Один источник правды для merge при OAuth и для шаблона amocrm в system_templates.
"""

from __future__ import annotations

from typing import Any

from apps.crm.integrations.amocrm.mapping import (
    AMO_USERS_ENTITY_TYPE_ID,
    ENTITY_TYPE_BY_AMO_COLLECTION,
)

LEAD_AMO_OPTIONAL_FIELDS: dict[str, Any] = {
    "source": {"type": "string", "label": "Источник"},
    "stage": {"type": "string", "label": "Стадия"},
    "budget": {"type": "number", "label": "Бюджет"},
    "price": {"type": "number", "label": "Бюджет (amo)"},
    "status_id": {"type": "integer", "label": "status_id"},
    "pipeline_id": {"type": "integer", "label": "pipeline_id"},
}

CONTACT_AMO_OPTIONAL_FIELDS: dict[str, Any] = {
    "display_name": {"type": "string", "label": "Имя"},
    "role": {"type": "string", "label": "Роль"},
    "aliases": {"type": "array", "label": "Псевдонимы"},
    "first_name": {"type": "string", "label": "Имя"},
    "last_name": {"type": "string", "label": "Фамилия"},
}

MEMBER_AMO_OPTIONAL_FIELDS: dict[str, Any] = {
    "aliases": {"type": "array", "label": "Псевдонимы"},
    "email": {"type": "string", "label": "Email"},
    "is_active": {"type": "boolean", "label": "Активен"},
}

TASK_AMO_OPTIONAL_FIELDS: dict[str, Any] = {
    "title": {"type": "string", "label": "Название задачи"},
    "due_date": {"type": "date", "label": "Срок"},
    "priority": {"type": "enum", "values": ["low", "medium", "high", "urgent"]},
    "status": {
        "type": "enum",
        "values": ["todo", "in_progress", "done"],
        "label": "Статус",
    },
    "amo_task_type_id": {"type": "integer", "label": "Amo task_type_id"},
    "amo_task_type_name": {"type": "string", "label": "Тип задачи Amo"},
    "amo_is_completed": {"type": "boolean", "label": "Завершена в Amo"},
    "amo_result_text": {"type": "string", "label": "Результат (Amo)"},
}

AMO_OPTIONAL_FIELDS_BY_TYPE_ID: dict[str, dict[str, Any]] = {
    "lead": LEAD_AMO_OPTIONAL_FIELDS,
    "contact": CONTACT_AMO_OPTIONAL_FIELDS,
    "member": MEMBER_AMO_OPTIONAL_FIELDS,
    "task": TASK_AMO_OPTIONAL_FIELDS,
}


def amo_canonical_type_ids() -> frozenset[str]:
    return frozenset(
        {*ENTITY_TYPE_BY_AMO_COLLECTION.values(), AMO_USERS_ENTITY_TYPE_ID, "task"}
    )
