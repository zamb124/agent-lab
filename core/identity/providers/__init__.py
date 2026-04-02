"""
OAuth провайдеры авторизации.
"""

from core.identity.providers.yandex import YandexProvider
from core.identity.providers.google import GoogleProvider
from core.identity.providers.github import GithubProvider
from core.identity.providers.apple import AppleProvider

__all__ = [
    "YandexProvider",
    "GoogleProvider",
    "GithubProvider",
    "AppleProvider",
]













