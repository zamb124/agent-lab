"""
RAG провайдер на базе pgvector (PostgreSQL).
Хранит векторные документы в таблице vector_documents через SQLAlchemy 2+.
"""

import math
import os
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Literal, override

from sqlalchemy import (
    Boolean,
    Float,
    Integer,
    String,
    and_,
    case,
    delete,
    func,
    or_,
    select,
    text,
    tuple_,
    update,
)
from sqlalchemy import cast as sql_cast
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.sql.elements import ColumnElement

from core.ai.embedding_client import AIEmbeddingClient
from core.ai.runtime import create_embedding_client_from_runtime
from core.config import get_settings
from core.config.llm_openai_compat import (
    llm_provider_block,
    yandex_provider_http_headers,
)
from core.config.models import RAGProviderConfig, YandexLLMProviderConfig
from core.config.testing import is_testing
from core.db.models import VectorDocument
from core.db.sqlalchemy_pool import sqlalchemy_async_engine_pool_kwargs
from core.db.utils import get_rowcount
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
    metadata = doc.metadata_ or {}
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
    metadata = doc.metadata_ or {}
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
    metadata = doc.metadata_ or {}
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

        db_url = config.db_url
        if not db_url:
            settings = get_settings()
            if not settings.database.rag_url:
                raise ValueError('DATABASE__RAG_URL is not configured')
            db_url = settings.database.rag_url

        self._engine: AsyncEngine = create_async_engine(
            db_url,
            echo=False,
            **sqlalchemy_async_engine_pool_kwargs(),
        )
        self._session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

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

        use_deterministic_embeddings = (
            is_testing()
            or os.environ.get("RAG__EMBEDDING__MOCK") == "true"
            or os.environ.get("PGVECTOR_TEST_MOCK_EMBEDDINGS") == "true"
        )
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
        await self._engine.dispose()

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
        async with self._session_factory() as session:
            stmt = (
                select(func.count())
                .select_from(VectorDocument)
                .where(VectorDocument.namespace_id == name)
            )
            result = await session.execute(stmt)
            count = result.scalar() or 0

        return RAGNamespace(
            namespace_id=name,
            name=name,
            description=description,
            document_count=count,
        )

    @override
    async def get_namespace(self, namespace_id: str) -> RAGNamespace | None:
        async with self._session_factory() as session:
            stmt = (
                select(func.count())
                .select_from(VectorDocument)
                .where(VectorDocument.namespace_id == namespace_id)
            )
            result = await session.execute(stmt)
            count = result.scalar() or 0

        if count == 0:
            return None

        return RAGNamespace(
            namespace_id=namespace_id,
            name=namespace_id,
            document_count=count,
        )

    @override
    async def list_namespaces(self) -> list[RAGNamespace]:
        async with self._session_factory() as session:
            stmt = select(
                VectorDocument.namespace_id,
                func.count().label("doc_count"),
            ).group_by(VectorDocument.namespace_id)
            result = await session.execute(stmt)
            rows: Sequence[tuple[str, int]] = result.tuples().all()

        return [
            RAGNamespace(
                namespace_id=row_namespace_id,
                name=row_namespace_id,
                document_count=doc_count,
            )
            for row_namespace_id, doc_count in rows
        ]

    @override
    async def delete_namespace(self, namespace_id: str) -> bool:
        async with self._session_factory() as session:
            stmt = delete(VectorDocument).where(VectorDocument.namespace_id == namespace_id)
            result = await session.execute(stmt)
            await session.commit()
            deleted = get_rowcount(result)

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
        s3_key, bucket_name, original_filename = await self._upload_file_to_s3(
            file_path, namespace_id, public=False
        )

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
        doc_metadata["s3_key"] = s3_key
        doc_metadata["s3_bucket"] = bucket_name
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
        bucket_key = doc_metadata.get("s3_bucket")
        if bucket_key is not None and not isinstance(bucket_key, str):
            raise ValueError('metadata.s3_bucket must be a string')
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
        doc_metadata["s3_bucket"] = bucket_name
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
                    metadata_=_chunk_storage_metadata(
                        ingest=metadata,
                        chunk=chunk,
                        indexing_runtime=indexing_runtime,
                    ),
                )
            )

        async with self._session_factory() as session:
            _ = await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                {"lock_key": f"{namespace_id}:{document_id}"},
            )
            delete_stmt = delete(VectorDocument).where(
                VectorDocument.namespace_id == namespace_id,
                VectorDocument.document_id == document_id,
            )
            delete_result = await session.execute(delete_stmt)
            deleted_count = get_rowcount(delete_result)
            if deleted_count:
                logger.info("rag.pgvector.stale_chunks_deleted", document_name=document_name, deleted_count=deleted_count)
            session.add_all(rows)
            await session.commit()

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
        async with self._session_factory() as session:
            stmt = (
                select(VectorDocument)
                .where(
                    VectorDocument.namespace_id == namespace_id,
                    VectorDocument.document_id == document_id,
                )
                .limit(1)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()

        if not row:
            return None

        return RAGDocument(
            document_id=document_id,
            name=row.document_name or "",
            namespace=namespace_id,
            status="completed",
            metadata=row.metadata_ or {},
        )

    @override
    async def get_document_content(
        self,
        namespace_id: str,
        document_id: str,
    ) -> RAGDocumentContent | None:
        async with self._session_factory() as session:
            stmt = (
                select(VectorDocument)
                .where(
                    VectorDocument.namespace_id == namespace_id,
                    VectorDocument.document_id == document_id,
                )
                .order_by(VectorDocument.chunk_index.asc())
            )
            rows = list((await session.execute(stmt)).scalars().all())
        if not rows:
            return None
        first_row = rows[0]
        document_name = first_row.document_name or ""
        metadata = dict(first_row.metadata_ or {})
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
        async with self._session_factory() as session:
            stmt = (
                select(VectorDocument)
                .where(VectorDocument.namespace_id == namespace_id)
                .distinct(VectorDocument.document_id)
                .limit(limit)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()

        docs: list[RAGDocument] = []
        for row in rows:
            meta = row.metadata_
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
        async with self._session_factory() as session:
            stmt = (
                select(VectorDocument)
                .where(VectorDocument.namespace_id == namespace_id)
                .distinct(VectorDocument.document_id)
            )

            if where:
                stmt = stmt.where(self._build_metadata_filter_expression(where))

            stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            rows = result.scalars().all()

        docs: list[RAGDocument] = []
        for row in rows:
            meta = row.metadata_
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

        logger.info("rag.pgvector.documents_listed", namespace_id=namespace_id, count=len(docs))
        return docs

    def _metadata_expr_for_scalar(
        self,
        key: str,
        value: JsonValue,
    ) -> ColumnElement[bool] | ColumnElement[int] | ColumnElement[float] | ColumnElement[str]:
        metadata_value = VectorDocument.metadata_.op("->>")(key)
        if isinstance(value, bool):
            return sql_cast(metadata_value, Boolean)
        if isinstance(value, int) and not isinstance(value, bool):
            return sql_cast(metadata_value, Integer)
        if isinstance(value, float):
            return sql_cast(metadata_value, Float)
        return sql_cast(metadata_value, String)

    def _build_field_operator_expression(
        self, key: str, operator: str, op_value: JsonValue
    ) -> ColumnElement[bool]:
        if operator == "$eq":
            return self._metadata_expr_for_scalar(key, op_value) == op_value
        if operator == "$ne":
            return self._metadata_expr_for_scalar(key, op_value) != op_value

        if operator == "$in":
            if not isinstance(op_value, list) or len(op_value) == 0:
                raise ValueError(
                    f"RAG filters: $in requires a non-empty value list for key {key!r}",
                )
            vals = op_value
            if len(vals) == 1:
                v0 = vals[0]
                return self._metadata_expr_for_scalar(key, v0) == v0
            in_expressions: list[ColumnElement[bool]] = [
                self._metadata_expr_for_scalar(key, value) == value for value in vals
            ]
            return or_(*in_expressions)
        if operator == "$nin":
            if not isinstance(op_value, list) or len(op_value) == 0:
                raise ValueError(
                    f"RAG filters: $nin requires a non-empty value list for key {key!r}",
                )
            vals = op_value
            if len(vals) == 1:
                v0 = vals[0]
                return self._metadata_expr_for_scalar(key, v0) != v0
            nin_expressions: list[ColumnElement[bool]] = [
                self._metadata_expr_for_scalar(key, value) != value for value in vals
            ]
            return and_(*nin_expressions)

        if isinstance(op_value, int) and not isinstance(op_value, bool):
            col_int = sql_cast(VectorDocument.metadata_.op("->>")(key), Integer)
            if operator == "$gt":
                return col_int > op_value
            if operator == "$gte":
                return col_int >= op_value
            if operator == "$lt":
                return col_int < op_value
            if operator == "$lte":
                return col_int <= op_value
        if not isinstance(op_value, (int, float)) or isinstance(op_value, bool):
            raise ValueError(
                f"RAG filters: {key}.{operator} supports only number"
            )
        fv = float(op_value)
        if operator == "$gt":
            return self._metadata_expr_for_scalar(key, fv) > fv
        if operator == "$gte":
            return self._metadata_expr_for_scalar(key, fv) >= fv
        if operator == "$lt":
            return self._metadata_expr_for_scalar(key, fv) < fv
        if operator == "$lte":
            return self._metadata_expr_for_scalar(key, fv) <= fv

        raise ValueError(f"RAG filters: unsupported operator {operator}")

    def _build_metadata_filter_expression(self, filters: RAGMetadataFilter) -> ColumnElement[bool]:
        validate_metadata_filters(filters)
        return self._build_metadata_filter_node(filters)

    def _build_metadata_filter_node(self, node: RAGMetadataFilter) -> ColumnElement[bool]:
        if "$and" in node:
            and_items = node["$and"]
            if not isinstance(and_items, list):
                raise ValueError('RAG filters: $and must be an array of conditions')
            and_expressions: list[ColumnElement[bool]] = [
                self._build_metadata_filter_node(
                    require_json_object(item, "RAG filters $and item")
                )
                for item in and_items
            ]
            return and_(*and_expressions)
        if "$or" in node:
            or_items = node["$or"]
            if not isinstance(or_items, list):
                raise ValueError('RAG filters: $or must be an array of conditions')
            or_expressions: list[ColumnElement[bool]] = [
                self._build_metadata_filter_node(
                    require_json_object(item, "RAG filters $or item")
                )
                for item in or_items
            ]
            return or_(*or_expressions)

        expressions: list[ColumnElement[bool]] = []
        for key, value in node.items():
            if isinstance(value, dict):
                op, op_value = next(iter(value.items()))
                expressions.append(self._build_field_operator_expression(key, op, op_value))
                continue
            expressions.append(self._metadata_expr_for_scalar(key, value) == value)
        return and_(*expressions)

    @override
    async def delete_document(self, namespace_id: str, document_id: str) -> bool:
        async with self._session_factory() as session:
            stmt = delete(VectorDocument).where(
                VectorDocument.namespace_id == namespace_id,
                VectorDocument.document_id == document_id,
            )
            result = await session.execute(stmt)
            await session.commit()
            deleted = get_rowcount(result)

        if deleted:
            logger.info("rag.pgvector.document_deleted", document_id=document_id, deleted=deleted)
        return deleted > 0

    async def batch_document_semantic_index_status(
        self,
        keys: list[tuple[str, str, str]],
    ) -> dict[tuple[str, str, str], Literal["absent", "pending_embedding", "ready"]]:
        """
        Агрегат по chunk-ам vector_documents для троек ``(namespace_id, document_id, company_id)``.

        - ``absent`` — нет строк.
        - ``pending_embedding`` — есть строка с ``embedding IS NULL``.
        - ``ready`` — есть строки, все с непустым ``embedding``.
        """
        if not keys:
            return {}
        unique_keys = list(dict.fromkeys(keys))
        out: dict[tuple[str, str, str], Literal["absent", "pending_embedding", "ready"]] = {
            k: "absent" for k in unique_keys
        }

        null_chunks_expr = func.coalesce(
            func.sum(case((VectorDocument.embedding.is_(None), 1), else_=0)),
            0,
        ).label("null_chunks")
        chunk_count = func.count().label("chunk_count")

        stmt = (
            select(
                VectorDocument.namespace_id,
                VectorDocument.document_id,
                VectorDocument.company_id,
                chunk_count,
                null_chunks_expr,
            )
            .where(
                tuple_(
                    VectorDocument.namespace_id,
                    VectorDocument.document_id,
                    VectorDocument.company_id,
                ).in_(unique_keys)
            )
            .group_by(
                VectorDocument.namespace_id,
                VectorDocument.document_id,
                VectorDocument.company_id,
            )
        )

        async with self._session_factory() as session:
            result = await session.execute(stmt)
            rows: Sequence[tuple[str, str, str | None, int, int | None]] = result.tuples().all()

        for ns, doc_id, cid, cnt, null_chunks in rows:
            if cid is None:
                continue
            key = (ns, doc_id, cid)
            if key not in out:
                continue
            null_int = int(null_chunks or 0)
            total = int(cnt)
            if null_int > 0:
                out[key] = "pending_embedding"
            elif total > 0:
                out[key] = "ready"
            else:
                out[key] = "absent"

        return out

    async def fetch_stale_chunks_for_reembed(
        self,
        *,
        limit: int,
        target_embedding_model: str,
    ) -> list[tuple[str, str, str]]:
        """
        Кандидаты на перевекторизацию: ``(id, content, company_id)``.

        Возвращает только строки с непустым ``company_id`` (NULL/'' разбираются
        отдельным maintenance-тиком ``rag_cleanup_orphan_company_chunks_tick``).
        Стабильный порядок по ``company_id``/``id`` — для группировки по компании.
        """
        if limit <= 0:
            raise ValueError("fetch_stale_chunks_for_reembed: limit must be positive")
        stale_where = or_(
            VectorDocument.embedding_model.is_(None),
            VectorDocument.embedding_model != target_embedding_model,
        )
        async with self._session_factory() as session:
            stmt = (
                select(VectorDocument.id, VectorDocument.content, VectorDocument.company_id)
                .where(stale_where)
                .where(VectorDocument.content.isnot(None))
                .where(VectorDocument.content != "")
                .where(VectorDocument.company_id.isnot(None))
                .where(VectorDocument.company_id != "")
                .order_by(VectorDocument.company_id.asc(), VectorDocument.id.asc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            rows: Sequence[tuple[str, str, str | None]] = result.tuples().all()
        stale_chunks: list[tuple[str, str, str]] = []
        for chunk_id, content, company_id in rows:
            if company_id is None:
                raise ValueError("fetch_stale_chunks_for_reembed returned chunk without company_id")
            stale_chunks.append((chunk_id, content, company_id))
        return stale_chunks

    async def write_reembed_chunk_embeddings(
        self,
        doc_embeddings: list[tuple[str, list[float]]],
        target_embedding_model: str,
    ) -> int:
        """Записывает векторы для списка ``(chunk_id, embedding)``."""
        if not doc_embeddings:
            return 0
        updated = 0
        async with self._session_factory() as session:
            for doc_id, emb in doc_embeddings:
                upd = (
                    update(VectorDocument)
                    .where(VectorDocument.id == doc_id)
                    .values(
                        embedding=emb,
                        embedding_model=target_embedding_model,
                    )
                )
                upd_result = await session.execute(upd)
                updated += get_rowcount(upd_result)
            await session.commit()
        return updated

    @override
    async def delete_orphan_company_chunks(self, *, limit: int) -> int:
        """
        Батчевое удаление чанков ``vector_documents`` без ``company_id``.

        У таких строк нет владельца — биллинг и поиск по тенанту невозможны.
        Зовётся отдельным maintenance-тиком, не reembed.
        """
        if limit <= 0:
            raise ValueError("delete_orphan_company_chunks: limit must be positive")
        async with self._session_factory() as session:
            ids_stmt = (
                select(VectorDocument.id)
                .where(
                    or_(
                        VectorDocument.company_id.is_(None),
                        VectorDocument.company_id == "",
                    )
                )
                .order_by(VectorDocument.id.asc())
                .limit(limit)
            )
            result = await session.execute(ids_stmt)
            ids = [row[0] for row in result.all()]
            if not ids:
                return 0
            del_stmt = delete(VectorDocument).where(VectorDocument.id.in_(ids))
            del_result = await session.execute(del_stmt)
            await session.commit()
        return get_rowcount(del_result)

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

        async with self._session_factory() as session:
            _ = await session.execute(text("SET hnsw.iterative_scan = relaxed_order"))
            distance_expr = sql_cast(VectorDocument.embedding.op("<=>")(query_embedding), Float())
            similarity_expr = (1 - distance_expr).label("similarity")

            stmt = (
                select(VectorDocument, similarity_expr)
                .where(VectorDocument.namespace_id == namespace_id)
                .where(VectorDocument.embedding.isnot(None))
                .where(VectorDocument.embedding_model == embedding_model)
                .order_by(distance_expr)
                .limit(fetch_limit)
            )

            if filters:
                stmt = stmt.where(self._build_metadata_filter_expression(filters))

            result = await session.execute(stmt)
            rows: Sequence[tuple[VectorDocument, float | None]] = result.tuples().all()

        results = self._build_search_results(rows, namespace_id)
        if not freshness_enabled or freshness_weight is None or freshness_half_life_days is None:
            return results

        now = datetime.now(timezone.utc)
        docs_by_chunk_id = {doc.id: doc for doc, _similarity in rows}
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
        rescored.sort(key=lambda entry: entry.score, reverse=True)
        return rescored[:limit]

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
        """
        Двухканальный поиск: семантический (cosine) + лексический (websearch tsquery,
        ``ts_rank_cd``), слияние RRF. При заданных ``freshness_weight``/``freshness_half_life_days``
        итоговый score = RRF * мультипликативный экспоненциальный decay возраста документа,
        применённый к полному fused-пулу кандидатов до среза ``limit``.
        """
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

        async with self._session_factory() as session:
            _ = await session.execute(text("SET hnsw.iterative_scan = relaxed_order"))

            # Семантический канал
            distance_expr = sql_cast(VectorDocument.embedding.op("<=>")(query_embedding), Float())
            similarity_expr = (1 - distance_expr).label("similarity")

            semantic_stmt = (
                select(VectorDocument.id, similarity_expr)
                .where(VectorDocument.namespace_id == namespace_id)
                .where(VectorDocument.embedding.isnot(None))
                .where(VectorDocument.embedding_model == embedding_model)
            )
            if filters:
                semantic_stmt = semantic_stmt.where(self._build_metadata_filter_expression(filters))
            semantic_stmt = semantic_stmt.order_by(distance_expr).limit(per_channel)

            # Лексический канал: websearch-синтаксис + русская морфология (Snowball),
            # ранг с учётом плотности/близости терминов (ts_rank_cd).
            tsquery_expr = func.websearch_to_tsquery(LEXICAL_TS_CONFIG, query)
            rank_expr = func.ts_rank_cd(VectorDocument.content_tsv, tsquery_expr).label("lexical_rank")

            lexical_stmt = (
                select(VectorDocument.id, rank_expr)
                .where(VectorDocument.namespace_id == namespace_id)
                .where(VectorDocument.content_tsv.op("@@")(tsquery_expr))
            )
            if filters:
                lexical_stmt = lexical_stmt.where(self._build_metadata_filter_expression(filters))
            lexical_stmt = lexical_stmt.order_by(rank_expr.desc()).limit(per_channel)

            semantic_result = await session.execute(semantic_stmt)
            semantic_rows: Sequence[tuple[str, float | None]] = semantic_result.tuples().all()
            lexical_result = await session.execute(lexical_stmt)
            lexical_rows: Sequence[tuple[str, float | None]] = lexical_result.tuples().all()

            # RRF-слияние
            semantic_ids = [row[0] for row in semantic_rows]
            lexical_ids = [row[0] for row in lexical_rows]

            fused = reciprocal_rank_fusion([semantic_ids, lexical_ids], k=rrf_k_int)
            if not fused:
                return []

            # Freshness переранжирует полный fused-пул, поэтому документы
            # загружаются для всех кандидатов, а не только для top-limit.
            candidate_pairs = fused if freshness_enabled else fused[:limit]
            candidate_ids = [doc_id for doc_id, _score in candidate_pairs]

            docs_stmt = select(VectorDocument).where(VectorDocument.id.in_(candidate_ids))
            docs_rows = list((await session.execute(docs_stmt)).scalars().all())
            by_id = {doc.id: doc for doc in docs_rows}

            scored: list[tuple[str, float, RAGMetadata]] = []
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
                scored.append((doc_id, final_score, doc.metadata_ or {}))

            scored.sort(key=lambda item: item[1], reverse=True)
            top = scored[:limit]
            top_ids = [doc_id for doc_id, _score, _metadata in top]
            if not top_ids:
                return []

            headline_by_id = await self._lexical_headlines(
                session,
                doc_ids=top_ids,
                query=query,
            )

        score_by_id = {doc_id: final_score for doc_id, final_score, _metadata in top}
        ordered: list[RAGSearchResult] = []
        for doc_id in top_ids:
            doc = by_id.get(doc_id)
            if doc is None:
                continue
            provenance: RAGMetadata = {"channel": "hybrid_rrf", "rrf_k": rrf_k_int}
            if doc_id in freshness_provenance:
                provenance.update(freshness_provenance[doc_id])
            headline = headline_by_id.get(doc_id)
            if headline:
                provenance["headline"] = headline
            ordered.append(
                _rag_search_result_from_document(
                    doc,
                    score=score_by_id[doc_id],
                    namespace_id=namespace_id,
                    provenance=provenance,
                )
            )
        return ordered

    async def _lexical_headlines(
        self,
        session: AsyncSession,
        *,
        doc_ids: list[str],
        query: str,
    ) -> dict[str, str]:
        """Сниппеты ``ts_headline`` с подсветкой терминов запроса для финальной выдачи."""
        tsquery_expr = func.websearch_to_tsquery(LEXICAL_TS_CONFIG, query)
        headline_expr = func.ts_headline(
            LEXICAL_TS_CONFIG,
            VectorDocument.content,
            tsquery_expr,
            TS_HEADLINE_OPTIONS,
        )
        stmt = select(VectorDocument.id, headline_expr).where(VectorDocument.id.in_(doc_ids))
        rows: Sequence[tuple[str, str | None]] = (await session.execute(stmt)).tuples().all()
        headlines: dict[str, str] = {}
        for doc_id, headline in rows:
            if headline is None:
                continue
            normalized = headline.strip()
            if normalized:
                headlines[doc_id] = normalized
        return headlines

    def _build_search_results(
        self,
        rows: Sequence[tuple[VectorDocument, float | None]],
        namespace_id: str,
    ) -> list[RAGSearchResult]:
        search_results: list[RAGSearchResult] = []
        for row in rows:
            doc = row[0]
            score = float(row[1]) if row[1] is not None else 0.0
            search_results.append(
                _rag_search_result_from_document(
                    doc,
                    score=score,
                    namespace_id=namespace_id,
                    provenance={},
                )
            )
        return search_results
