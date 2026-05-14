"""
Identity - система аутентификации и авторизации.
"""

from core.identity.auth_service import AuthService
from core.identity.base_provider import BaseAuthProvider
from core.identity.providers.apple import AppleProvider
from core.identity.providers.github import GithubProvider
from core.identity.providers.google import GoogleProvider
from core.identity.providers.yandex import YandexProvider
from core.models.identity_models import AuthProvider, AuthSession, Company, User

__all__ = [
    "AuthService",
    "BaseAuthProvider",
    "YandexProvider",
    "GoogleProvider",
    "GithubProvider",
    "AppleProvider",
    "User",
    "Company",
    "AuthProvider",
    "AuthSession",
]
