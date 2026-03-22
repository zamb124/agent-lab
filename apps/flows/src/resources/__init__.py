"""
Resources - система ресурсов для агентов.

Resource = переиспользуемый компонент доступный нодам.
"""

from apps.flows.src.resources.resolver import ResourceResolver
from apps.flows.src.resources.wrappers import (
    CodeModule,
    RAGResource,
    LLMResource,
    HTTPResource,
    FilesResource,
    CacheResource,
    PromptResource,
)
from apps.flows.src.resources.providers import (
    BaseResourceProvider,
    CodeResourceProvider,
    RAGResourceProvider,
    LLMResourceProvider,
    HTTPResourceProvider,
    FilesResourceProvider,
    CacheResourceProvider,
    PromptResourceProvider,
    SecretResourceProvider,
)

__all__ = [
    "ResourceResolver",
    "CodeModule",
    "RAGResource",
    "LLMResource",
    "HTTPResource",
    "FilesResource",
    "CacheResource",
    "PromptResource",
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
