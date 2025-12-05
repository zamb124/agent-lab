"""
CRM Agents - агенты для извлечения сущностей и работы с CRM.
"""

from apps.agents.agents.crm.entity_extractor_agent import EntityExtractorAgent
from apps.agents.agents.crm.entity_comparison_agent import EntityComparisonAgent
from apps.agents.agents.crm.crm_assistant_agent import CRMAssistantAgent

__all__ = [
    "EntityExtractorAgent",
    "EntityComparisonAgent",
    "CRMAssistantAgent",
]


