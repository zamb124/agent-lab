"""Нормализация фрагмента кода инлайн-tool перед валидацией и exec."""

from __future__ import annotations


def strip_forbidden_platform_import_lines(code: str) -> str:
    """
    Удаляет строки import из apps.* и core.* — в инлайн-окружении они запрещены,
    нужные имена уже в namespace (см. PythonNamespaceBuilder.build: FlowInterrupt,
    ServiceClient, ServiceClientError, RagClient, PravoClientError,
    build_catalog_search_url, fetch_catalog_search_html, parse_catalog_search_html,
    fetch_legislation_document, legislation_document_api_url,
    extract_legislation_document_hash, rag_document_id_for_pravo_legislation,
    get_context, get_operator_handoff_service,
    get_schedule_service, get_oauth_service, get_google_oauth_token,
    get_file_bytes, GoogleDocsClient, quote,
    _require_context_namespace, …).
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
