"""
Core репозитории для shared сущностей.
"""

from core.db.repositories.auth_session_repository import AuthSessionRepository
from core.db.repositories.company_repository import CompanyRepository
from core.db.repositories.company_voice_provider_repository import (
    CompanyVoiceProviderRepository,
    VoiceKind,
)
from core.db.repositories.embed_config_repository import EmbedConfigRepository
from core.db.repositories.embed_mapping_repository import EmbedMappingRepository
from core.db.repositories.subdomain_repository import SubdomainMapping, SubdomainRepository
from core.db.repositories.usage_repository import UsageRepository
from core.db.repositories.user_repository import UserRepository
from core.db.repositories.variable_repository import Variable, VariableData, VariableRepository

__all__ = [
    "UserRepository",
    "CompanyRepository",
    "AuthSessionRepository",
    "SubdomainRepository",
    "SubdomainMapping",
    "VariableRepository",
    "Variable",
    "VariableData",
    "UsageRepository",
    "EmbedConfigRepository",
    "EmbedMappingRepository",
    "CompanyVoiceProviderRepository",
    "VoiceKind",
]
