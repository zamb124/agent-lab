"""
Дополнения optional_fields канонических типов при подключении AmoCRM к namespace.

Один источник правды для merge optional_fields при подготовке namespace интеграцией (OAuth / ensure_namespace_ready).
"""

from __future__ import annotations

from apps.crm.integrations.amocrm.mapping import (
    AMO_USERS_ENTITY_TYPE_ID,
    ENTITY_TYPE_BY_AMO_COLLECTION,
)
from core.types import JsonObject

AMO_OPTIONAL_FIELD_EXTERNAL_REFS: JsonObject = {
    "type": "external_refs",
    "label": "Внешние ссылки",
    "description": (
        "Связи с записями во внешних системах; идемпотентность импорта — по record_id в разрезе провайдера."
    ),
}

LEAD_AMO_OPTIONAL_FIELDS: JsonObject = {
    "source": {"type": "string", "label": "Источник"},
    "stage": {"type": "string", "label": "Стадия"},
    "budget": {"type": "number", "label": "Бюджет"},
    "price": {"type": "number", "label": "Бюджет (amo)"},
    "status_id": {"type": "integer", "label": "status_id"},
    "pipeline_id": {"type": "integer", "label": "pipeline_id"},
    "external_refs": dict(AMO_OPTIONAL_FIELD_EXTERNAL_REFS),
}

ORGANIZATION_AMO_OPTIONAL_FIELDS: JsonObject = {
    "name": {"type": "string", "label": "Название"},
    "industry": {"type": "string", "label": "Отрасль"},
    "legal_name": {"type": "string", "label": "Юридическое название"},
    "external_refs": dict(AMO_OPTIONAL_FIELD_EXTERNAL_REFS),
}

CONTACT_AMO_OPTIONAL_FIELDS: JsonObject = {
    "display_name": {"type": "string", "label": "Имя"},
    "role": {"type": "string", "label": "Роль"},
    "aliases": {"type": "array", "label": "Псевдонимы"},
    "first_name": {"type": "string", "label": "Имя"},
    "last_name": {"type": "string", "label": "Фамилия"},
    "external_refs": dict(AMO_OPTIONAL_FIELD_EXTERNAL_REFS),
}

MEMBER_AMO_OPTIONAL_FIELDS: JsonObject = {
    "aliases": {"type": "array", "label": "Псевдонимы"},
    "email": {"type": "string", "label": "Email"},
    "is_active": {"type": "boolean", "label": "Активен"},
    "external_refs": dict(AMO_OPTIONAL_FIELD_EXTERNAL_REFS),
}

TASK_AMO_OPTIONAL_FIELDS: JsonObject = {
    "title": {"type": "string", "label": "Название задачи"},
    "amo_task_type_id": {"type": "integer", "label": "Amo task_type_id"},
    "amo_task_type_name": {"type": "string", "label": "Тип задачи Amo"},
    "amo_is_completed": {"type": "boolean", "label": "Завершена в Amo"},
    "amo_result_text": {"type": "string", "label": "Результат (Amo)"},
    "external_refs": dict(AMO_OPTIONAL_FIELD_EXTERNAL_REFS),
}

AMO_OPTIONAL_FIELDS_BY_TYPE_ID: dict[str, JsonObject] = {
    "lead": LEAD_AMO_OPTIONAL_FIELDS,
    "contact": CONTACT_AMO_OPTIONAL_FIELDS,
    "organization": ORGANIZATION_AMO_OPTIONAL_FIELDS,
    "member": MEMBER_AMO_OPTIONAL_FIELDS,
    "task": TASK_AMO_OPTIONAL_FIELDS,
}


def amo_canonical_type_ids() -> frozenset[str]:
    return frozenset({*ENTITY_TYPE_BY_AMO_COLLECTION.values(), AMO_USERS_ENTITY_TYPE_ID, "task"})
