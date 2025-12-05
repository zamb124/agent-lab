"""
CRM Entity Extractor Flow - извлечение сущностей из текста для CRM.

Вызывается из CRM Service через API:
POST /agents/api/v1/flows/crm_entity_extractor/message
"""

from apps.agents.models import FlowConfig


# Flow конфигурация для CRM Entity Extractor
crm_entity_extractor_flow_config = FlowConfig(
    flow_id="crm_entity_extractor",
    name="CRM Entity Extractor",
    description="Извлекает сущности (люди, организации, проекты) из текста заметок",
    entry_point_agent="apps.agents.agents.crm.entity_extractor_agent.EntityExtractorAgent",
    platforms={"api": {}},
    is_public=False,
)

# Flow для сравнения сущностей
crm_entity_comparison_flow_config = FlowConfig(
    flow_id="crm_entity_comparison",
    name="CRM Entity Comparison",
    description="Сравнивает сущности для определения дубликатов",
    entry_point_agent="apps.agents.agents.crm.entity_comparison_agent.EntityComparisonAgent",
    platforms={"api": {}},
    is_public=False,
)

