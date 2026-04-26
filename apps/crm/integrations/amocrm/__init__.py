"""Встроенная интеграция AmoCRM."""

from apps.crm.integrations.amocrm.connector import AmoCRMConnector
from apps.crm.integrations.amocrm.service import AmoCRMIntegrationService

__all__ = ["AmoCRMConnector", "AmoCRMIntegrationService"]
