"""
Конфигурация Secrets Service.

URL БД переменных: settings.database.secrets_url.
Ключ шифрования: settings.secrets.encryption_key.
"""

from core.config import BaseSettings


class SecretsSettings(BaseSettings):
    """Настройки сервиса версионируемых переменных и секретов."""
