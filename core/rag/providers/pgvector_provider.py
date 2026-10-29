"""
RAG провайдер на базе pgvector (PostgreSQL).
Чанки лежат в ``vector_documents``. Косинус и FTS читаются сырым SQL.
"""

import math
import uuid
from datetime import datetime, timezone
from typing import Literal, override

from core.ai.embedding_client import AIEmbeddingClient
from core.ai.runtime import create_embedding_client_from_runtime
from core.config import get_settings
from core.config.llm_openai_compat import (
    llm_provider_block,
    yandex_provider_http_headers,
)
from core.config.models import RAGProviderConfig, YandexLLMProviderConfig
from core.config.testing import is_testing
from core.db.models.rag import VectorDocument
from core.files.file_ref import FileRef
from core.files.reader import FileReader, ReadFileArgs
from core.files.reader.models import (
    ContentMode,
    FileExtract,
    FileReadKind,
    PageLayout,
    PageLayoutKind,
    ReadLane,
    UniversalPage,
)
from core.logging import get_logger
from core.rag.base_provider import BaseRAGProvider, validate_metadata_filters
from core.rag.chunking import resolve_split_config, split_file_extract
from core.rag.embedding_runtime import RagEmbeddingRuntime
from core.rag.models import (
    RAGChunk,
    RAGDocument,
    RAGDocumentContent,
    RAGMetadata,
    RAGMetadataFilter,
    RAGNamespace,
    RAGSearchOptions,
    RAGSearchResult,
)
from core.rag.rrf import reciprocal_rank_fusion
from core.rag.ttl import ensure_ttl_seconds_in_metadata
from core.rag.upload_profile_binding import UploadProfileBinding
from core.rag_indexing_schema import IndexProfileConfig, IndexProfileSplitConfig
from core.types import JsonObject, JsonValue, require_json_object

logger = get_logger(__name__)
# Значения из шаблонного conf.json — не отправлять в OpenRouter как ключ
_EMBEDDING_API_KEY_PLACEHOLDERS: frozenset[str] = frozenset(
    {
        "YOUR_EMBEDDING_API_KEY",
        "YOUR_OPENROUTER_API_KEY",
    }
)

# Конфигурация текстового поиска lexical-канала. Должна совпадать с конфигом
# generated column ``vector_documents.content_tsv`` (миграция rag_0006):
# ``russian`` стеммит и русские (Snowball), и ascii-слова (english_stem).
LEXICAL_TS_CONFIG = "russian"
TS_HEADLINE_OPTIONS = (
    'StartSel=**, StopSel=**, MaxFragments=2, MaxWords=25, MinWords=8, FragmentDelimiter=" … "'
)
# Для evergreen-контента freshness decay ослабляется: half-life растягивается.
FRESHNESS_EVERGREEN_HALF_LIFE_FACTOR = 4.0

_SqlParam = str | int | float | bool | datetime | None

def _kept_by_score_desc(entries: list[RAGSearchResult]) -> list[RAGSearchResult]:
    """Кандидаты поиска, score DESC."""
    entries.sort(key=lambda entry: entry.score, reverse=True)
    return entries


def _pairs_by_score_desc(scored: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """Пары (id, score), score DESC."""
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored


class _Binder:
    """Нумерация параметров сырого SQL с уже занятым префиксом."""

    def __init__(self, start: int) -> None:
        self.params: list[_SqlParam] = []
        self._next: int = start

    def add(self, value: _SqlParam) -> str:
        self._next += 1
        self.params.append(value)
        return f"${self._next}"

    def next_index(self) -> int:
        return self._next + 1


def _metadata_cast(placeholder: str, value: JsonValue) -> str:
    if isinstance(value, bool):
        return f"(metadata->>{placeholder})::boolean"
    if isinstance(value, int):
        return f"(metadata->>{placeholder})::integer"
    if isinstance(value, float):
        return f"(metadata->>{placeholder})::double precision"
    return f"(metadata->>{placeholder})::text"


def _metadata_compare(binder: _Binder, key: str, value: JsonValue, operator: str) -> str:
    if not isinstance(value, (str, int, float, bool)) and value is not None:
        raise ValueError("RAG filters: compared value must be a scalar")
    key_placeholder = binder.add(key)
    expression = _metadata_cast(key_placeholder, value)
    value_placeholder = binder.add(value)
    return f"{expression} {operator} {value_placeholder}"


def _metadata_filter_sql(binder: _Binder, node: RAGMetadataFilter) -> str:
    if "$and" in node:
        and_items = node["$and"]
        if not isinstance(and_items, list):
            raise ValueError("RAG filters: $and must be an array of conditions")
        parts = [
            _metadata_filter_sql(binder, require_json_object(item, "RAG filters $and item"))
            for item in and_items
        ]
        return "(" + " AND ".join(parts) + ")"
    if "$or" in node:
        or_items = node["$or"]
        if not isinstance(or_items, list):
            raise ValueError("RAG filters: $or must be an array of conditions")
        parts = [
            _metadata_filter_sql(binder, require_json_object(item, "RAG filters $or item"))
            for item in or_items
        ]
        return "(" + " OR ".join(parts) + ")"
    parts: list[str] = []
    for key, value in node.items():
        if isinstance(value, dict):
            operator, op_value = next(iter(value.items()))
            parts.append(_metadata_operator_sql(binder, key, str(operator), op_value))
            continue
        parts.append(_metadata_compare(binder, key, value, "="))
    if not parts:
        raise ValueError("RAG filters: empty condition")
    return "(" + " AND ".join(parts) + ")"


def _metadata_operator_sql(binder: _Binder, key: str, operator: str, op_value: JsonValue) -> str:
    if operator == "$eq":
        return _metadata_compare(binder, key, op_value, "=")
    if operator == "$ne":
        return _metadata_compare(binder, key, op_value, "<>")
    if operator in {"$in", "$nin"}:
        if not isinstance(op_value, list) or len(op_value) == 0:
            raise ValueError(f"RAG filters: {operator} requires a non-empty value list for key {key!r}")
        joiner = " OR " if operator == "$in" else " AND "
        comparator = "=" if operator == "$in" else "<>"
        return (
            "("
            + joiner.join(_metadata_compare(binder, key, item, comparator) for item in op_value)
            + ")"
        )
    if operator not in {"$gt", "$gte", "$lt", "$lte"}:
        raise ValueError(f"RAG filters: unsupported operator {operator}")
    if isinstance(op_value, bool) or not isinstance(op_value, (int, float)):
        raise ValueError(f"RAG filters: {key}.{operator} supports only number")
    symbol = {"$gt": ">", "$gte": ">=", "$lt": "<", "$lte": "<="}[operator]
    number = int(op_value) if isinstance(op_value, int) else float(op_value)
    return _metadata_compare(binder, key, number, symbol)


_SEARCH_ATTRIBUTE_SKIP_KEYS: frozenset[str] = frozenset(
    {
        "page_index",
        "page_label",
        "heading_trail",
        "files",
        "split",
        "indexing_runtime",
        "document_id",
        "document_name",
        "chunk_index",
        "total_chunks",
    }
)


def _resolve_index_document_id(metadata: RAGMetadata) -> str:
    document_id_raw = metadata.get("document_id")
    document_id = str(document_id_raw).strip() if document_id_raw else ""
    if document_id:
        return document_id
    return str(uuid.uuid4())


def _chunk_storage_metadata(
    *,
    ingest: RAGMetadata,
    chunk: RAGChunk,
    indexing_runtime: RAGMetadata,
) -> RAGMetadata:
    files_payload: list[JsonObject] = [
        require_json_object(file_ref.model_dump(mode="json"), "RAGChunk.files item")
        for file_ref in chunk.files
    ]
    stored: RAGMetadata = dict(ingest)
    stored["page_index"] = chunk.page_index
    stored["page_label"] = chunk.page_label
    if chunk.heading_trail:
        stored["heading_trail"] = list(chunk.heading_trail)
    else:
        stored["heading_trail"] = _heading_trail_from_metadata(ingest.get("heading_trail"))
    stored["files"] = files_payload
    stored["split"] = require_json_object(
        chunk.split.model_dump(mode="json"),
        "RAGChunk.split",
    )
    stored["indexing_runtime"] = indexing_runtime
    stored["document_id"] = chunk.document_id
    stored["document_name"] = chunk.document_name
    stored["chunk_index"] = chunk.chunk_index
    stored["total_chunks"] = chunk.total_chunks
    return stored


def _optional_int(value: JsonValue | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError('page_index in chunk metadata must be int or null')
    return value


def _optional_label(value: JsonValue | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError('page_label in chunk metadata must be str or null')
    stripped = value.strip()
    if not stripped:
        return None
    return stripped


def _heading_trail_from_metadata(value: JsonValue | None) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError('heading_trail in chunk metadata must be a list of strings')
    trail: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError('heading_trail in chunk metadata must be a list of strings')
        trail.append(item)
    return trail


def _files_from_metadata(value: JsonValue | None) -> list[FileRef]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError('files in chunk metadata must be a list of FileRef')
    return [FileRef.model_validate(item) for item in value]


def _split_from_metadata(value: JsonValue | None) -> IndexProfileSplitConfig:
    if value is None:
        return IndexProfileSplitConfig()
    return IndexProfileSplitConfig.model_validate(value)


def _search_attributes(metadata: RAGMetadata) -> JsonObject:
    attributes: JsonObject = {}
    for key, item in metadata.items():
        if key in _SEARCH_ATTRIBUTE_SKIP_KEYS:
            continue
        attributes[key] = item
    return attributes


def _rag_search_result_from_document(
    doc: VectorDocument,
    *,
    score: float,
    namespace_id: str,
    provenance: RAGMetadata,
) -> RAGSearchResult:
    metadata = doc.metadata
    return RAGSearchResult(
        content=doc.content,
        document_id=doc.document_id,
        document_name=doc.document_name or "",
        namespace=namespace_id,
        chunk_index=doc.chunk_index,
        total_chunks=doc.total_chunks,
        page_index=_optional_int(metadata.get("page_index")),
        page_label=_optional_label(metadata.get("page_label")),
        heading_trail=_heading_trail_from_metadata(metadata.get("heading_trail")),
        files=_files_from_metadata(metadata.get("files")),
        split=_split_from_metadata(metadata.get("split")),
        attributes=_search_attributes(metadata),
        score=score,
        chunk_id=doc.id,
        provenance=provenance,
    )


def _parse_metadata_document_date(metadata: RAGMetadata, key: str) -> datetime | None:
    """ISO-дата из metadata краулера; metadata — внешняя граница, битая дата → None."""
    raw_value = metadata.get(key)
    if not isinstance(raw_value, str) or not raw_value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(raw_value.strip())
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _document_freshness_age_days(doc: VectorDocument, *, now: datetime) -> tuple[float, str]:
    """
    Возраст документа в днях для freshness decay.

    Приоритет: ``metadata.date_modified`` → ``metadata.date_published`` →
    ``vector_documents.created_at`` (дата индексации, есть всегда).
    """
    metadata = doc.metadata
    for key in ("date_modified", "date_published"):
        parsed = _parse_metadata_document_date(metadata, key)
        if parsed is not None:
            return max(0.0, (now - parsed).total_seconds() / 86400.0), key
    created_at = doc.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return max(0.0, (now - created_at).total_seconds() / 86400.0), "created_at"


def _freshness_multiplier(*, age_days: float, half_life_days: float, weight: float) -> float:
    """``(1 - weight) + weight * 0.5 ** (age / half_life)`` — множитель в (1-weight, 1]."""
    decay = math.pow(0.5, age_days / half_life_days)
    return (1.0 - weight) + weight * decay


def _freshness_score_and_provenance(
    doc: VectorDocument,
    base_score: float,
    *,
    weight: float,
    half_life_days: float,
    now: datetime,
) -> tuple[float, RAGMetadata]:
    """Итоговый score с freshness decay и provenance-поля — единый расчёт для всех каналов."""
    age_days, age_source = _document_freshness_age_days(doc, now=now)
    effective_half_life = half_life_days
    metadata = doc.metadata
    if metadata.get("freshness_relevance") == "evergreen":
        effective_half_life *= FRESHNESS_EVERGREEN_HALF_LIFE_FACTOR
    multiplier = _freshness_multiplier(
        age_days=age_days,
        half_life_days=effective_half_life,
        weight=weight,
    )
    freshness_provenance: RAGMetadata = {
        "freshness_multiplier": round(multiplier, 6),
        "freshness_age_days": round(age_days, 2),
        "freshness_age_source": age_source,
    }
    return base_score * multiplier, freshness_provenance


def _normalize_embedding_api_key(raw: str | None) -> str:
    if raw is None:
        return ""
    s = str(raw).strip()
    if not s or s in _EMBEDDING_API_KEY_PLACEHOLDERS:
        return ""
    return s


def deterministic_embeddings_enabled() -> bool:
    """Тестовый контур или rag.embedding.mock: клиент без внешнего embedding API."""
    return is_testing() or get_settings().rag.embedding.mock


class PgVectorProvider(BaseRAGProvider):
    """
    RAG провайдер на базе pgvector.
    Использует PostgreSQL + pgvector для хранения и поиска векторных документов.
    """

    def __init__(
        self,
        config: RAGProviderConfig,
        embedding_runtime: RagEmbeddingRuntime | None = None,
    ) -> None:
        super().__init__(config)

        rag_url = config.db_url
        if rag_url is None or rag_url == "":
            rag_url = get_settings().database.rag_url
        if rag_url is None or rag_url == "":
            raise ValueError("DATABASE__RAG_URL is not configured")

        if embedding_runtime is None:
            raise ValueError('embedding runtime is required for pgvector')
        api_key = _normalize_embedding_api_key(config.embedding_api_key) or None

        timeout = config.timeout

        model = embedding_runtime.model
        dimension = embedding_runtime.dimension
        embedding_base_url = embedding_runtime.base_url
        mrl_output_dimension = embedding_runtime.mrl_output_dimension

        if not model:
            raise ValueError('embedding.model is required in configuration')
        if not dimension:
            raise ValueError('embedding.dimension is required in configuration')

        embedding_extra_headers = dict(embedding_runtime.extra_request_headers or {})
        root_for_yandex_check = (embedding_base_url or "").strip()
        if embedding_runtime.provider == "yandex" or "llm.api.cloud.yandex.net" in root_for_yandex_check:
            yc_raw = llm_provider_block(get_settings().llm, "yandex")
            if not isinstance(yc_raw, YandexLLMProviderConfig):
                raise ValueError(
                    'Embedding provider/base_url points to Yandex: set the llm.yandex block '
                    + "(api_key, folder_id)."
                )
            embedding_extra_headers = {
                **yandex_provider_http_headers(yc_raw),
                **embedding_extra_headers,
            }

        use_deterministic_embeddings = deterministic_embeddings_enabled()
        self._embedding_client: AIEmbeddingClient = create_embedding_client_from_runtime(
            provider=embedding_runtime.provider,
            model=model,
            base_url=embedding_base_url or None,
            api_key=api_key,
            timeout=timeout,
            dimension=dimension,
            mrl_output_dimension=mrl_output_dimension,
            extra_headers=embedding_extra_headers or None,
            deterministic=use_deterministic_embeddings,
        )
        if use_deterministic_embeddings:
            logger.info("rag.pgvector.mock.embeddings")

        query_instruction = embedding_runtime.query_instruction
        self._query_instruction: str | None = (
            query_instruction.strip()
            if query_instruction is not None and query_instruction.strip()
            else None
        )

        self._file_reader: FileReader = FileReader()

        logger.info("rag.pgvector.initialized", model=model, dimension=dimension)

    @property
    @override
    def provider_name(self) -> str:
        return "pgvector"

    @override
    async def close(self) -> None:
        return

    @property
    def embedding_client(self) -> AIEmbeddingClient:
        """Embedding client pgvector for background orchestrators."""
        return self._embedding_client

    def embedding_model_name(self) -> str:
        """Идентификатор текущей модели эмбеддинга для записи в embedding_model."""
        return self._embedding_client.model

    def _query_embedding_text(self, query: str) -> str:
        """
        Asymmetric instruct-префикс для запроса (Qwen3-Embedding и совместимые модели).

        Документы индексируются без префикса; запрос оборачивается в
        ``Instruct: {task}\\nQuery: {query}``, если в ``rag.embedding.api.query_instruction``
        задана инструкция.
        """
        if self._query_instruction is None:
            return query
        return f"Instruct: {self._query_instruction}\nQuery: {query}"

    # — Пространства имён —

    @override
    async def create_namespace(
        self, name: str, description: str | None = None
    ) -> RAGNamespace:
        """Namespace -- логическое понятие, фильтр по namespace_id."""
        count = await VectorDocument.count_rows_for_namespace(name)
        return RAGNamespace(
            namespace_id=name,
            name=name,
            description=description,
            document_count=count,
        )

    @override
    async def get_namespace(self, namespace_id: str) -> RAGNamespace | None:
        count = await VectorDocument.count_rows_for_namespace(namespace_id)
        if count == 0:
            return None

        return RAGNamespace(
            namespace_id=namespace_id,
            name=namespace_id,
            document_count=count,
        )

    @override
    async def list_namespaces(self) -> list[RAGNamespace]:
        namespaces: list[RAGNamespace] = []
        for row_namespace_id, chunk_count in await VectorDocument.chunk_counts_by_namespace():
            namespaces.append(
                RAGNamespace(
                    namespace_id=row_namespace_id,
                    name=row_namespace_id,
                    document_count=chunk_count,
                )
            )
        return namespaces

    @override
    async def delete_namespace(self, namespace_id: str) -> bool:
        deleted = await VectorDocument.delete_by_namespace(namespace_id)

        logger.info("rag.pgvector.namespace_deleted", namespace_id=namespace_id, deleted=deleted)
        return deleted > 0

    # — Загрузка документов —

    @override
    async def upload_document_from_file(
        self,
        namespace_id: str,
        file_path: str,
        document_name: str | None = None,
        metadata: RAGMetadata | None = None,
    ) -> RAGDocument:
        stored = await self._upload_file_to_s3(file_path, namespace_id, public=False)
        original_filename = stored.original_name

        doc_name = document_name or original_filename

        doc_metadata = dict(metadata) if metadata is not None else {}
        document_id = _resolve_index_document_id(doc_metadata)
        doc_metadata["document_id"] = document_id
        read_args = ReadFileArgs(page_end=-1, persist_assets_namespace=namespace_id)
        extract = await self._file_reader.read(
            file_path,
            read_args,
            file_name=doc_name,
            file_id=document_id,
        )
        doc_metadata["file_type"] = extract.kind.value
        doc_metadata["file_id"] = stored.file_id
        doc_metadata["original_filename"] = original_filename
        if extract.source_checksum:
            doc_metadata["source_checksum"] = extract.source_checksum

        return await self._upload_file_extract_internal(
            namespace_id=namespace_id,
            extract=extract,
            document_name=doc_name,
            metadata=doc_metadata,
        )

    @override
    async def upload_document_from_s3(
        self,
        namespace_id: str,
        s3_key: str,
        document_name: str | None = None,
        metadata: RAGMetadata | None = None,
        *,
        upload_profile: UploadProfileBinding | None = None,
    ) -> RAGDocument:
        doc_metadata = dict(metadata) if metadata is not None else {}
        bucket_key = doc_metadata.get("storage_id")
        if bucket_key is not None and not isinstance(bucket_key, str):
            raise ValueError('metadata.storage_id must be a string')
        file_data, bucket_name, original_filename = await self._download_file_from_s3(
            s3_key, bucket_config_key=bucket_key
        )

        filename = document_name or original_filename

        doc_metadata = dict(metadata) if metadata is not None else {}
        document_id = _resolve_index_document_id(doc_metadata)
        doc_metadata["document_id"] = document_id
        read_args = ReadFileArgs(page_end=-1, persist_assets_namespace=namespace_id)
        extract = await self._file_reader.read(
            file_data,
            read_args,
            file_name=filename,
            file_id=document_id,
        )
        doc_metadata["file_type"] = extract.kind.value
        doc_metadata["s3_key"] = s3_key
        doc_metadata["storage_id"] = bucket_name
        doc_metadata["original_filename"] = original_filename
        if extract.source_checksum:
            doc_metadata["source_checksum"] = extract.source_checksum

        logger.info("rag.pgvector.s3_index_started", s3_key=s3_key)
        return await self._upload_file_extract_internal(
            namespace_id=namespace_id,
            extract=extract,
            document_name=filename,
            metadata=doc_metadata,
            upload_profile=upload_profile,
        )

    @override
    async def upload_document_from_text(
        self,
        namespace_id: str,
        text: str,
        document_name: str | None = None,
        metadata: RAGMetadata | None = None,
    ) -> RAGDocument:
        doc_name = document_name or f"text_{uuid.uuid4().hex[:8]}"

        doc_metadata = dict(metadata) if metadata is not None else {}
        doc_metadata["file_type"] = "text"

        return await self._upload_text_internal(
            namespace_id=namespace_id,
            text_content=text,
            document_name=doc_name,
            metadata=doc_metadata,
        )

    async def _upload_file_extract_internal(
        self,
        namespace_id: str,
        extract: FileExtract,
        document_name: str,
        metadata: RAGMetadata,
        upload_profile: UploadProfileBinding | None = None,
    ) -> RAGDocument:
        """Chunk + embed из канонического FileExtract."""
        md = dict(metadata)
        document_id_raw = md.get("document_id")
        document_id = str(document_id_raw).strip() if document_id_raw else ""
        if not document_id:
            document_id = str(uuid.uuid4())
        md["document_id"] = document_id

        metadata = ensure_ttl_seconds_in_metadata(
            md,
            default_ttl_seconds=get_settings().rag.ttl.default_ttl_seconds,
        )
        index_profile_config = metadata.get("index_profile_config")
        if index_profile_config is None and upload_profile is not None:
            index_profile_config = require_json_object(
                upload_profile.config.model_dump(mode="json", exclude_none=True),
                "upload_profile.config",
            )
            metadata["index_profile_config"] = index_profile_config

        if index_profile_config is not None and not isinstance(index_profile_config, dict):
            raise ValueError('index_profile_config must be an object')
        if index_profile_config is None:
            profile = get_settings().rag.document_indexing
        else:
            profile = IndexProfileConfig.model_validate(index_profile_config)
        split_config = resolve_split_config(extract, profile)
        rag_chunks = split_file_extract(
            extract,
            split_config,
            document_id=document_id,
            document_name=document_name,
            namespace=namespace_id,
        )
        if not rag_chunks:
            raise ValueError(
                f"No text to index after FileReader (empty pages). file={document_name}"
            )
        chunks = [chunk.content for chunk in rag_chunks]
        indexing_runtime: RAGMetadata = dict(
            require_json_object(
                profile.model_dump(mode="json"),
                "index profile",
            )
        )

        try:
            raw_embeddings = await self._embedding_client.generate_embeddings(chunks)
            embeddings: list[list[float] | None] = list(raw_embeddings)
            embedding_tokens = self._embedding_client.count_tokens(chunks)
            embedding_model: str | None = self.embedding_model_name()
            indexing_runtime["embedding"] = require_json_object(
                self._embedding_client.runtime_snapshot(embedding_tokens=embedding_tokens),
                "embedding runtime",
            )
        except Exception as exc:
            logger.warning(
                "rag.pgvector.embedding_unavailable",
                document_name=document_name,
                namespace_id=namespace_id,
                error=str(exc),
            )
            embeddings = [None] * len(chunks)
            embedding_model = None
            indexing_runtime["embedding"] = {"pending": True, "error": str(exc)[:200]}

        company_id_value = metadata.get("company_id")
        if company_id_value is not None and not isinstance(company_id_value, str):
            raise ValueError('metadata.company_id must be a string')

        now = datetime.now(timezone.utc)
        rows: list[VectorDocument] = []
        for i, (chunk, emb) in enumerate(zip(rag_chunks, embeddings)):
            chunk_row_id = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"rag://{namespace_id}/{document_id}/{i}",
            ).hex
            rows.append(
                VectorDocument(
                    id=chunk_row_id,
                    namespace_id=namespace_id,
                    company_id=company_id_value,
                    document_id=document_id,
                    document_name=document_name,
                    content=chunk.content,
                    embedding=emb,
                    embedding_model=embedding_model,
                    chunk_index=chunk.chunk_index,
                    total_chunks=chunk.total_chunks,
                    metadata=_chunk_storage_metadata(
                        ingest=metadata,
                        chunk=chunk,
                        indexing_runtime=indexing_runtime,
                    ),
                    created_at=now,
                    updated_at=now,
                )
            )

        deleted_count = await VectorDocument.replace_chunks(rows)
        if deleted_count:
            logger.info(
                "rag.pgvector.stale_chunks_deleted",
                document_name=document_name,
                deleted_count=deleted_count,
            )

        logger.info("rag.pgvector.document_uploaded", document_name=document_name, namespace_id=namespace_id, chunk_count=len(chunks))
        merged_doc_meta = {
            **metadata,
            "indexing_runtime": indexing_runtime,
            "total_chunks": len(chunks),
        }
        return RAGDocument(
            document_id=document_id,
            name=document_name,
            namespace=namespace_id,
            status="completed",
            metadata=merged_doc_meta,
        )

    async def _upload_text_internal(
        self,
        namespace_id: str,
        text_content: str,
        document_name: str,
        metadata: RAGMetadata,
    ) -> RAGDocument:
        """Прямой текст (без файла): одна логическая страница в FileExtract."""
        extract = FileExtract(
            file_name=document_name,
            kind=FileReadKind.TEXT,
            mime_type="text/plain",
            read_lane=ReadLane.TEXT,
            page_layout=PageLayout(kind=PageLayoutKind.VIRTUAL, pages_total=1, page_size=0),
            pages=[
                UniversalPage(
                    index=0,
                    label="",
                    text=text_content,
                    content_mode=ContentMode.FULL,
                )
            ],
            content_chars_total=len(text_content),
            warnings=[],
        )
        return await self._upload_file_extract_internal(
            namespace_id=namespace_id,
            extract=extract,
            document_name=document_name,
            metadata=metadata,
        )

    # — CRUD документов —

    @override
    async def get_document(self, namespace_id: str, document_id: str) -> RAGDocument | None:
        loaded = await VectorDocument.list_for_namespace_and_document_by_chunk_index_asc(namespace_id, document_id, limit=1)
        if len(loaded) == 0:
            return None
        row = loaded[0]
        return RAGDocument(
            document_id=document_id,
            name=row.document_name or "",
            namespace=namespace_id,
            status="completed",
            metadata=row.metadata,
        )

    @override
    async def get_document_content(
        self,
        namespace_id: str,
        document_id: str,
    ) -> RAGDocumentContent | None:
        rows = await VectorDocument.list_for_namespace_and_document_by_chunk_index_asc(namespace_id, document_id)
        if not rows:
            return None
        first_row = rows[0]
        document_name = first_row.document_name or ""
        metadata = dict(first_row.metadata)
        for key in ("document_id", "document_name", "chunk_index", "total_chunks"):
            if key in metadata:
                del metadata[key]
        markdown_parts: list[str] = []
        for row in rows:
            if row.content.strip():
                markdown_parts.append(row.content.strip())
        markdown = "\n\n".join(markdown_parts)
        if not markdown.strip():
            raise ValueError(
                f"document content is empty: namespace_id={namespace_id}, document_id={document_id}"
            )
        return RAGDocumentContent(
            document_id=document_id,
            document_name=document_name,
            markdown=markdown,
            chunks_count=len(rows),
            metadata=metadata,
        )

    @override
    async def list_documents(self, namespace_id: str, limit: int = 100) -> list[RAGDocument]:
        rows = await VectorDocument.any_chunk_rows_by_document_id_asc(namespace_id, limit=limit)
        docs: list[RAGDocument] = []
        for row in rows:
            meta = row.metadata
            docs.append(
                RAGDocument(
                    document_id=row.document_id,
                    name=row.document_name or "",
                    namespace=namespace_id,
                    status="completed",
                    metadata={
                        k: v
                        for k, v in meta.items()
                        if k not in ("document_id", "document_name", "chunk_index", "total_chunks")
                    },
                )
            )
        return docs

    @override
    async def list_documents_with_filters(
        self, namespace_id: str, where: RAGMetadataFilter | None = None, limit: int = 100
    ) -> list[RAGDocument]:
        binder = _Binder(1)
        filter_sql = ""
        if where is not None:
            validate_metadata_filters(where)
            filter_sql = " AND " + _metadata_filter_sql(binder, where)
        loaded = await VectorDocument.any_chunk_rows_by_document_id_where_asc(
            namespace_id,
            filter_sql=filter_sql,
            filter_params=binder.params,
            limit=limit,
            limit_placeholder=binder.next_index(),
        )
        docs: list[RAGDocument] = []
        for row in loaded:
            meta = row.metadata
            docs.append(
                RAGDocument(
                    document_id=row.document_id,
                    name=row.document_name or "",
                    namespace=namespace_id,
                    status="completed",
                    metadata={
                        key: value
                        for key, value in meta.items()
                        if key not in ("document_id", "document_name", "chunk_index", "total_chunks")
                    },
                )
            )
        logger.info("rag.pgvector.documents_listed", namespace_id=namespace_id, count=len(docs))
        return docs

    @override
    async def delete_document(self, namespace_id: str, document_id: str) -> bool:
        deleted = await VectorDocument.delete_by_namespace_and_document_id(namespace_id, document_id)
        if deleted:
            logger.info("rag.pgvector.document_deleted", document_id=document_id, deleted=deleted)
        return deleted > 0

    async def batch_document_semantic_index_status(
        self,
        keys: list[tuple[str, str, str]],
    ) -> dict[tuple[str, str, str], Literal["absent", "pending_embedding", "ready"]]:
        """Агрегат чанков по тройкам (namespace_id, document_id, company_id)."""
        if not keys:
            return {}
        unique_keys = list(dict.fromkeys(keys))
        out: dict[tuple[str, str, str], Literal["absent", "pending_embedding", "ready"]] = {
            key: "absent" for key in unique_keys
        }
        counted = await VectorDocument.chunk_and_null_count_rows(unique_keys)
        for namespace_id, document_id, company_id, chunk_count, null_chunks in counted:
            key = (namespace_id, document_id, company_id)
            if key not in out:
                continue
            if null_chunks > 0:
                out[key] = "pending_embedding"
            elif chunk_count > 0:
                out[key] = "ready"
        return out

    async def fetch_stale_chunks_for_reembed(
        self,
        *,
        limit: int,
        target_embedding_model: str,
    ) -> list[tuple[str, str, str]]:
        """Кандидаты на перевекторизацию: (id, content, company_id)."""
        return await VectorDocument.stale_id_content_company_rows_by_company_rank_asc(
            limit=limit,
            target_embedding_model=target_embedding_model,
        )

    async def write_reembed_chunk_embeddings(
        self,
        doc_embeddings: list[tuple[str, list[float]]],
        target_embedding_model: str,
    ) -> int:
        """Записывает векторы для списка (chunk_id, embedding)."""
        return await VectorDocument.update_embedding_and_model(
            doc_embeddings,
            target_embedding_model,
        )

    @override
    async def delete_orphan_company_chunks(self, *, limit: int) -> int:
        """Удаляет чанки без company_id."""
        return await VectorDocument.delete_without_company_id_by_id_asc(limit=limit)

    # — Поиск —

    @override
    async def search(
        self,
        namespace_id: str,
        query: str,
        limit: int = 5,
        filters: RAGMetadataFilter | None = None,
        search_options: RAGSearchOptions | None = None,
    ) -> list[RAGSearchResult]:
        embedding_model = self.embedding_model_name()
        channels = search_options.channels if search_options is not None else None
        use_hybrid_rrf = (
            channels is not None
            and channels.semantic
            and channels.lexical
        )

        if use_hybrid_rrf:
            if search_options is None:
                raise ValueError("hybrid search requires search_options")
            return await self._hybrid_search_rrf(
                namespace_id=namespace_id,
                query=query,
                limit=limit,
                filters=filters,
                embedding_model=embedding_model,
                rrf_k=search_options.rrf_k,
                per_channel_top_k=search_options.per_channel_top_k,
                freshness_weight=search_options.freshness_weight,
                freshness_half_life_days=search_options.freshness_half_life_days,
            )

        query_embedding = await self._embedding_client.generate_embedding(
            self._query_embedding_text(query)
        )

        freshness_weight = search_options.freshness_weight if search_options is not None else None
        freshness_half_life_days = (
            search_options.freshness_half_life_days if search_options is not None else None
        )
        freshness_enabled = (
            freshness_weight is not None
            and freshness_weight > 0.0
            and freshness_half_life_days is not None
        )
        # Freshness переранжирует расширенный пул кандидатов до среза limit —
        # тот же контракт, что в _hybrid_search_rrf.
        fetch_limit = limit * 3 if freshness_enabled else limit

        binder = _Binder(3)
        filter_sql = ""
        if filters is not None:
            validate_metadata_filters(filters)
            filter_sql = " AND " + _metadata_filter_sql(binder, filters)
        limit_placeholder = binder.next_index()
        rows = await VectorDocument.rows_with_similarity_by_distance_asc(
            namespace_id=namespace_id,
            embedding_model=embedding_model,
            query_embedding=query_embedding,
            filter_sql=filter_sql,
            filter_params=binder.params,
            limit=fetch_limit,
            limit_placeholder=limit_placeholder,
        )
        results = self._build_search_results(rows, namespace_id)
        if not freshness_enabled or freshness_weight is None or freshness_half_life_days is None:
            return results

        now = datetime.now(timezone.utc)
        docs_by_chunk_id = {doc.id: doc for doc, _similarity_score in rows}
        rescored: list[RAGSearchResult] = []
        for item in results:
            doc = docs_by_chunk_id[item.chunk_id]
            final_score, freshness_provenance = _freshness_score_and_provenance(
                doc,
                item.score,
                weight=freshness_weight,
                half_life_days=freshness_half_life_days,
                now=now,
            )
            rescored.append(
                item.model_copy(
                    update={
                        "score": final_score,
                        "provenance": {**item.provenance, **freshness_provenance},
                    }
                )
            )
        return _kept_by_score_desc(rescored)[:limit]

    async def _hybrid_search_rrf(
        self,
        *,
        namespace_id: str,
        query: str,
        limit: int,
        filters: RAGMetadataFilter | None,
        embedding_model: str,
        rrf_k: int | None = None,
        per_channel_top_k: int | None = None,
        freshness_weight: float | None = None,
        freshness_half_life_days: float | None = None,
    ) -> list[RAGSearchResult]:
        """Семантический cosine и лексический ts_rank_cd, слияние RRF."""
        query_embedding = await self._embedding_client.generate_embedding(
            self._query_embedding_text(query)
        )
        rrf_k_int = 60 if rrf_k is None else int(rrf_k)
        per_channel = limit * 3 if per_channel_top_k is None else int(per_channel_top_k)
        freshness_enabled = (
            freshness_weight is not None
            and freshness_weight > 0.0
            and freshness_half_life_days is not None
        )
        binder = _Binder(3)
        filter_sql = ""
        if filters is not None:
            validate_metadata_filters(filters)
            filter_sql = " AND " + _metadata_filter_sql(binder, filters)
        limit_placeholder = binder.next_index()
        lexical_binder = _Binder(3)
        lexical_filter = ""
        if filters is not None:
            lexical_filter = " AND " + _metadata_filter_sql(lexical_binder, filters)
        lexical_limit = lexical_binder.next_index()
        semantic_ids, lexical_ids = await VectorDocument.semantic_by_distance_and_lexical_by_ts_rank_desc_chunk_ids(
            namespace_id=namespace_id,
            embedding_model=embedding_model,
            query_embedding=query_embedding,
            query=query,
            lexical_config=LEXICAL_TS_CONFIG,
            semantic_filter_sql=filter_sql,
            semantic_params=binder.params,
            semantic_limit_placeholder=limit_placeholder,
            lexical_filter_sql=lexical_filter,
            lexical_params=lexical_binder.params,
            lexical_limit_placeholder=lexical_limit,
            per_channel=per_channel,
        )
        fused = reciprocal_rank_fusion([semantic_ids, lexical_ids], k=rrf_k_int)
        if not fused:
            return []
        candidate_pairs = fused if freshness_enabled else fused[:limit]
        candidate_ids = [doc_id for doc_id, _score in candidate_pairs]
        by_id = await VectorDocument.found_by_ids(candidate_ids)
        scored: list[tuple[str, float]] = []
        now = datetime.now(timezone.utc)
        freshness_provenance: dict[str, RAGMetadata] = {}
        for doc_id, rrf_score in candidate_pairs:
            doc = by_id.get(doc_id)
            if doc is None:
                continue
            final_score = float(rrf_score)
            if freshness_enabled and freshness_weight is not None and freshness_half_life_days is not None:
                final_score, freshness_provenance[doc_id] = _freshness_score_and_provenance(
                    doc,
                    final_score,
                    weight=freshness_weight,
                    half_life_days=freshness_half_life_days,
                    now=now,
                )
            scored.append((doc_id, final_score))
        scored = _pairs_by_score_desc(scored)
        top = scored[:limit]
        top_ids = [doc_id for doc_id, _score in top]
        if not top_ids:
            return []
        headline_by_id = await VectorDocument.stripped_headlines_by_id(
            doc_ids=top_ids,
            query=query,
            lexical_config=LEXICAL_TS_CONFIG,
            headline_options=TS_HEADLINE_OPTIONS,
        )
        ordered: list[RAGSearchResult] = []
        for doc_id, final_score in top:
            doc = by_id.get(doc_id)
            if doc is None:
                continue
            provenance: RAGMetadata = {"channel": "hybrid_rrf", "rrf_k": rrf_k_int}
            if doc_id in freshness_provenance:
                provenance.update(freshness_provenance[doc_id])
            headline = headline_by_id.get(doc_id)
            if headline is not None:
                provenance["headline"] = headline
            ordered.append(
                _rag_search_result_from_document(
                    doc,
                    score=final_score,
                    namespace_id=namespace_id,
                    provenance=provenance,
                )
            )
        return ordered

    def _build_search_results(
        self,
        rows: list[tuple[VectorDocument, float]],
        namespace_id: str,
    ) -> list[RAGSearchResult]:
        return [
            _rag_search_result_from_document(
                doc,
                score=score,
                namespace_id=namespace_id,
                provenance={},
            )
            for doc, score in rows
        ]
