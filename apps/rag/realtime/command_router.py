"""Регистрация WS command-handler'ов rag в `core.websocket`."""

from __future__ import annotations

from apps.rag.di import RagDi
from apps.rag.models import DocumentStatusesBatchRequest
from apps.rag.realtime.operations import (
    RagDocumentRefPayload,
    RagDocumentsListPayload,
    RagDocumentStatusPayload,
    RagGlobalSearchPayload,
    RagIndexFilePayload,
    RagIngestTextPayload,
    RagNamespaceCreatePayload,
    RagNamespaceDeletePayload,
    RagNamespaceSearchPayload,
    op_documents_content,
    op_documents_index_file,
    op_documents_index_remove,
    op_documents_ingest_text,
    op_documents_list,
    op_documents_remove,
    op_documents_status,
    op_documents_statuses,
    op_namespaces_create,
    op_namespaces_remove,
    op_providers_list,
    op_search_defaults,
    op_search_global,
    op_search_namespace,
)
from core.namespace.operations import NamespacesListPayload, op_namespaces_list
from core.websocket import EmptyPayload, Operation, RegisteredOperation

RAG_OPERATIONS: dict[str, RegisteredOperation[RagDi]] = {
    "rag/namespaces/list_requested": Operation(
        payload_model=NamespacesListPayload, fn=op_namespaces_list
    ),
    "rag/namespaces/create_requested": Operation(
        payload_model=RagNamespaceCreatePayload, fn=op_namespaces_create
    ),
    "rag/namespaces/remove_requested": Operation(
        payload_model=RagNamespaceDeletePayload, fn=op_namespaces_remove
    ),
    "rag/documents/list_requested": Operation(
        payload_model=RagDocumentsListPayload, fn=op_documents_list
    ),
    "rag/documents/ingest_text_requested": Operation(
        payload_model=RagIngestTextPayload, fn=op_documents_ingest_text
    ),
    "rag/documents/index_file_requested": Operation(
        payload_model=RagIndexFilePayload, fn=op_documents_index_file
    ),
    "rag/documents/remove_requested": Operation(
        payload_model=RagDocumentRefPayload, fn=op_documents_remove
    ),
    "rag/documents/index_remove_requested": Operation(
        payload_model=RagDocumentRefPayload, fn=op_documents_index_remove
    ),
    "rag/documents/content_requested": Operation(
        payload_model=RagDocumentRefPayload, fn=op_documents_content
    ),
    "rag/documents/status_requested": Operation(
        payload_model=RagDocumentStatusPayload, fn=op_documents_status
    ),
    "rag/documents/statuses_requested": Operation(
        payload_model=DocumentStatusesBatchRequest, fn=op_documents_statuses
    ),
    "rag/search/defaults_requested": Operation(
        payload_model=EmptyPayload, fn=op_search_defaults
    ),
    "rag/search/namespace_requested": Operation(
        payload_model=RagNamespaceSearchPayload, fn=op_search_namespace
    ),
    "rag/search/global_requested": Operation(
        payload_model=RagGlobalSearchPayload, fn=op_search_global
    ),
    "rag/providers/list_requested": Operation(
        payload_model=EmptyPayload, fn=op_providers_list
    ),
}
