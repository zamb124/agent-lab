"""Обход дерева Documents для исходников code_agent."""

from __future__ import annotations

from core.clients.documents_client import DocumentsClient
from core.guest_runtime.models import CodeAgentSourceFile
from core.types import require_json_object


async def walk_code_agent_catalog(
    documents: DocumentsClient,
    catalog_id: str,
    *,
    relative_dir: str = "",
) -> list[CodeAgentSourceFile]:
    if not catalog_id.strip():
        raise ValueError("catalog_id required")
    payload = await documents.list_catalog_items(catalog_id)
    documents_raw = payload.get("documents")
    catalogs_raw = payload.get("catalogs")
    if not isinstance(documents_raw, list):
        raise ValueError("catalog items.documents required")
    if not isinstance(catalogs_raw, list):
        raise ValueError("catalog items.catalogs required")
    files: list[CodeAgentSourceFile] = []
    for raw_doc in documents_raw:
        document = require_json_object(raw_doc, "catalog.documents[]")
        title = document.get("title")
        file_id = document.get("file_id")
        file_size = document.get("file_size")
        if not isinstance(title, str) or title.strip() == "":
            raise ValueError("document title required")
        if not isinstance(file_id, str) or file_id.strip() == "":
            raise ValueError("document file_id required")
        if not isinstance(file_size, int):
            raise ValueError("document file_size required")
        relative_path = f"{relative_dir}/{title}" if relative_dir else title
        files.append(
            CodeAgentSourceFile(
                file_id=file_id,
                relative_path=relative_path,
                file_size=file_size,
            )
        )
    for raw_catalog in catalogs_raw:
        catalog = require_json_object(raw_catalog, "catalog.catalogs[]")
        child_id = catalog.get("catalog_id")
        title = catalog.get("title")
        if not isinstance(child_id, str) or child_id.strip() == "":
            raise ValueError("child catalog_id required")
        if not isinstance(title, str) or title.strip() == "":
            raise ValueError("child catalog title required")
        child_dir = f"{relative_dir}/{title}" if relative_dir else title
        files.extend(
            await walk_code_agent_catalog(documents, child_id, relative_dir=child_dir)
        )
    return files
