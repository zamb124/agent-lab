"""
Базовые модели системы, используемые в core.

Включает:
- base.py - StrictBaseModel
- identity_models.py - User, Company, AuthSession
- i18n_models.py - Language, Translation
- context_models.py - Context
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
    AuthCodeCache,
    AuthProvider,
    AuthRequest,
    AuthResult,
    AuthSession,
    AuthState,
    Company,
    ProviderUserInfo,
    User,
    UserProviderRecord,
    UserStatus,
)
from core.models.voice_models import VADSegment

__all__ = [
    "StrictBaseModel",
    "FlexibleBaseModel",
    "User",
    "Company",
    "UserStatus",
    "AuthProvider",
    "AuthSession",
    "ProviderUserInfo",
    "UserProviderRecord",
    "AuthRequest",
    "AuthState",
    "AuthCodeCache",
    "AuthResult",
    "Language",
    "Context",
    "VADSegment",
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
