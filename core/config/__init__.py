"""
Конфигурация приложения.
"""

from core.config.base import BaseSettings, get_settings, set_settings, settings
from core.config.loader import load_merged_config
from core.config.models import (
    AuthConfig,
    AuthProviderConfig,
    DatabaseConfig,
    LoggingConfig,
    ServerConfig,
    ProxyConfig,
    OpenAIProviderConfig,
    OpenRouterProviderConfig,
    BothubProviderConfig,
    ModelConfig,
    LLMConfig,
    S3BucketConfig,
    S3Config,
)

__all__ = [
    "BaseSettings",
    "get_settings",
    "set_settings",
    "settings",
    "load_merged_config",
    "AuthConfig",
    "AuthProviderConfig",
    "DatabaseConfig",
    "LoggingConfig",
    "ServerConfig",
    "ProxyConfig",
    "OpenAIProviderConfig",
    "OpenRouterProviderConfig",
    "BothubProviderConfig",
    "ModelConfig",
    "LLMConfig",
    "S3BucketConfig",
    "S3Config",
]
