"""Платформенный слой namespace: единый сервис жизненного цикла записи Namespace."""

from core.namespace.membership import ensure_personal_namespace_for_user
from core.namespace.service import (
    NamespaceService,
    infer_namespace_kind,
    personal_namespace_name,
)

__all__ = [
    "NamespaceService",
    "ensure_personal_namespace_for_user",
    "infer_namespace_kind",
    "personal_namespace_name",
]
