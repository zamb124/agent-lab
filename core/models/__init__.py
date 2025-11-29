"""
Базовые модели системы, используемые в core.

Включает:
- identity_models.py - User, Company, AuthSession
- i18n_models.py - Language, Translation
- context_models.py - Context
- variable_models.py - VariableDefinition
"""

from core.models.identity_models import (
    User,
    Company,
    UserStatus,
    AuthProvider,
    AuthSession,
    ProviderUserInfo,
    AuthRequest,
    AuthResult,
)
from core.models.i18n_models import Language
from core.models.context_models import Context
from core.models.variable_models import VariableDefinition, VariableDefinitionInput

__all__ = [
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
]

