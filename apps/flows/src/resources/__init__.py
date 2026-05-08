"""
Resources - система ресурсов для агентов.

Resource = переиспользуемый компонент доступный нодам.
"""

from apps.flows.src.resources.resolver import ResourceResolver
from apps.flows.src.resources.wrappers import CodeModule, LLMResource, FilesResource
from apps.flows.src.resources.providers import (
    BaseResourceProvider,
    CodeResourceProvider,
    LLMResourceProvider,
    FilesResourceProvider,
)

__all__ = [
    "ResourceResolver",
    "CodeModule",
    "LLMResource",
    "FilesResource",
    "BaseResourceProvider",
    "CodeResourceProvider",
    "LLMResourceProvider",
    "FilesResourceProvider",
]
