"""
Слой внешних интеграций CRM (коннекторы по namespace, не ядро сущностей).
"""

from apps.crm.integrations.registry import IntegrationRegistry

__all__ = ["IntegrationRegistry"]
