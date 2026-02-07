"""
RAG провайдер на базе pgvector (PostgreSQL).
Хранит векторные документы в таблице vector_documents через SQLAlchemy 2+.
"""

import logging
import os
import uuid
from typing import Any, Dict, List, Optional

import tiktoken
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.db.models import VectorDocument
from core.rag.base_provider import BaseRAGProvider
from core.rag.models import RAGDocument, RAGNamespace, RAGSearchResult
from core.rag.services.document_parser import DocumentParser
from core.rag.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class PgVectorProvider(BaseRAGProvider):
    """
    RAG провайдер на базе pgvector.
    Использует PostgreSQL + pgvector для хранения и поиска векторных документов.
    """

    DEFAULT_CHUNK_SIZE = 1000
    DEFAULT_CHUNK_OVERLAP = 100

    def __init__(self, config: Dict[str, Any], embedding_config: Optional[Dict[str, Any]] = None):
        super().__init__(config)

        db_url = config.get("db_url")
        if not db_url:
            from core.config import get_settings
            db_url = get_settings().database.url

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

        api_key = config.get("embedding_api_key")
        if not api_key:
            raise ValueError("embedding_api_key обязателен для PgVector провайдера")

        timeout = config.get("timeout", 60)

        emb_cfg = embedding_config or {}
        model = emb_cfg.get("model")
        dimension = emb_cfg.get("dimension")

        if not model:
            raise ValueError("embedding.model обязателен в конфигурации")
        if not dimension:
            raise ValueError("embedding.dimension обязателен в конфигурации")

        cost_per_1m_tokens = config.get("embedding_cost_per_1m_tokens", 5.0)
        platform_markup = config.get("embedding_platform_markup", 1.1)

        self._embedding_service = EmbeddingService(
            api_key=api_key,
            models=[model],
            timeout=timeout,
            dimension=dimension,
            cost_per_1m_tokens=cost_per_1m_tokens,
            platform_markup=platform_markup,
        )

        if os.environ.get("TESTING") == "true" or os.environ.get("RAG__EMBEDDING__MOCK") == "true":

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

            self._embedding_service.generate_embeddings = fake_generate_embeddings
            self._embedding_service.generate_embedding = fake_generate_embedding
            logger.info("PgVector провайдер: mock embeddings для тестов")

        self._parser = DocumentParser()
        self._chunk_size = config.get("chunk_size", self.DEFAULT_CHUNK_SIZE)
        self._chunk_overlap = config.get("chunk_overlap", self.DEFAULT_CHUNK_OVERLAP)
        self._tokenizer = tiktoken.get_encoding("cl100k_base")

        logger.info(f"PgVector провайдер инициализирован: model={model}, dimension={dimension}")

    @property
    def provider_name(self) -> str:
        return "pgvector"

    async def close(self):
        await self._engine.dispose()

    # -- Chunking --

    def _chunk_text(self, text_content: str) -> List[str]:
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
        s3_key, bucket_name, original_filename, _ = await self._upload_file_to_s3(
            file_path, namespace_id, public=False
        )

        doc_name = document_name or original_filename
        file_text = self._parser.parse_file(file_path)
        file_type = self._parser.get_file_type(original_filename)

        doc_metadata = metadata or {}
        doc_metadata["file_type"] = file_type
        doc_metadata["s3_key"] = s3_key
        doc_metadata["s3_bucket"] = bucket_name
        doc_metadata["original_filename"] = original_filename

        return await self._upload_text_internal(
            namespace_id=namespace_id,
            text_content=file_text,
            document_name=doc_name,
            metadata=doc_metadata,
        )

    async def upload_document_from_s3(
        self,
        namespace_id: str,
        s3_key: str,
        document_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> RAGDocument:
        file_data, bucket_name, original_filename = await self._download_file_from_s3(s3_key)

        filename = document_name or original_filename
        file_text = self._parser.parse_bytes(file_data, filename)
        file_type = self._parser.get_file_type(filename)

        doc_metadata = metadata or {}
        doc_metadata["file_type"] = file_type
        doc_metadata["s3_key"] = s3_key
        doc_metadata["s3_bucket"] = bucket_name
        doc_metadata["original_filename"] = original_filename

        logger.info(f"Документ из S3 индексируется: {s3_key}")
        return await self._upload_text_internal(
            namespace_id=namespace_id,
            text_content=file_text,
            document_name=filename,
            metadata=doc_metadata,
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

        return await self._upload_text_internal(
            namespace_id=namespace_id,
            text_content=text,
            document_name=doc_name,
            metadata=doc_metadata,
        )

    async def _upload_text_internal(
        self,
        namespace_id: str,
        text_content: str,
        document_name: str,
        metadata: Dict[str, Any],
    ) -> RAGDocument:
        """Chunk + embed + batch INSERT в vector_documents."""
        document_id = metadata.get("document_id") or str(uuid.uuid4())

        # Удаляем существующие чанки этого документа
        async with self._session_factory() as session:
            stmt = delete(VectorDocument).where(
                VectorDocument.namespace_id == namespace_id,
                VectorDocument.document_id == document_id,
            )
            result = await session.execute(stmt)
            await session.commit()
            if result.rowcount:
                logger.info(f"Удалены старые чанки документа '{document_name}': {result.rowcount}")

        chunks = self._chunk_text(text_content)
        if not chunks:
            raise ValueError("Документ пустой или не удалось разбить на chunks")

        embeddings = await self._embedding_service.generate_embeddings(chunks)

        rows = []
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            rows.append(
                VectorDocument(
                    id=f"{document_id}_{i}",
                    namespace_id=namespace_id,
                    company_id=metadata.get("company_id"),
                    document_id=document_id,
                    document_name=document_name,
                    content=chunk,
                    embedding=emb,
                    chunk_index=i,
                    total_chunks=len(chunks),
                    metadata_={
                        **metadata,
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
        return RAGDocument(
            document_id=document_id,
            name=document_name,
            namespace=namespace_id,
            status="completed",
            metadata=metadata,
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
                .distinct(VectorDocument.document_id)
            )

            if where:
                for key, value in where.items():
                    stmt = stmt.where(
                        VectorDocument.metadata_[key].as_string() == str(value)
                    )

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

    async def search(
        self,
        namespace_id: str,
        query: str,
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        **kwargs,
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

            if filters:
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

            result = await session.execute(stmt)
            rows = result.all()

        search_results = []
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
                )
            )

        logger.info(f"Поиск '{query[:50]}...' в {namespace_id}: {len(search_results)} результатов")
        return search_results
