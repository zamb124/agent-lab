"""Нормализация фрагмента кода инлайн-tool перед валидацией и exec."""

from __future__ import annotations


def strip_forbidden_platform_import_lines(code: str) -> str:
    """
    Удаляет строки import из apps.* и core.* — в инлайн-окружении они запрещены,
    нужные имена уже в namespace (см. PythonNamespaceBuilder.build: FlowInterrupt,
    ServiceClient, ServiceClientError, get_context, quote, _require_context_namespace, …).
    """
    lines = code.split("\n")
    kept: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("from apps.") or stripped.startswith("from core."):
            continue
        if stripped.startswith("import apps") or stripped.startswith("import core"):
            continue
        kept.append(line)
    return "\n".join(kept)
