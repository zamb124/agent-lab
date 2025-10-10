"""
Провайдеры авторизации.
"""

from .yandex import YandexProvider
from .google import GoogleProvider

__all__ = ["YandexProvider", "GoogleProvider"]

