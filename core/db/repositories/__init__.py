"""
Core репозитории для shared сущностей.
"""

from core.db.repositories.user_repository import UserRepository
from core.db.repositories.company_repository import CompanyRepository
from core.db.repositories.auth_session_repository import AuthSessionRepository
from core.db.repositories.subdomain_repository import SubdomainRepository, SubdomainMapping
from core.db.repositories.variable_repository import VariableRepository, Variable, VariableData
from core.db.repositories.usage_repository import UsageRepository
from core.db.repositories.embed_config_repository import EmbedConfigRepository
from core.db.repositories.embed_mapping_repository import EmbedMappingRepository

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
]
