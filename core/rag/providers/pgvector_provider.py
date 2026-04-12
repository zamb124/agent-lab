"""
RAG провайдер на базе pgvector (PostgreSQL).
Хранит векторные документы в таблице vector_documents через SQLAlchemy 2+.
"""

import logging
import os
import uuid
from pathlib import Path
from collections.abc import Sequence
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, desc, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.sql.selectable import Select

from core.config import get_settings
from core.config.llm_openai_compat import resolve_llm_api_key_for_openai_compatible_calls
from core.config.openai_v1_base_url import normalize_openai_v1_base_url
from core.db.models import VectorDocument
from core.rag.base_provider import BaseRAGProvider
from core.rag.chunking import split_parsed_document
from core.rag_indexing_schema import IndexProfileConfig
from core.rag.models import RAGDocument, RAGNamespace, RAGSearchResult
from core.rag.parsed_document import ParsedDocument
from core.rag.parsing import parse_document_bytes
from core.rag.rrf import reciprocal_rank_fusion
from core.rag.services.chunk_enrichment import (
    ChunkEnricher,
    ChunkEnrichmentContext,
    NoOpChunkEnricher,
)
from core.rag.services.document_parser import DocumentParser
from core.rag.embedding_runtime import RagEmbeddingRuntime
from core.rag.services.embedding_service import EmbeddingService
from core.rag.index_profile_merge import merge_index_profile_config
from core.rag.upload_profile_binding import UploadProfileBinding

logger = logging.getLogger(__name__)

_METADATA_INDEXING_KEYS: frozenset[str] = frozenset({"index_profile_config"})
_METADATA_SERVER_KEYS: frozenset[str] = frozenset({"indexing_runtime"})

# Значения из шаблонного conf.json — не отправлять в OpenRouter как ключ
_EMBEDDING_API_KEY_PLACEHOLDERS: frozenset[str] = frozenset(
    {
        "YOUR_EMBEDDING_API_KEY",
        "YOUR_OPENROUTER_API_KEY",
    }
)


def _normalize_embedding_api_key(raw: Optional[str]) -> str:
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

    DEFAULT_CHUNK_SIZE = 1000
    DEFAULT_CHUNK_OVERLAP = 100

    def __init__(
        self,
        config: Dict[str, Any],
        embedding_config: Optional[RagEmbeddingRuntime | Dict[str, Any]] = None,
        *,
        chunk_enricher: ChunkEnricher | None = None,
    ):
        super().__init__(config)

        settings = get_settings()

        db_url = config.get("db_url")
        if not db_url:
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

        timeout = config.get("timeout", 60)

        if embedding_config is None:
            emb_cfg: Dict[str, Any] = {}
        elif isinstance(embedding_config, RagEmbeddingRuntime):
            emb_cfg = {
                "provider": embedding_config.provider,
                "model": embedding_config.model,
                "dimension": embedding_config.dimension,
                "base_url": embedding_config.base_url,
            }
        else:
            emb_cfg = embedding_config
        embedding_provider = emb_cfg.get("provider") or "openrouter"
        model = emb_cfg.get("model")
        dimension = emb_cfg.get("dimension")
        embedding_base_url = emb_cfg.get("base_url")

        if not model:
            raise ValueError("embedding.model обязателен в конфигурации")
        if not dimension:
            raise ValueError("embedding.dimension обязателен в конфигурации")

        if embedding_provider == "provider_litserve":
            if not embedding_base_url or not str(embedding_base_url).strip():
                raise ValueError(
                    "rag.embedding: при provider=provider_litserve (локальная модель) base URL задаётся в provider_litserve.api.base_url "
                    "(корень …/v1, как у llm.openrouter.base_url)."
                )
            api_key = ""
        elif embedding_provider == "openrouter":
            if "pgvector" not in settings.rag.providers:
                raise ValueError("rag.providers.pgvector не объявлен в конфигурации")
            pgv_settings = settings.rag.providers["pgvector"]
            override_key = _normalize_embedding_api_key(pgv_settings.embedding_api_key)
            if override_key:
                api_key = override_key
            else:
                api_key = resolve_llm_api_key_for_openai_compatible_calls(settings.llm)
            if embedding_base_url is not None and str(embedding_base_url).strip():
                embedding_base_url = normalize_openai_v1_base_url(str(embedding_base_url).strip())
            else:
                raise ValueError(
                    "rag.embedding: при provider=openrouter задайте rag.embedding.api.base_url "
                    "или настройте llm (base_url и api_key активного llm.provider)."
                )
        else:
            raise ValueError(f"Неизвестный rag.embedding.provider для PgVector: {embedding_provider}")

        cost_per_1m_tokens = config.get("embedding_cost_per_1m_tokens", 5.0)
        platform_markup = config.get("embedding_platform_markup", 1.1)

        self._embedding_service = EmbeddingService(
            api_key=api_key,
            base_url=embedding_base_url,
            models=[model],
            timeout=timeout,
            dimension=dimension,
            provider=embedding_provider,
            cost_per_1m_tokens=cost_per_1m_tokens,
            platform_markup=platform_markup,
        )

        # Не RAG__*: иначе pydantic-settings кладёт значение в rag.embedding.* и падает (extra forbid).
        if os.environ.get("PGVECTOR_TEST_MOCK_EMBEDDINGS") == "true":

            async def fake_generate_embeddings(texts: List[str]) -> List[List[float]]:
                dim = self._embedding_service.dimension or 1024
                embeddings = []
                for t in texts:
                    h = hash(t)
                    embeddings.append([float((h + i) % 100) / 100.0 for i in range(dim)])
                return embeddings

            async def fake_generate_embedding(t: str) -> List[float]:
                result = await fake_generate_embeddings([t])
                return result[0]

            async def fake_iter_embedding_batches(texts: Sequence[str]):
                svc = self._embedding_service
                bs = svc.BATCH_SIZE
                n = len(texts)
                for start in range(0, n, bs):
                    batch = [texts[i] for i in range(start, min(start + bs, n))]
                    embs = await fake_generate_embeddings(batch)
                    yield start, batch, embs

            async def fake_apply_embedding_billing(_token_count: int) -> None:
                return None

            self._embedding_service.generate_embeddings = fake_generate_embeddings
            self._embedding_service.generate_embedding = fake_generate_embedding
            self._embedding_service.iter_embedding_batches = fake_iter_embedding_batches
            self._embedding_service.apply_embedding_billing = fake_apply_embedding_billing
            logger.info("PgVector провайдер: PGVECTOR_TEST_MOCK_EMBEDDINGS=true, эмбеддинги без HTTP")

        self._parser = DocumentParser()
        self._chunk_enricher: ChunkEnricher = (
            chunk_enricher if chunk_enricher is not None else NoOpChunkEnricher()
        )
        self._chunk_size = config.get("chunk_size", self.DEFAULT_CHUNK_SIZE)
        self._chunk_overlap = config.get("chunk_overlap", self.DEFAULT_CHUNK_OVERLAP)

        logger.info(f"PgVector провайдер инициализирован: model={model}, dimension={dimension}")

    def _build_indexing_runtime(
        self,
        profile_cfg: IndexProfileConfig,
        embedding_tokens: int,
    ) -> Dict[str, Any]:
        """Фактические параметры нарезки/парсинга и эмбеддинга для сохранения в метаданных."""
        return {
            "split": profile_cfg.split.model_dump(mode="json"),
            "parsing": profile_cfg.parsing.model_dump(mode="json"),
            "lexical": profile_cfg.lexical.model_dump(mode="json"),
            "embedding": self._embedding_service.runtime_snapshot(
                embedding_tokens=embedding_tokens,
            ),
        }

    @property
    def provider_name(self) -> str:
        return "pgvector"

    async def close(self):
        await self._engine.dispose()

    # -- Chunking --

    def _resolve_indexing_config_for_upload(
        self,
        metadata: Dict[str, Any],
        upload_profile: Optional[UploadProfileBinding],
    ) -> IndexProfileConfig:
        base = (
            upload_profile.config
            if upload_profile is not None
            else get_settings().rag.document_indexing
        )
        raw_override = metadata.get("index_profile_config")
        if raw_override is None:
            return base
        if not isinstance(raw_override, dict):
            raise ValueError("metadata.index_profile_config должен быть JSON-объектом")
        return merge_index_profile_config(base, raw_override)

    def _chunks_for_upload(
        self,
        text_content: str,
        metadata: Dict[str, Any],
        *,
        parsed_override: ParsedDocument | None = None,
        profile_cfg: Optional[IndexProfileConfig] = None,
    ) -> List[str]:
        """Нарезка по профилю (явный cfg или merge metadata с ``rag.document_indexing``)."""
        eff_cfg = (
            profile_cfg
            if profile_cfg is not None
            else self._resolve_indexing_config_for_upload(metadata, None)
        )
        doc_for_split = parsed_override or ParsedDocument(
            canonical_text=text_content,
            blocks=None,
            source_metadata={},
        )
        return split_parsed_document(doc_for_split, eff_cfg.split)

    # -- Namespaces --

    async def create_namespace(
        self, name: str, description: Optional[str] = None, **kwargs
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

    async def get_namespace(self, namespace_id: str) -> Optional[RAGNamespace]:
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

    async def list_namespaces(self) -> List[RAGNamespace]:
        async with self._session_factory() as session:
            stmt = (
                select(
                    VectorDocument.namespace_id,
                    func.count().label("doc_count"),
                )
                .group_by(VectorDocument.namespace_id)
            )
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
            deleted = result.rowcount or 0

        logger.info(f"Удален namespace {namespace_id}: {deleted} записей")
        return deleted > 0

    # -- Document Upload --

    async def upload_document_from_file(
        self,
        namespace_id: str,
        file_path: str,
        document_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> RAGDocument:
        s3_key, bucket_name, original_filename = await self._upload_file_to_s3(
            file_path, namespace_id, public=False
        )

        doc_name = document_name or original_filename

        doc_metadata = metadata or {}
        doc_metadata["file_type"] = self._parser.get_file_type(original_filename)
        doc_metadata["s3_key"] = s3_key
        doc_metadata["s3_bucket"] = bucket_name
        doc_metadata["original_filename"] = original_filename

        profile_cfg = self._resolve_indexing_config_for_upload(doc_metadata, None)
        raw = Path(file_path).read_bytes()
        parsed_override = parse_document_bytes(
            profile_cfg.parsing,
            raw,
            original_filename,
        )
        file_text = parsed_override.canonical_text

        return await self._upload_text_internal(
            namespace_id=namespace_id,
            text_content=file_text,
            document_name=doc_name,
            metadata=doc_metadata,
            parsed_override=parsed_override,
            upload_profile=None,
            profile_cfg=profile_cfg,
        )

    async def upload_document_from_s3(
        self,
        namespace_id: str,
        s3_key: str,
        document_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        *,
        upload_profile: Optional[UploadProfileBinding] = None,
        **kwargs,
    ) -> RAGDocument:
        doc_metadata = metadata or {}
        bucket_key = doc_metadata.get("s3_bucket")
        file_data, bucket_name, original_filename = await self._download_file_from_s3(
            s3_key, bucket_config_key=bucket_key
        )

        filename = document_name or original_filename

        doc_metadata["file_type"] = self._parser.get_file_type(filename)
        doc_metadata["s3_key"] = s3_key
        doc_metadata["s3_bucket"] = bucket_name
        doc_metadata["original_filename"] = original_filename

        profile_cfg = self._resolve_indexing_config_for_upload(doc_metadata, upload_profile)
        parsed_override = parse_document_bytes(profile_cfg.parsing, file_data, filename)
        file_text = parsed_override.canonical_text

        logger.info(f"Документ из S3 индексируется: {s3_key}")
        return await self._upload_text_internal(
            namespace_id=namespace_id,
            text_content=file_text,
            document_name=filename,
            metadata=doc_metadata,
            parsed_override=parsed_override,
            upload_profile=upload_profile,
            profile_cfg=profile_cfg,
        )

    async def upload_document_from_text(
        self,
        namespace_id: str,
        text: str,
        document_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> RAGDocument:
        doc_name = document_name or f"text_{uuid.uuid4().hex[:8]}"

        doc_metadata = metadata or {}
        doc_metadata["file_type"] = "text"

        profile_cfg = self._resolve_indexing_config_for_upload(doc_metadata, None)
        parsed_override = ParsedDocument(
            canonical_text=text,
            blocks=None,
            source_metadata={},
        )

        return await self._upload_text_internal(
            namespace_id=namespace_id,
            text_content=text,
            document_name=doc_name,
            metadata=doc_metadata,
            parsed_override=parsed_override,
            upload_profile=None,
            profile_cfg=profile_cfg,
        )

    async def _upload_text_internal(
        self,
        namespace_id: str,
        text_content: str,
        document_name: str,
        metadata: Dict[str, Any],
        *,
        parsed_override: ParsedDocument | None = None,
        upload_profile: Optional[UploadProfileBinding] = None,
        profile_cfg: Optional[IndexProfileConfig] = None,
    ) -> RAGDocument:
        """Chunk + embed + batch INSERT в vector_documents."""
        document_id = metadata.get("document_id") or str(uuid.uuid4())
        split_cfg = (
            profile_cfg
            if profile_cfg is not None
            else self._resolve_indexing_config_for_upload(metadata, upload_profile)
        )

        async with self._session_factory() as session:
            stmt = delete(VectorDocument).where(
                VectorDocument.namespace_id == namespace_id,
                VectorDocument.document_id == document_id,
            )
            result = await session.execute(stmt)
            await session.commit()
            if result.rowcount:
                logger.info(f"Удалены старые чанки документа '{document_name}': {result.rowcount}")

        chunks = self._chunks_for_upload(
            text_content,
            metadata,
            parsed_override=parsed_override,
            profile_cfg=split_cfg,
        )
        if not chunks:
            raise ValueError("Документ пустой или не удалось разбить на chunks")

        total_chunks = len(chunks)
        token_count = self._embedding_service.count_tokens(chunks)
        indexing_runtime = self._build_indexing_runtime(split_cfg, token_count)

        chunk_meta_base = {
            k: v
            for k, v in metadata.items()
            if k not in _METADATA_INDEXING_KEYS and k not in _METADATA_SERVER_KEYS
        }

        async with self._session_factory() as session:
            async for start_idx, _batch_texts, batch_embeddings in self._embedding_service.iter_embedding_batches(
                chunks
            ):
                batch_rows: List[VectorDocument] = []
                for offset, emb in enumerate(batch_embeddings):
                    chunk_index = start_idx + offset
                    chunk = chunks[chunk_index]
                    enrichment_ctx = ChunkEnrichmentContext(
                        namespace_id=namespace_id,
                        document_id=document_id,
                        document_name=document_name,
                        chunk_index=chunk_index,
                        total_chunks=total_chunks,
                        chunk_text=chunk,
                    )
                    enrichment = await self._chunk_enricher.enrich(enrichment_ctx)
                    chunk_meta = {
                        **chunk_meta_base,
                        "document_id": document_id,
                        "document_name": document_name,
                        "chunk_index": chunk_index,
                        "total_chunks": total_chunks,
                        "chunk_enrichment": enrichment.model_dump(mode="json", exclude_none=True),
                        "indexing_runtime": indexing_runtime,
                    }
                    batch_rows.append(
                        VectorDocument(
                            id=str(uuid.uuid4()),
                            namespace_id=namespace_id,
                            company_id=metadata.get("company_id"),
                            document_id=document_id,
                            document_name=document_name,
                            content=chunk,
                            embedding=emb,
                            chunk_index=chunk_index,
                            total_chunks=total_chunks,
                            metadata_=chunk_meta,
                        )
                    )
                session.add_all(batch_rows)
                await session.commit()

        await self._embedding_service.apply_embedding_billing(token_count)

        out_meta = {
            k: v
            for k, v in metadata.items()
            if k not in _METADATA_INDEXING_KEYS and k not in _METADATA_SERVER_KEYS
        }
        out_meta["total_chunks"] = total_chunks
        out_meta["indexing_runtime"] = indexing_runtime
        logger.info(f"Загружен документ '{document_name}' в {namespace_id}: {total_chunks} chunks")
        return RAGDocument(
            document_id=document_id,
            name=document_name,
            namespace=namespace_id,
            status="completed",
            metadata=out_meta,
        )

    # -- Document CRUD --

    async def get_document(self, namespace_id: str, document_id: str) -> Optional[RAGDocument]:
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

    async def list_documents(self, namespace_id: str, limit: int = 100) -> List[RAGDocument]:
        async with self._session_factory() as session:
            stmt = (
                select(
                    VectorDocument.document_id,
                    VectorDocument.document_name,
                    VectorDocument.metadata_,
                )
                .where(VectorDocument.namespace_id == namespace_id)
                .distinct(VectorDocument.document_id)
                .order_by(VectorDocument.document_id, desc(VectorDocument.updated_at))
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
        self, namespace_id: str, where: Optional[Dict[str, Any]] = None, limit: int = 100
    ) -> List[RAGDocument]:
        async with self._session_factory() as session:
            stmt = (
                select(
                    VectorDocument.document_id,
                    VectorDocument.document_name,
                    VectorDocument.metadata_,
                )
                .where(VectorDocument.namespace_id == namespace_id)
            )

            if where:
                for key, value in where.items():
                    stmt = stmt.where(
                        VectorDocument.metadata_[key].as_string() == str(value)
                    )

            stmt = (
                stmt.distinct(VectorDocument.document_id)
                .order_by(VectorDocument.document_id, desc(VectorDocument.updated_at))
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

        logger.info(f"Найдено {len(docs)} документов с фильтрами в {namespace_id}")
        return docs

    async def delete_document(self, namespace_id: str, document_id: str) -> bool:
        async with self._session_factory() as session:
            stmt = delete(VectorDocument).where(
                VectorDocument.namespace_id == namespace_id,
                VectorDocument.document_id == document_id,
            )
            result = await session.execute(stmt)
            await session.commit()
            deleted = result.rowcount or 0

        if deleted:
            logger.info(f"Удален документ {document_id}: {deleted} chunks")
        return deleted > 0

    # -- Search --

    @staticmethod
    def _apply_metadata_filters_to_vector_stmt(
        stmt: Select[Any],
        filters: Optional[Dict[str, Any]],
    ) -> Select[Any]:
        if not filters:
            return stmt
        for key, value in filters.items():
            if isinstance(value, dict):
                for op, op_value in value.items():
                    if op == "$eq":
                        stmt = stmt.where(
                            VectorDocument.metadata_[key].as_string() == str(op_value)
                        )
            else:
                stmt = stmt.where(
                    VectorDocument.metadata_[key].as_string() == str(value)
                )
        return stmt

    @staticmethod
    def _parse_search_channel_flags(kwargs: Dict[str, Any]) -> tuple[bool, bool]:
        ch = kwargs.get("channels")
        if isinstance(ch, dict):
            return (bool(ch.get("semantic", True)), bool(ch.get("lexical", False)))
        return (True, False)

    async def _search_semantic_ordered(
        self,
        namespace_id: str,
        query: str,
        limit: int,
        filters: Optional[Dict[str, Any]],
    ) -> List[RAGSearchResult]:
        query_embedding = await self._embedding_service.generate_embedding(query)

        async with self._session_factory() as session:
            distance_expr = VectorDocument.embedding.cosine_distance(query_embedding)
            similarity_expr = (1 - distance_expr).label("similarity")

            stmt = (
                select(VectorDocument, similarity_expr)
                .where(VectorDocument.namespace_id == namespace_id)
                .where(VectorDocument.embedding.isnot(None))
                .order_by(distance_expr)
                .limit(limit)
            )
            stmt = self._apply_metadata_filters_to_vector_stmt(stmt, filters)

            result = await session.execute(stmt)
            rows = result.all()

        search_results: List[RAGSearchResult] = []
        for rank, row in enumerate(rows, start=1):
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
                    provenance={"channel": "semantic", "rank": rank},
                )
            )
        return search_results

    async def _search_lexical_ordered(
        self,
        namespace_id: str,
        query: str,
        limit: int,
        filters: Optional[Dict[str, Any]],
    ) -> List[RAGSearchResult]:
        tsq = func.websearch_to_tsquery(literal_column("'simple'"), query)
        rank_expr = func.ts_rank_cd(VectorDocument.content_tsv, tsq).label("lex_rank")

        stmt = (
            select(VectorDocument, rank_expr)
            .where(VectorDocument.namespace_id == namespace_id)
            .where(VectorDocument.content_tsv.op("@@")(tsq))
            .order_by(rank_expr.desc())
            .limit(limit)
        )
        stmt = self._apply_metadata_filters_to_vector_stmt(stmt, filters)

        async with self._session_factory() as session:
            result = await session.execute(stmt)
            rows = result.all()

        out: List[RAGSearchResult] = []
        for rank, row in enumerate(rows, start=1):
            doc = row[0]
            lr = row[1]
            score = float(lr) if lr is not None else 0.0
            out.append(
                RAGSearchResult(
                    content=doc.content,
                    score=score,
                    document_id=doc.document_id,
                    document_name=doc.document_name or "",
                    metadata=doc.metadata_ or {},
                    namespace=namespace_id,
                    chunk_id=doc.id,
                    provenance={"channel": "lexical", "rank": rank},
                )
            )
        return out

    async def _search_hybrid_rrf(
        self,
        namespace_id: str,
        query: str,
        limit: int,
        filters: Optional[Dict[str, Any]],
        *,
        use_semantic: bool,
        use_lexical: bool,
        rrf_k: int,
        per_channel_top_k: int,
    ) -> List[RAGSearchResult]:
        if not use_semantic and not use_lexical:
            raise ValueError("Нужен хотя бы один канал поиска (semantic или lexical)")

        if use_semantic and not use_lexical:
            return await self._search_semantic_ordered(
                namespace_id, query, limit, filters
            )

        if use_lexical and not use_semantic:
            return await self._search_lexical_ordered(
                namespace_id, query, limit, filters
            )

        sem_results = await self._search_semantic_ordered(
            namespace_id, query, per_channel_top_k, filters
        )
        lex_results = await self._search_lexical_ordered(
            namespace_id, query, per_channel_top_k, filters
        )

        sem_ids = [r.chunk_id for r in sem_results if r.chunk_id]
        lex_ids = [r.chunk_id for r in lex_results if r.chunk_id]
        ranked_lists = [lst for lst in (sem_ids, lex_ids) if lst]
        if not ranked_lists:
            return []

        fused = reciprocal_rank_fusion(ranked_lists, k=rrf_k)
        by_chunk: Dict[str, RAGSearchResult] = {}
        for r in sem_results:
            if r.chunk_id:
                by_chunk[r.chunk_id] = r
        for r in lex_results:
            if r.chunk_id and r.chunk_id not in by_chunk:
                by_chunk[r.chunk_id] = r

        out: List[RAGSearchResult] = []
        for chunk_id, rrf_score in fused[:limit]:
            base = by_chunk.get(chunk_id)
            if base is None:
                continue
            sem_rank = sem_ids.index(chunk_id) + 1 if chunk_id in sem_ids else None
            lex_rank = lex_ids.index(chunk_id) + 1 if chunk_id in lex_ids else None
            out.append(
                RAGSearchResult(
                    content=base.content,
                    score=rrf_score,
                    document_id=base.document_id,
                    document_name=base.document_name,
                    metadata=base.metadata,
                    namespace=namespace_id,
                    chunk_id=chunk_id,
                    provenance={
                        "channel": "hybrid_rrf",
                        "rrf_score": rrf_score,
                        "semantic_rank": sem_rank,
                        "lexical_rank": lex_rank,
                        "rrf_k": rrf_k,
                    },
                )
            )
        return out

    async def search(
        self,
        namespace_id: str,
        query: str,
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> List[RAGSearchResult]:
        use_semantic, use_lexical = self._parse_search_channel_flags(kwargs)
        rrf_k = int(kwargs.get("rrf_k") or 60)
        pct = kwargs.get("per_channel_top_k")
        per_channel_top_k = int(pct) if pct is not None else max(limit * 3, limit + 10)

        results = await self._search_hybrid_rrf(
            namespace_id,
            query,
            limit,
            filters,
            use_semantic=use_semantic,
            use_lexical=use_lexical,
            rrf_k=rrf_k,
            per_channel_top_k=per_channel_top_k,
        )

        logger.info(f"Поиск '{query[:50]}...' в {namespace_id}: {len(results)} результатов")
        return results

    # TODO(RAG-92): переписать логику поиска по нескольким namespace (семантика/лексика/RRF, согласование с search()).
    async def search_multiple_namespaces(
        self,
        namespace_ids: List[str],
        query: str,
        limit: int = 5,
        **kwargs,
    ) -> Dict[str, List[RAGSearchResult]]:
        filters: Optional[Dict[str, Any]] = kwargs.get("filters")
        use_semantic, use_lexical = self._parse_search_channel_flags(kwargs)

        unique_ns = list(dict.fromkeys(namespace_ids))
        if not unique_ns:
            return {}
        if use_lexical:
            return await BaseRAGProvider.search_multiple_namespaces(
                self, unique_ns, query, limit, filters=filters, **kwargs
            )

        if len(unique_ns) == 1:
            ns_id = unique_ns[0]
            return {
                ns_id: await self.search(
                    ns_id, query, limit, filters=filters, **kwargs
                )
            }

        query_embedding = await self._embedding_service.generate_embedding(query)
        distance_expr = VectorDocument.embedding.cosine_distance(query_embedding)
        similarity_expr = (1 - distance_expr).label("similarity")
        row_number = (
            func.row_number()
            .over(partition_by=VectorDocument.namespace_id, order_by=distance_expr)
            .label("row_num")
        )

        inner = (
            select(VectorDocument, similarity_expr, row_number)
            .where(VectorDocument.namespace_id.in_(unique_ns))
            .where(VectorDocument.embedding.isnot(None))
        )
        inner = self._apply_metadata_filters_to_vector_stmt(inner, filters)
        ranked = inner.subquery()
        stmt = select(ranked).where(ranked.c.row_num <= limit)

        async with self._session_factory() as session:
            result = await session.execute(stmt)
            rows = result.mappings().all()

        out: Dict[str, List[RAGSearchResult]] = {ns: [] for ns in unique_ns}
        for row in rows:
            ns_id = row["namespace_id"]
            score = float(row["similarity"]) if row["similarity"] is not None else 0.0
            meta = row["metadata"]
            if meta is None:
                meta = {}
            chunk_pk = row["id"]
            out[ns_id].append(
                RAGSearchResult(
                    content=row["content"],
                    score=score,
                    document_id=row["document_id"],
                    document_name=row["document_name"] or "",
                    metadata=meta,
                    namespace=ns_id,
                    chunk_id=chunk_pk,
                    provenance={"channel": "semantic", "source": "search_multiple_namespaces"},
                )
            )

        total = sum(len(v) for v in out.values())
        logger.info(
            f"Глобальный поиск '{query[:50]}...' по {len(unique_ns)} namespace: {total} результатов"
        )
        return out
