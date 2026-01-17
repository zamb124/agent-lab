"""
Resource Providers - резолвинг ресурсов.

Каждый провайдер создаёт wrapper для своего типа ресурса.
"""

from apps.agents.src.resources.providers.base import BaseResourceProvider
from apps.agents.src.resources.providers.code import CodeResourceProvider
from apps.agents.src.resources.providers.rag import RAGResourceProvider
from apps.agents.src.resources.providers.llm import LLMResourceProvider
from apps.agents.src.resources.providers.http import HTTPResourceProvider
from apps.agents.src.resources.providers.files import FilesResourceProvider
from apps.agents.src.resources.providers.cache import CacheResourceProvider
from apps.agents.src.resources.providers.prompt import PromptResourceProvider
from apps.agents.src.resources.providers.secret import SecretResourceProvider

__all__ = [
    "BaseResourceProvider",
    "CodeResourceProvider",
    "RAGResourceProvider",
    "LLMResourceProvider",
    "HTTPResourceProvider",
    "FilesResourceProvider",
    "CacheResourceProvider",
    "PromptResourceProvider",
    "SecretResourceProvider",
]
