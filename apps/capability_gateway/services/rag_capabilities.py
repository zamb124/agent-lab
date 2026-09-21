"""RAG SDK capabilities: definitions + RagClient invoke helper."""

from __future__ import annotations

from typing import TypeAlias

from pydantic import BaseModel, ValidationError

from core.capabilities import CAPABILITY_LANGUAGES, CapabilityDefinition
from core.clients.rag_client import RagClient
from core.clients.rag_models import (
    RagAddTextArgs,
    RagCreateNamespaceArgs,
    RagDeleteNamespaceArgs,
    RagDocumentIdArgs,
    RagDocumentIdsArgs,
    RagEmptyArgs,
    RagGlobalSearchArgs,
    RagIndexFileArgs,
    RagNamespaceDocumentArgs,
    RagSearchArgs,
)
from core.clients.service_client import ServiceClientError
from core.rag.models import RAGMetadata, RAGMetadataFilter
from core.types import JsonObject, JsonValue, require_json_object

RagArgsModel: TypeAlias = type[BaseModel]

_RAG_OUTPUT_SCHEMA: JsonObject = {
    "type": "object",
    "description": "JSON from RagClient (product-level fields, no HTTP envelope).",
}


def _input_schema(model: RagArgsModel) -> JsonObject:
    return require_json_object(model.model_json_schema(), f"{model.__name__}.json_schema")


def _definition(
    *,
    method: str,
    title: str,
    description: str,
    args_model: RagArgsModel,
) -> CapabilityDefinition:
    return CapabilityDefinition(
        name=f"rag.{method}",
        title=title,
        description=description,
        input_schema=_input_schema(args_model),
        output_schema=_RAG_OUTPUT_SCHEMA,
        languages=list(CAPABILITY_LANGUAGES),
        tags=["rag", "knowledge"],
        sdk_namespace="rag",
        sdk_method=method,
    )


RAG_CAPABILITY_SPECS: tuple[tuple[str, str, str, RagArgsModel], ...] = (
    (
        "create_namespace",
        "Create RAG namespace",
        "Registers a RAG namespace in the active company.",
        RagCreateNamespaceArgs,
    ),
    (
        "ingest_text",
        "Ingest text into RAG",
        "Indexes text as one document. collection_id is required and written to metadata.",
        RagAddTextArgs,
    ),
    (
        "index_file",
        "Index a platform file into RAG",
        "Indexes an existing file_id into a namespace.",
        RagIndexFileArgs,
    ),
    (
        "delete_namespace_document",
        "Delete RAG namespace document",
        "Deletes a document from a namespace.",
        RagNamespaceDocumentArgs,
    ),
    (
        "delete_document_index",
        "Delete RAG document index",
        "Deletes the vector index for a document without removing the file.",
        RagNamespaceDocumentArgs,
    ),
    (
        "delete_namespace",
        "Delete RAG namespace",
        "Deletes a RAG namespace.",
        RagDeleteNamespaceArgs,
    ),
    (
        "get_document_processing_status",
        "Get RAG document processing status",
        "Returns indexing status for one document_id.",
        RagDocumentIdArgs,
    ),
    (
        "get_documents_processing_statuses",
        "Get RAG document processing statuses",
        "Batch indexing statuses; missing document_id maps to null.",
        RagDocumentIdsArgs,
    ),
    (
        "get_search_defaults",
        "Get RAG search defaults",
        "Returns platform retrieval defaults.",
        RagEmptyArgs,
    ),
    (
        "get_namespace_document_content",
        "Get RAG document content",
        "Returns stored document content for a namespace document_id.",
        RagNamespaceDocumentArgs,
    ),
    (
        "search",
        "Search RAG namespace",
        "Semantic search. collection_id is required and merged into filters.",
        RagSearchArgs,
    ),
    (
        "global_search",
        "Search across RAG namespaces",
        "Semantic search over several namespace_ids.",
        RagGlobalSearchArgs,
    ),
)


def rag_capability_definitions() -> dict[str, CapabilityDefinition]:
    return {
        f"rag.{method}": _definition(
            method=method,
            title=title,
            description=description,
            args_model=args_model,
        )
        for method, title, description, args_model in RAG_CAPABILITY_SPECS
    }


def rag_args_model_for(method: str) -> RagArgsModel:
    for spec_method, _title, _description, args_model in RAG_CAPABILITY_SPECS:
        if spec_method == method:
            return args_model
    raise ValueError(f"Unknown rag capability method: {method}")


RAG_CLIENT_METHOD_NAMES: frozenset[str] = frozenset(spec[0] for spec in RAG_CAPABILITY_SPECS)


def _merge_collection_id(metadata: RAGMetadata | None, collection_id: str) -> RAGMetadata:
    merged: RAGMetadata = dict(metadata) if metadata is not None else {}
    existing = merged.get("collection_id")
    if existing is not None and existing != collection_id:
        raise ValueError("metadata.collection_id does not match the collection_id argument")
    merged["collection_id"] = collection_id
    return merged


def _merge_collection_filter(
    filters: RAGMetadataFilter | None, collection_id: str
) -> RAGMetadataFilter:
    merged: RAGMetadataFilter = dict(filters) if filters is not None else {}
    existing = merged.get("collection_id")
    if existing is not None and existing != collection_id:
        raise ValueError("filters.collection_id does not match the collection_id argument")
    merged["collection_id"] = collection_id
    return merged


def _dump_model(value: BaseModel, *, operation: str) -> JsonObject:
    return require_json_object(value.model_dump(mode="json"), operation)


async def _rag_method_call(method: str, args: BaseModel) -> JsonValue:
    client = RagClient()
    if method == "create_namespace" and isinstance(args, RagCreateNamespaceArgs):
        return await client.create_namespace(
            args.name,
            args.description,
            provider=args.provider,
        )
    if method == "ingest_text" and isinstance(args, RagAddTextArgs):
        ingested = await client.ingest_text(
            args.namespace_id,
            args.text,
            document_name=args.document_name,
            metadata=_merge_collection_id(args.metadata, args.collection_id),
            document_id=args.document_id,
            provider=args.provider,
        )
        return _dump_model(ingested, operation="rag.ingest_text")
    if method == "index_file" and isinstance(args, RagIndexFileArgs):
        return await client.index_file(
            args.namespace_id,
            args.file_id,
            metadata=args.metadata,
            document_name=args.document_name,
            provider=args.provider,
        )
    if method == "delete_namespace_document" and isinstance(args, RagNamespaceDocumentArgs):
        return await client.delete_namespace_document(
            args.namespace_id,
            args.document_id,
            provider=args.provider,
        )
    if method == "delete_document_index" and isinstance(args, RagNamespaceDocumentArgs):
        return await client.delete_document_index(
            args.namespace_id,
            args.document_id,
            provider=args.provider,
        )
    if method == "delete_namespace" and isinstance(args, RagDeleteNamespaceArgs):
        return await client.delete_namespace(args.namespace_id, provider=args.provider)
    if method == "get_document_processing_status" and isinstance(args, RagDocumentIdArgs):
        return await client.get_document_processing_status(args.document_id)
    if method == "get_documents_processing_statuses" and isinstance(args, RagDocumentIdsArgs):
        statuses = await client.get_documents_processing_statuses(args.document_ids)
        return require_json_object({"statuses": statuses}, "rag.get_documents_processing_statuses")
    if method == "get_search_defaults" and isinstance(args, RagEmptyArgs):
        return _dump_model(await client.get_search_defaults(), operation="rag.get_search_defaults")
    if method == "get_namespace_document_content" and isinstance(args, RagNamespaceDocumentArgs):
        content = await client.get_namespace_document_content(
            args.namespace_id,
            args.document_id,
            provider=args.provider,
        )
        return _dump_model(content, operation="rag.get_namespace_document_content")
    if method == "search" and isinstance(args, RagSearchArgs):
        return await client.search(
            args.namespace_id,
            args.query,
            limit=args.limit,
            filters=_merge_collection_filter(args.filters, args.collection_id),
            provider=args.provider,
            channels=args.channels,
            rrf_k=args.rrf_k,
            per_channel_top_k=args.per_channel_top_k,
            rerank=args.rerank,
            rerank_max_candidates=args.rerank_max_candidates,
            retrieval=args.retrieval,
            freshness_weight=args.freshness_weight,
            freshness_half_life_days=args.freshness_half_life_days,
        )
    if method == "global_search" and isinstance(args, RagGlobalSearchArgs):
        return await client.global_search(
            args.namespace_ids,
            args.query,
            limit=args.limit,
            provider=args.provider,
            filters=args.filters,
            channels=args.channels,
            rrf_k=args.rrf_k,
            per_channel_top_k=args.per_channel_top_k,
            rerank=args.rerank,
            rerank_max_candidates=args.rerank_max_candidates,
            retrieval=args.retrieval,
            freshness_weight=args.freshness_weight,
            freshness_half_life_days=args.freshness_half_life_days,
        )
    raise ValueError(f"Unsupported rag capability invoke: {method}")


async def invoke_rag_client(method: str, kwargs: JsonObject) -> JsonValue:
    """Parse kwargs with the method's model and call RagClient (Context must be active)."""
    args_model = rag_args_model_for(method)
    try:
        args = args_model.model_validate(kwargs)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
    try:
        return await _rag_method_call(method, args)
    except ServiceClientError as exc:
        raise ValueError(str(exc)) from exc
