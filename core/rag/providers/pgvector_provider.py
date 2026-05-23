"""
RAG провайдер на базе pgvector (PostgreSQL).
Хранит векторные документы в таблице vector_documents через SQLAlchemy 2+.
"""

import hashlib
import math
import os
import re
import uuid
from typing import Literal

import tiktoken
from sqlalchemy import and_, case, delete, func, or_, select, text, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config import get_settings
from core.config.llm_openai_compat import yandex_provider_http_headers
from core.config.models import RAGProviderConfig
from core.config.testing import is_testing
from core.db.models import VectorDocument
from core.db.utils import get_rowcount
from core.files.reader import FileReader
from core.files.reader.models import FileReadKind, FileReadResult, ReadPage
from core.logging import get_logger
from core.rag.base_provider import BaseRAGProvider, validate_metadata_filters
from core.rag.embedding_runtime import RagEmbeddingRuntime
from core.rag.models import RAGDocument, RAGMetadata, RAGMetadataFilter, RAGNamespace, RAGSearchOptions, RAGSearchResult
from core.rag.openai_http_contracts import PROVIDER_LITSERVE_PLACEHOLDER_BEARER
from core.rag.rrf import reciprocal_rank_fusion
from core.rag.services.embedding_service import EmbeddingService
from core.rag.ttl import ensure_ttl_seconds_in_metadata
from core.rag.upload_profile_binding import UploadProfileBinding
from core.types import JsonValue, require_json_object

logger = get_logger(__name__)
# Значения из шаблонного conf.json — не отправлять в OpenRouter как ключ
_EMBEDDING_API_KEY_PLACEHOLDERS: frozenset[str] = frozenset(
    {
        "YOUR_EMBEDDING_API_KEY",
        "YOUR_OPENROUTER_API_KEY",
    }
)


class DeterministicEmbeddingService(EmbeddingService):
    """Детерминированный embedding-сервис для тестов и локального mock-режима."""

    async def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        dim = self.get_embedding_dimension()
        embeddings: list[list[float]] = []
        for source_text in texts:
            vector = [0.0] * dim
            tokens = re.findall(r"[\w]+", source_text.lower(), flags=re.UNICODE)
            if not tokens:
                tokens = ["__empty__"]

            def add_feature(feature: str, weight: float = 1.0) -> None:
                digest = hashlib.sha256(feature.encode("utf-8")).digest()
                idx = int.from_bytes(digest[:4], "big") % dim
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                vector[idx] += sign * weight

            for token in tokens:
                add_feature(token)
            add_feature(f"__document__:{source_text}", weight=0.125)
            norm = math.sqrt(sum(value * value for value in vector))
            if norm == 0.0:
                raise ValueError("Mock embedding norm is zero")
            embeddings.append([value / norm for value in vector])
        return embeddings


def _normalize_embedding_api_key(raw: str | None) -> str:
    if raw is None:
        return ""
    s = str(raw).strip()
    if not s or s in _EMBEDDING_API_KEY_PLACEHOLDERS:
        return ""
    return s


def _resolve_pgvector_embedding_api_key(config: RAGProviderConfig) -> str:
    key = _normalize_embedding_api_key(config.embedding_api_key)
    if key:
        return key

    settings = get_settings()
    if settings.rag.embedding.provider == "provider_litserve":
        return PROVIDER_LITSERVE_PLACEHOLDER_BEARER
    if getattr(settings.llm, "provider", None) == "openrouter":
        or_conf = getattr(settings.llm, "openrouter", None)
        if or_conf is not None:
            llm_key = _normalize_embedding_api_key(getattr(or_conf, "api_key", None))
            if llm_key:
                logger.info(
                    "pgvector: для embeddings используется llm.openrouter.api_key "
                    "(rag.providers.pgvector.embedding_api_key пустой или плейсхолдер)"
                )
                return llm_key
    if getattr(settings.llm, "provider", None) == "yandex":
        yc = getattr(settings.llm, "yandex", None)
        if yc is not None:
            llm_key = _normalize_embedding_api_key(getattr(yc, "api_key", None))
            if llm_key:
                logger.info(
                    "pgvector: для embeddings используется llm.yandex.api_key "
                    "(rag.providers.pgvector.embedding_api_key пустой или плейсхолдер)"
                )
                return llm_key
    raise ValueError(
        "Нужен rag.providers.pgvector.embedding_api_key (OpenRouter sk-or-...) "
        "или llm.openrouter.api_key при llm.provider=openrouter, "
        "или llm.yandex.api_key при llm.provider=yandex. "
        "При rag.embedding.provider=provider_litserve ключ из pgvector не обязателен. "
        "Плейсхолдеры YOUR_* из conf.json не считаются ключом. "
        "ENV: RAG__PROVIDERS__PGVECTOR__EMBEDDING_API_KEY, LLM__OPENROUTER__API_KEY"
    )


class PgVectorProvider(BaseRAGProvider):
    """
    RAG провайдер на базе pgvector.
    Использует PostgreSQL + pgvector для хранения и поиска векторных документов.
    """

    DEFAULT_CHUNK_SIZE = 1000
    DEFAULT_CHUNK_OVERLAP = 100

    def __init__(
        self,
        config: RAGProviderConfig,
        embedding_config: RagEmbeddingRuntime | None = None,
    ) -> None:
        super().__init__(config)

        db_url = config.db_url
        if not db_url:
            settings = get_settings()
            if not settings.database.rag_url:
                raise ValueError("DATABASE__RAG_URL не настроен")
            db_url = settings.database.rag_url

        self._engine = create_async_engine(
            db_url,
            echo=False,
            pool_size=5,
            max_overflow=10,
        )
        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        api_key = _resolve_pgvector_embedding_api_key(config)

        timeout = config.timeout

        if embedding_config is None:
            raise ValueError("embedding runtime обязателен для pgvector")
        model = embedding_config.model
        dimension = embedding_config.dimension
        embedding_base_url = embedding_config.base_url
        mrl_output_dimension = embedding_config.mrl_output_dimension

        if not model:
            raise ValueError("embedding.model обязателен в конфигурации")
        if not dimension:
            raise ValueError("embedding.dimension обязателен в конфигурации")

        embedding_extra_headers = None
        root_for_yandex_check = (embedding_base_url or "").strip()
        if "llm.api.cloud.yandex.net" in root_for_yandex_check:
            yc = get_settings().llm.yandex
            if yc is None:
                raise ValueError(
                    "Embedding base_url указывает на llm.api.cloud.yandex.net: задайте блок llm.yandex "
                    "(api_key, folder_id)."
                )
            embedding_extra_headers = yandex_provider_http_headers(yc)

        use_deterministic_embeddings = (
            is_testing()
            or os.environ.get("RAG__EMBEDDING__MOCK") == "true"
            or os.environ.get("PGVECTOR_TEST_MOCK_EMBEDDINGS") == "true"
        )
        embedding_service_cls = (
            DeterministicEmbeddingService if use_deterministic_embeddings else EmbeddingService
        )

        self._embedding_service = embedding_service_cls(
            api_key=api_key,
            models=[model],
            base_url=embedding_base_url or None,
            timeout=timeout,
            dimension=dimension,
            mrl_output_dimension=mrl_output_dimension,
            extra_headers=embedding_extra_headers,
        )
        if use_deterministic_embeddings:
            logger.info("PgVector провайдер: mock embeddings для тестов")

        self._file_reader = FileReader()
        self._chunk_size = config.chunk_size
        self._chunk_overlap = config.chunk_overlap
        self._tokenizer = tiktoken.get_encoding("cl100k_base")

        logger.info(f"PgVector провайдер инициализирован: model={model}, dimension={dimension}")

    @property
    def provider_name(self) -> str:
        return "pgvector"

    async def close(self) -> None:
        await self._engine.dispose()

    @property
    def embedding_service(self) -> EmbeddingService:
        """Сервис эмбеддингов pgvector (для оркестраторов фоновых задач)."""
        return self._embedding_service

    def embedding_model_name(self) -> str:
        """Идентификатор текущей модели эмбеддинга для записи в embedding_model."""
        return self._embedding_service.model

    # -- Чанкинг --

    def _chunk_text(self, text_content: str) -> list[str]:
        """Разбивает текст на chunks по токенам."""
        tokens = self._tokenizer.encode(text_content)
        chunks = []
        start = 0
        while start < len(tokens):
            end = start + self._chunk_size
            chunk_tokens = tokens[start:end]
            chunk_text = self._tokenizer.decode(chunk_tokens)
            chunks.append(chunk_text)
            start = end - self._chunk_overlap
        return chunks

    def _chunks_from_file_read_result(
        self,
        read_result: FileReadResult,
    ) -> list[tuple[str, RAGMetadata]]:
        """Чанки для embeddings строго из FileReadResult.pages."""
        out: list[tuple[str, RAGMetadata]] = []
        doc_checksum = read_result.source_checksum or ""
        for page in read_result.pages:
            body = (page.text or "").strip()
            if not body:
                continue
            base_meta: RAGMetadata = {
                "file_read_page_index": page.index,
                "file_read_page_label": page.label,
                "file_read_source_checksum": doc_checksum,
                "file_read_detected_kind": read_result.detected_kind.value,
                "file_read_page_count": read_result.page_count,
            }
            if page.assets:
                base_meta["file_read_page_asset_checksums"] = [a.checksum for a in page.assets]
            subchunks = self._chunk_text(body)
            for sci, chunk_text in enumerate(subchunks):
                meta = {**base_meta, "file_read_subchunk_index": sci}
                out.append((chunk_text, meta))
        if not out:
            raise ValueError(
                "После FileReader нет текста для индексации (пустые страницы). "
                f"file={read_result.file_name}"
            )
        return out

    # -- Namespaces --

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

    async def list_namespaces(self) -> list[RAGNamespace]:
        async with self._session_factory() as session:
            stmt = select(
                VectorDocument.namespace_id,
                func.count().label("doc_count"),
            ).group_by(VectorDocument.namespace_id)
            result = await session.execute(stmt)
            rows = result.all()

        return [
            RAGNamespace(
                namespace_id=row.namespace_id,
                name=row.namespace_id,
                document_count=row.doc_count,
            )
            for row in rows
        ]

    async def delete_namespace(self, namespace_id: str) -> bool:
        async with self._session_factory() as session:
            stmt = delete(VectorDocument).where(VectorDocument.namespace_id == namespace_id)
            result = await session.execute(stmt)
            await session.commit()
            deleted = get_rowcount(result)

        logger.info(f"Удален namespace {namespace_id}: {deleted} записей")
        return deleted > 0

    # -- Document Upload --

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
        read_result = await self._file_reader.read(
            file_path,
            file_name=doc_name,
        )
        doc_metadata["file_type"] = read_result.detected_kind.value
        doc_metadata["s3_key"] = s3_key
        doc_metadata["s3_bucket"] = bucket_name
        doc_metadata["original_filename"] = original_filename
        if read_result.source_checksum:
            doc_metadata["source_checksum"] = read_result.source_checksum

        return await self._upload_file_read_internal(
            namespace_id=namespace_id,
            read_result=read_result,
            document_name=doc_name,
            metadata=doc_metadata,
        )

    async def upload_document_from_s3(
        self,
        namespace_id: str,
        s3_key: str,
        document_name: str | None = None,
        metadata: RAGMetadata | None = None,
        upload_profile: UploadProfileBinding | None = None,
    ) -> RAGDocument:
        doc_metadata = dict(metadata) if metadata is not None else {}
        bucket_key = doc_metadata.get("s3_bucket")
        if bucket_key is not None and not isinstance(bucket_key, str):
            raise ValueError("metadata.s3_bucket должен быть строкой")
        file_data, bucket_name, original_filename = await self._download_file_from_s3(
            s3_key, bucket_config_key=bucket_key
        )

        filename = document_name or original_filename

        read_result = await self._file_reader.read(
            file_data,
            file_name=filename,
        )
        doc_metadata["file_type"] = read_result.detected_kind.value
        doc_metadata["s3_key"] = s3_key
        doc_metadata["s3_bucket"] = bucket_name
        doc_metadata["original_filename"] = original_filename
        if read_result.source_checksum:
            doc_metadata["source_checksum"] = read_result.source_checksum

        logger.info(f"Документ из S3 индексируется через FileReader: {s3_key}")
        return await self._upload_file_read_internal(
            namespace_id=namespace_id,
            read_result=read_result,
            document_name=filename,
            metadata=doc_metadata,
            upload_profile=upload_profile,
        )

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

    async def _upload_file_read_internal(
        self,
        namespace_id: str,
        read_result: FileReadResult,
        document_name: str,
        metadata: RAGMetadata,
        upload_profile: UploadProfileBinding | None = None,
    ) -> RAGDocument:
        """Chunk + embed из FileReadResult (единая схема с flows FileReader)."""
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

        async with self._session_factory() as session:
            stmt = delete(VectorDocument).where(
                VectorDocument.namespace_id == namespace_id,
                VectorDocument.document_id == document_id,
            )
            result = await session.execute(stmt)
            await session.commit()
            count = get_rowcount(result)
            if count:
                logger.info(f"Удалены старые чанки документа '{document_name}': {count}")

        chunk_pairs = self._chunks_from_file_read_result(read_result)
        chunks = [pair[0] for pair in chunk_pairs]
        chunk_metas = [pair[1] for pair in chunk_pairs]

        if index_profile_config is not None and not isinstance(index_profile_config, dict):
            raise ValueError("index_profile_config должен быть объектом")
        indexing_runtime: RAGMetadata = dict(index_profile_config or {})

        # Если embedding-сервис недоступен — сохраняем чанки с embedding=NULL.
        # crm_reembed_stale_documents_tick / rag_reembed_stale_documents_tick подберут их
        # когда сервис восстановится (ищут embedding_model IS NULL).
        try:
            raw_embeddings = await self._embedding_service.generate_embeddings(chunks)
            embeddings: list[list[float] | None] = list(raw_embeddings)
            embedding_tokens = self._embedding_service.count_tokens(chunks)
            embedding_model: str | None = self.embedding_model_name()
            indexing_runtime["embedding"] = require_json_object(
                self._embedding_service.runtime_snapshot(embedding_tokens=embedding_tokens),
                "embedding runtime",
            )
        except Exception as exc:
            logger.warning(
                f"Embedding unavailable for '{document_name}' in '{namespace_id}': {exc}. "
                "Storing chunks without embeddings — reembed task will retry."
            )
            embeddings = [None] * len(chunks)
            embedding_model = None
            indexing_runtime["embedding"] = {"pending": True, "error": str(exc)[:200]}

        company_id_value = metadata.get("company_id")
        if company_id_value is not None and not isinstance(company_id_value, str):
            raise ValueError("metadata.company_id должен быть строкой")

        rows: list[VectorDocument] = []
        for i, (chunk, emb, chunk_meta) in enumerate(zip(chunks, embeddings, chunk_metas)):
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
                    content=chunk,
                    embedding=emb,
                    embedding_model=embedding_model,
                    chunk_index=i,
                    total_chunks=len(chunks),
                    metadata_={
                        **metadata,
                        **chunk_meta,
                        "indexing_runtime": indexing_runtime,
                        "document_id": document_id,
                        "document_name": document_name,
                        "chunk_index": i,
                        "total_chunks": len(chunks),
                    },
                )
            )

        async with self._session_factory() as session:
            session.add_all(rows)
            await session.commit()

        logger.info(f"Загружен документ '{document_name}' в {namespace_id}: {len(chunks)} chunks")
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
        """Прямой текст (без файла): одна логическая страница в FileReadResult."""
        page = ReadPage(index=0, text=text_content, assets=[], label=None)
        read_result = FileReadResult(
            file_name=document_name,
            content_type="text/plain",
            detected_kind=FileReadKind.TEXT,
            page_count=1,
            pages=[page],
            warnings=[],
        )
        return await self._upload_file_read_internal(
            namespace_id=namespace_id,
            read_result=read_result,
            document_name=document_name,
            metadata=metadata,
        )

    # -- Document CRUD --

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

    async def list_documents(self, namespace_id: str, limit: int = 100) -> list[RAGDocument]:
        async with self._session_factory() as session:
            stmt = (
                select(
                    VectorDocument.document_id,
                    VectorDocument.document_name,
                    VectorDocument.metadata_,
                )
                .where(VectorDocument.namespace_id == namespace_id)
                .distinct(VectorDocument.document_id)
                .limit(limit)
            )
            result = await session.execute(stmt)
            rows = result.all()

        docs = []
        for row in rows:
            meta = row.metadata_ or {}
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

    async def list_documents_with_filters(
        self, namespace_id: str, where: RAGMetadataFilter | None = None, limit: int = 100
    ) -> list[RAGDocument]:
        async with self._session_factory() as session:
            stmt = (
                select(
                    VectorDocument.document_id,
                    VectorDocument.document_name,
                    VectorDocument.metadata_,
                )
                .where(VectorDocument.namespace_id == namespace_id)
                .distinct(VectorDocument.document_id)
            )

            if where:
                stmt = stmt.where(self._build_metadata_filter_expression(where))

            stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            rows = result.all()

        docs = []
        for row in rows:
            meta = row.metadata_ or {}
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

        logger.info(f"Найдено {len(docs)} документов с фильтрами в {namespace_id}")
        return docs

    def _metadata_expr_for_scalar(self, key: str, value: JsonValue):
        if isinstance(value, bool):
            return VectorDocument.metadata_[key].as_boolean()
        if isinstance(value, int) and not isinstance(value, bool):
            return VectorDocument.metadata_[key].as_integer()
        if isinstance(value, float):
            return VectorDocument.metadata_[key].as_float()
        return VectorDocument.metadata_[key].as_string()

    def _build_field_operator_expression(self, key: str, operator: str, op_value: JsonValue):
        if operator == "$eq":
            return self._metadata_expr_for_scalar(key, op_value) == op_value
        if operator == "$ne":
            return self._metadata_expr_for_scalar(key, op_value) != op_value

        if operator == "$in":
            if not isinstance(op_value, (list, tuple)) or len(op_value) == 0:
                raise ValueError(
                    f"RAG filters: $in требует непустой список значений для ключа {key!r}",
                )
            vals = list(op_value)
            if len(vals) == 1:
                v0 = vals[0]
                return self._metadata_expr_for_scalar(key, v0) == v0
            return or_(*[self._metadata_expr_for_scalar(key, v) == v for v in vals])
        if operator == "$nin":
            if not isinstance(op_value, (list, tuple)) or len(op_value) == 0:
                raise ValueError(
                    f"RAG filters: $nin требует непустой список значений для ключа {key!r}",
                )
            vals = list(op_value)
            if len(vals) == 1:
                v0 = vals[0]
                return self._metadata_expr_for_scalar(key, v0) != v0
            return and_(*[self._metadata_expr_for_scalar(key, v) != v for v in vals])

        if isinstance(op_value, int) and not isinstance(op_value, bool):
            col_int = VectorDocument.metadata_[key].as_integer()
            if operator == "$gt":
                return col_int > op_value
            if operator == "$gte":
                return col_int >= op_value
            if operator == "$lt":
                return col_int < op_value
            if operator == "$lte":
                return col_int <= op_value
        else:
            fv = float(op_value)
            if operator == "$gt":
                return VectorDocument.metadata_[key].as_float() > fv
            if operator == "$gte":
                return VectorDocument.metadata_[key].as_float() >= fv
            if operator == "$lt":
                return VectorDocument.metadata_[key].as_float() < fv
            if operator == "$lte":
                return VectorDocument.metadata_[key].as_float() <= fv

        raise ValueError(f"RAG filters: неподдерживаемый оператор {operator}")

    def _build_metadata_filter_expression(self, filters: RAGMetadataFilter):
        validate_metadata_filters(filters)
        return self._build_metadata_filter_node(filters)

    def _build_metadata_filter_node(self, node: RAGMetadataFilter):
        if "$and" in node:
            return and_(*[self._build_metadata_filter_node(item) for item in node["$and"]])
        if "$or" in node:
            return or_(*[self._build_metadata_filter_node(item) for item in node["$or"]])

        expressions = []
        for key, value in node.items():
            if isinstance(value, dict):
                op, op_value = next(iter(value.items()))
                expressions.append(self._build_field_operator_expression(key, op, op_value))
                continue
            expressions.append(self._metadata_expr_for_scalar(key, value) == value)
        return and_(*expressions)

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
            logger.info(f"Удален документ {document_id}: {deleted} chunks")
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
            rows = result.all()

        for row in rows:
            ns, doc_id, cid, cnt, null_chunks = (
                row[0],
                row[1],
                row[2],
                row[3],
                row[4],
            )
            if cid is None:
                continue
            key = (str(ns), str(doc_id), str(cid))
            if key not in out:
                continue
            null_int = int(null_chunks or 0)
            total = int(cnt or 0)
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
            rows = list(result.all())
        return [(str(row[0]), str(row[1]), str(row[2])) for row in rows]

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

    # -- Search --

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
            return await self._hybrid_search_rrf(
                namespace_id=namespace_id,
                query=query,
                limit=limit,
                filters=filters,
                embedding_model=embedding_model,
                rrf_k=search_options.rrf_k,
                per_channel_top_k=search_options.per_channel_top_k,
            )

        query_embedding = await self._embedding_service.generate_embedding(query)

        async with self._session_factory() as session:
            await session.execute(text("SET hnsw.iterative_scan = relaxed_order"))
            distance_expr = VectorDocument.embedding.cosine_distance(query_embedding)
            similarity_expr = (1 - distance_expr).label("similarity")

            stmt = (
                select(VectorDocument, similarity_expr)
                .where(VectorDocument.namespace_id == namespace_id)
                .where(VectorDocument.embedding.isnot(None))
                .where(VectorDocument.embedding_model == embedding_model)
                .order_by(distance_expr)
                .limit(limit)
            )

            if filters:
                stmt = stmt.where(self._build_metadata_filter_expression(filters))

            result = await session.execute(stmt)
            rows = result.all()

        return self._build_search_results(list(rows), namespace_id)

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
    ) -> list[RAGSearchResult]:
        """Двухканальный поиск: семантический (cosine) + лексический (tsquery), слияние RRF."""
        query_embedding = await self._embedding_service.generate_embedding(query)

        rrf_k_int = 60 if rrf_k is None else int(rrf_k)
        per_channel = limit * 3 if per_channel_top_k is None else int(per_channel_top_k)

        async with self._session_factory() as session:
            await session.execute(text("SET hnsw.iterative_scan = relaxed_order"))

            # Семантический канал
            distance_expr = VectorDocument.embedding.cosine_distance(query_embedding)
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

            # Лексический канал (tsquery по content_tsv)
            tsquery_expr = func.plainto_tsquery("simple", query)
            rank_expr = func.ts_rank(VectorDocument.content_tsv, tsquery_expr).label("lexical_rank")

            lexical_stmt = (
                select(VectorDocument.id, rank_expr)
                .where(VectorDocument.namespace_id == namespace_id)
                .where(VectorDocument.content_tsv.op("@@")(tsquery_expr))
            )
            if filters:
                lexical_stmt = lexical_stmt.where(self._build_metadata_filter_expression(filters))
            lexical_stmt = lexical_stmt.order_by(rank_expr.desc()).limit(per_channel)

            semantic_rows = (await session.execute(semantic_stmt)).all()
            lexical_rows = (await session.execute(lexical_stmt)).all()

            # RRF-слияние
            semantic_ids = [row[0] for row in semantic_rows]
            lexical_ids = [row[0] for row in lexical_rows]

            fused = reciprocal_rank_fusion([semantic_ids, lexical_ids], k=rrf_k_int)

            fused_ordered = fused[:limit]
            score_by_id = dict(fused_ordered)
            top_ids = [doc_id for doc_id, _score in fused_ordered]

            if not top_ids:
                return []

            docs_stmt = select(VectorDocument).where(VectorDocument.id.in_(top_ids))
            docs_rows = list((await session.execute(docs_stmt)).scalars().all())

        by_id = {doc.id: doc for doc in docs_rows}
        ordered: list[RAGSearchResult] = []
        for doc_id in top_ids:
            doc = by_id.get(doc_id)
            if doc is None:
                continue
            ordered.append(
                RAGSearchResult(
                    content=doc.content,
                    score=float(score_by_id[doc_id]),
                    document_id=doc.document_id,
                    document_name=doc.document_name or "",
                    metadata=doc.metadata_ or {},
                    namespace=namespace_id,
                    chunk_id=doc.id,
                    provenance={"channel": "hybrid_rrf", "rrf_k": rrf_k_int},
                )
            )
        return ordered

    def _build_search_results(
        self,
        rows: list[tuple[VectorDocument, float | None]],
        namespace_id: str,
    ) -> list[RAGSearchResult]:
        search_results: list[RAGSearchResult] = []
        for row in rows:
            doc = row[0]
            score = float(row[1]) if row[1] is not None else 0.0
            search_results.append(
                RAGSearchResult(
                    content=doc.content,
                    score=score,
                    document_id=doc.document_id,
                    document_name=doc.document_name or "",
                    metadata=doc.metadata_ or {},
                    namespace=namespace_id,
                    chunk_id=doc.id,
                    provenance={},
                )
            )
        return search_results
