"""
Конфигурация приложения.
"""

from core.config.base import BaseSettings, get_settings, settings
from core.config.loader import load_merged_config
from core.config.models import (
    AuthConfig,
    AuthProviderConfig,
    DatabaseConfig,
    LoggingConfig,
    ServerConfig,
    S3Config,
    S3BucketConfig,
    ProxyConfig,
)

__all__ = [
    "BaseSettings",
    "get_settings",
    "settings",
    "load_merged_config",
    "AuthConfig",
    "AuthProviderConfig",
    "DatabaseConfig",
    "LoggingConfig",
    "ServerConfig",
    "S3Config",
    "S3BucketConfig",
    "ProxyConfig",
]
