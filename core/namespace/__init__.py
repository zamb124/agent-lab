"""Платформенный слой namespace: единый сервис жизненного цикла записи Namespace."""

from core.namespace.membership import ensure_personal_namespace_for_user
from core.namespace.service import (
    TECHNICAL_NAMESPACE_NAME_PREFIXES,
    NamespaceService,
    infer_namespace_kind,
    personal_namespace_name,
)

__all__ = [
    "TECHNICAL_NAMESPACE_NAME_PREFIXES",
    "NamespaceService",
    "ensure_personal_namespace_for_user",
    "infer_namespace_kind",
    "personal_namespace_name",
]
