"""
Resource Providers - резолвинг ресурсов.

Каждый провайдер создаёт wrapper для своего типа ресурса.
"""

from apps.flows.src.resources.providers.base import BaseResourceProvider
from apps.flows.src.resources.providers.code import CodeResourceProvider
from apps.flows.src.resources.providers.files import FilesResourceProvider
from apps.flows.src.resources.providers.llm import LLMResourceProvider

__all__ = [
    "BaseResourceProvider",
    "CodeResourceProvider",
    "LLMResourceProvider",
    "FilesResourceProvider",
]
