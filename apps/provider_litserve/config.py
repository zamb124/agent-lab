"""
Настройки процессов ``apps/provider_litserve`` (локальные модели эмбеддинга/реранка): общий ``conf.json``
+ ``services.provider_litserve``. Порты и воркеры: ``provider_litserve.infra``; публичный URL клиентов RAG: ``provider_litserve.api``.
"""

from __future__ import annotations

from typing import Optional

from core.config import BaseSettings
from core.config.loader import load_merged_config

_provider_litserve_settings: Optional[BaseSettings] = None


def get_provider_litserve_settings() -> BaseSettings:
    global _provider_litserve_settings
    if _provider_litserve_settings is None:
        merged = load_merged_config(service_name="provider_litserve")
        _provider_litserve_settings = BaseSettings(**merged)
    return _provider_litserve_settings
