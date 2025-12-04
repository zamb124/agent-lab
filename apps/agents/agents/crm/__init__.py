"""
CRM Agents - агенты для извлечения сущностей и дедупликации.
"""

from apps.agents.agents.crm.entity_extractor_agent import EntityExtractorAgent
from apps.agents.agents.crm.entity_comparison_agent import EntityComparisonAgent

__all__ = [
    "EntityExtractorAgent",
    "EntityComparisonAgent",
]

