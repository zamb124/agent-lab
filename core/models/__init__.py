"""
Базовые модели системы, используемые в core.

Включает:
- base.py - StrictBaseModel
- identity_models.py - User, Company, AuthSession
- i18n_models.py - Language, Translation
- context_models.py - Context
- variable_models.py - VariableDefinition
"""

from core.models.base import FlexibleBaseModel, StrictBaseModel
from core.models.calendar_models import (
    CalendarAttendee,
    CalendarEvent,
    CalendarEventSource,
    CalendarEventStatus,
    CalendarEventUpsertPayload,
    CalendarExternalRef,
    CalendarIntegration,
    CalendarIntegrationConnectPayload,
    CalendarIntegrationCredentialMetadata,
    CalendarIntegrationCredentials,
    CalendarIntegrationSettings,
    CalendarProvider,
)
from core.models.context_models import Context
from core.models.i18n_models import Language
from core.models.identity_models import (
    AuthProvider,
    AuthRequest,
    AuthResult,
    AuthSession,
    Company,
    ProviderUserInfo,
    User,
    UserStatus,
)
from core.models.variable_models import VariableDefinition, VariableDefinitionInput

__all__ = [
    "StrictBaseModel",
    "FlexibleBaseModel",
    "User",
    "Company",
    "UserStatus",
    "AuthProvider",
    "AuthSession",
    "ProviderUserInfo",
    "AuthRequest",
    "AuthResult",
    "Language",
    "Context",
    "VariableDefinition",
    "VariableDefinitionInput",
    "CalendarProvider",
    "CalendarEventSource",
    "CalendarEventStatus",
    "CalendarAttendee",
    "CalendarExternalRef",
    "CalendarEvent",
    "CalendarEventUpsertPayload",
    "CalendarIntegrationCredentialMetadata",
    "CalendarIntegrationCredentials",
    "CalendarIntegrationSettings",
    "CalendarIntegration",
    "CalendarIntegrationConnectPayload",
]
