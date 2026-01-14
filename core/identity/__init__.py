"""
Identity - система аутентификации и авторизации.
"""

from core.identity.auth_service import AuthService
from core.identity.base_provider import BaseAuthProvider
from core.identity.providers.yandex import YandexProvider
from core.identity.providers.google import GoogleProvider
from core.identity.providers.github import GithubProvider
from core.models.identity_models import User, Company, AuthProvider, AuthSession

__all__ = [
    "AuthService",
    "BaseAuthProvider",
    "YandexProvider",
    "GoogleProvider",
    "GithubProvider",
    "User",
    "Company",
    "AuthProvider",
    "AuthSession",
]
