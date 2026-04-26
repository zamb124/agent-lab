"""
Соответствие коллекций AmoCRM API v4 каноническим type_id в NetWorkle.

type_id задаются шаблоном пространства (см. system_templates template_id amocrm);
коннектор только маппит endpoint провайдера на эти идентификаторы.
"""

from __future__ import annotations

# Должен совпадать с AmoCRMConnector.provider_id — ключ attributes.external_refs[source_id].
AMO_PROVIDER_ID = "amocrm"

ENTITY_TYPE_BY_AMO_COLLECTION: dict[str, str] = {
    "leads": "lead",
    "contacts": "contact",
    "companies": "organization",
}

# Пользователи /api/v4/users — отдельный entity_type от contact, чтобы не совпадал record_id с контактом.
AMO_USERS_ENTITY_TYPE_ID = "member"
