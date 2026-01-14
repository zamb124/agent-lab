"""
RAG провайдер на базе ChromaDB.
Подключается к Chroma Server по HTTP для работы в распределенном окружении.
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

import chromadb
import tiktoken

from ..base_provider import BaseRAGProvider
from ..models import RAGDocument, RAGNamespace, RAGSearchResult
from ..services.document_parser import DocumentParser
from ..services.embedding_service import EmbeddingService

# S3ClientFactory используется через базовый класс BaseRAGProvider

logger = logging.getLogger(__name__)


class ChromaDBRAGProvider(BaseRAGProvider):
    """
    RAG провайдер на базе ChromaDB.
    Подключается к Chroma Server по HTTP.
    Поддерживает полный синтаксис фильтров ChromaDB для интеграции с CRM.
    """

    DEFAULT_CHUNK_SIZE = 1000
    DEFAULT_CHUNK_OVERLAP = 100

    def __init__(self, config: Dict[str, Any], embedding_config: Optional[Dict[str, Any]] = None):
        import os
        super().__init__(config)

        # ENV переменные имеют приоритет над config (для Docker)
        host = os.environ.get("CHROMA_HOST") or config.get("host", "localhost")
        port = int(os.environ.get("CHROMA_PORT", 0)) or config.get("port", 8000)

        self._client = chromadb.HttpClient(host=host, port=port)

        # API ключ для embeddings берётся из провайдера
        api_key = config.get("embedding_api_key")
        if not api_key:
            raise ValueError("embedding_api_key обязателен для ChromaDB провайдера")

        timeout = config.get("timeout", 60)

        # Получаем модель из конфигурации embedding
        emb_cfg = embedding_config or {}

        model = emb_cfg.get("model")
        dimension = emb_cfg.get("dimension")

        if not model:
            raise ValueError("embedding.model обязателен в конфигурации")

        if not dimension:
            raise ValueError("embedding.dimension обязателен в конфигурации")

        models = [model]

        # Billing параметры из конфига провайдера
        cost_per_1m_tokens = config.get("embedding_cost_per_1m_tokens", 5.0)
        platform_markup = config.get("embedding_platform_markup", 1.1)

        self._embedding_service = EmbeddingService(
            api_key=api_key,
            models=models,
            timeout=timeout,
            dimension=dimension,
            cost_per_1m_tokens=cost_per_1m_tokens,
            platform_markup=platform_markup,
        )

        # В тестовом окружении используем mock embeddings
        import os

        if os.environ.get("TESTING") == "true" or os.environ.get("RAG__EMBEDDING__MOCK") == "true":

            async def fake_generate_embeddings(texts: List[str]) -> List[List[float]]:
                """Фейковые embeddings для тестов"""
                dimension = self._embedding_service.dimension or 1536
                embeddings = []
                for text in texts:
                    hash_val = hash(text)
                    embedding = [float((hash_val + i) % 100) / 100.0 for i in range(dimension)]
                    embeddings.append(embedding)
                return embeddings

            async def fake_generate_embedding(text: str) -> List[float]:
                """Один фейковый embedding для тестов"""
                result = await fake_generate_embeddings([text])
                return result[0]

            self._embedding_service.generate_embeddings = fake_generate_embeddings
            self._embedding_service.generate_embedding = fake_generate_embedding
            logger.info("ChromaDB провайдер: используются mock embeddings для тестов")

        self._parser = DocumentParser()

        self._chunk_size = config.get("chunk_size", self.DEFAULT_CHUNK_SIZE)
        self._chunk_overlap = config.get("chunk_overlap", self.DEFAULT_CHUNK_OVERLAP)

        self._tokenizer = tiktoken.get_encoding("cl100k_base")

        logger.info(f"ChromaDB провайдер инициализирован: {host}:{port}, models={models}")

    @property
    def provider_name(self) -> str:
        return "chromadb"

    async def close(self):
        pass

    def _chunk_text(self, text: str) -> List[str]:
        """
        Разбивает текст на chunks по токенам.

        Args:
            text: Исходный текст

        Returns:
            Список chunks
        """
        tokens = self._tokenizer.encode(text)
        chunks = []

        start = 0
        while start < len(tokens):
            end = start + self._chunk_size
            chunk_tokens = tokens[start:end]
            chunk_text = self._tokenizer.decode(chunk_tokens)
            chunks.append(chunk_text)
            start = end - self._chunk_overlap

        return chunks

    async def create_namespace(
        self, name: str, description: Optional[str] = None, **kwargs
    ) -> RAGNamespace:
        """Создает namespace (коллекцию) в ChromaDB"""
        collection_name = self._get_collection_name(name)

        metadata = {}
        if description:
            metadata["description"] = description

        collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata=metadata or None,
        )

        logger.info(f"Создан namespace: {collection_name}")

        return RAGNamespace(
            namespace_id=collection_name,
            name=name,
            description=description,
            document_count=collection.count(),
            metadata={"chromadb_name": collection_name},
        )

    async def get_namespace(self, namespace_id: str) -> Optional[RAGNamespace]:
        """Получает namespace из ChromaDB"""
        try:
            collection = self._client.get_collection(name=namespace_id)
            return RAGNamespace(
                namespace_id=namespace_id,
                name=namespace_id,
                document_count=collection.count(),
                metadata=collection.metadata or {},
            )
        except Exception:
            return None

    async def list_namespaces(self) -> List[RAGNamespace]:
        """Список всех namespaces"""
        collections = self._client.list_collections()

        namespaces = []
        for col in collections:
            try:
                namespaces.append(
                    RAGNamespace(
                        namespace_id=col.name,
                        name=col.name,
                        document_count=col.count(),
                        metadata=col.metadata or {},
                    )
                )
            except Exception:
                # Коллекция могла быть удалена между list_collections() и count()
                pass

        return namespaces

    async def delete_namespace(self, namespace_id: str) -> bool:
        """Удаляет namespace"""
        try:
            self._client.delete_collection(name=self._get_collection_name(namespace_id))
            logger.info(f"Удален namespace: {namespace_id}")
            return True
        except Exception:
            return False

    async def upload_document_from_file(
        self,
        namespace_id: str,
        file_path: str,
        document_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> RAGDocument:
        """
        Загружает документ из локального файла.

        Стратегия (совместимо с Agentset):
        1. Загружаем оригинал файла в S3
        2. Парсим содержимое
        3. Индексируем в ChromaDB
        4. Сохраняем s3_key в metadata для доступа к оригиналу
        """
        s3_key, bucket_name, original_filename, _ = await self._upload_file_to_s3(
            file_path, namespace_id, public=False
        )

        doc_name = document_name or original_filename

        text = self._parser.parse_file(file_path)
        file_type = self._parser.get_file_type(original_filename)

        doc_metadata = metadata or {}
        doc_metadata["file_type"] = file_type
        doc_metadata["s3_key"] = s3_key
        doc_metadata["s3_bucket"] = bucket_name
        doc_metadata["original_filename"] = original_filename

        return await self._upload_text_internal(
            namespace_id=namespace_id,
            text=text,
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
        """
        Загружает документ из S3.

        Стратегия (совместимо с Agentset):
        1. Скачиваем файл из S3 для парсинга
        2. Парсим содержимое
        3. Индексируем в ChromaDB
        4. Сохраняем s3_key в metadata (оригинал остаётся в S3)
        """
        file_data, bucket_name, original_filename = await self._download_file_from_s3(s3_key)

        filename = document_name or original_filename

        text = self._parser.parse_bytes(file_data, filename)
        file_type = self._parser.get_file_type(filename)

        doc_metadata = metadata or {}
        doc_metadata["file_type"] = file_type
        doc_metadata["s3_key"] = s3_key
        doc_metadata["s3_bucket"] = bucket_name
        doc_metadata["original_filename"] = original_filename

        logger.info(f"Документ из S3 индексируется: {s3_key}")

        return await self._upload_text_internal(
            namespace_id=namespace_id,
            text=text,
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
        """Загружает текст напрямую"""
        doc_name = document_name or f"text_{uuid.uuid4().hex[:8]}"

        doc_metadata = metadata or {}
        doc_metadata["file_type"] = "text"

        return await self._upload_text_internal(
            namespace_id=namespace_id,
            text=text,
            document_name=doc_name,
            metadata=doc_metadata,
        )

    async def _upload_text_internal(
        self,
        namespace_id: str,
        text: str,
        document_name: str,
        metadata: Dict[str, Any],
    ) -> RAGDocument:
        """Внутренний метод загрузки текста с chunking и embedding"""
        collection_name = self._get_collection_name(namespace_id)
        collection = self._client.get_or_create_collection(name=collection_name)

        # Удаляем существующий документ с таким же именем
        existing = collection.get(
            where={"document_name": document_name},
            include=[],
        )
        if existing["ids"]:
            collection.delete(ids=existing["ids"])
            logger.info(
                f"Удален существующий документ '{document_name}': {len(existing['ids'])} chunks"
            )

        # Используем document_id из metadata если передан, иначе генерируем новый
        document_id = metadata.get("document_id") or str(uuid.uuid4())

        chunks = self._chunk_text(text)
        if not chunks:
            raise ValueError("Документ пустой или не удалось разбить на chunks")

        embeddings = await self._embedding_service.generate_embeddings(chunks)

        ids = [f"{document_id}_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                **metadata,
                "document_id": document_id,
                "document_name": document_name,
                "chunk_index": i,
                "total_chunks": len(chunks),
            }
            for i in range(len(chunks))
        ]

        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadatas,
        )

        logger.info(f"Загружен документ '{document_name}' в {namespace_id}: {len(chunks)} chunks")

        return RAGDocument(
            document_id=document_id,
            name=document_name,
            namespace=namespace_id,
            status="completed",
            metadata=metadata,
        )

    async def get_document(self, namespace_id: str, document_id: str) -> Optional[RAGDocument]:
        """Получает информацию о документе"""
        collection_name = self._get_collection_name(namespace_id)
        collection = self._client.get_or_create_collection(name=collection_name)

        results = collection.get(
            where={"document_id": document_id},
            limit=1,
            include=["metadatas"],
        )

        if not results["ids"]:
            return None

        metadata = results["metadatas"][0] if results["metadatas"] else {}

        return RAGDocument(
            document_id=document_id,
            name=metadata.get("document_name", ""),
            namespace=namespace_id,
            status="completed",
            metadata=metadata,
        )

    async def list_documents(self, namespace_id: str, limit: int = 100) -> List[RAGDocument]:
        """Список документов в namespace"""
        collection_name = self._get_collection_name(namespace_id)
        collection = self._client.get_or_create_collection(name=collection_name)

        results = collection.get(
            include=["metadatas"],
            limit=limit * 10,
        )

        seen_docs = {}
        for metadata in results["metadatas"] or []:
            doc_id = metadata.get("document_id")
            if doc_id and doc_id not in seen_docs:
                seen_docs[doc_id] = RAGDocument(
                    document_id=doc_id,
                    name=metadata.get("document_name", ""),
                    namespace=namespace_id,
                    status="completed",
                    metadata={
                        k: v
                        for k, v in metadata.items()
                        if k not in ("document_id", "document_name", "chunk_index", "total_chunks")
                    },
                )

        return list(seen_docs.values())[:limit]

    async def list_documents_with_filters(
        self, namespace_id: str, where: Optional[Dict[str, Any]] = None, limit: int = 100
    ) -> List[RAGDocument]:
        """Список документов с фильтрацией по metadata через ChromaDB where clause"""
        collection_name = self._get_collection_name(namespace_id)
        collection = self._client.get_or_create_collection(name=collection_name)

        get_params = {
            "include": ["metadatas"],
            "limit": limit * 10,
        }

        if where:
            get_params["where"] = where

        results = collection.get(**get_params)

        seen_docs = {}
        for metadata in results["metadatas"] or []:
            doc_id = metadata.get("document_id")
            if doc_id and doc_id not in seen_docs:
                seen_docs[doc_id] = RAGDocument(
                    document_id=doc_id,
                    name=metadata.get("document_name", ""),
                    namespace=namespace_id,
                    status="completed",
                    metadata={
                        k: v
                        for k, v in metadata.items()
                        if k not in ("document_id", "document_name", "chunk_index", "total_chunks")
                    },
                )

        logger.info(f"Найдено {len(seen_docs)} документов с фильтрами {where} в {namespace_id}")
        return list(seen_docs.values())[:limit]

    async def delete_document(self, namespace_id: str, document_id: str) -> bool:
        """Удаляет документ (все его chunks)"""
        collection_name = self._get_collection_name(namespace_id)
        collection = self._client.get_or_create_collection(name=collection_name)

        results = collection.get(
            where={"document_id": document_id},
            include=[],
        )

        if not results["ids"]:
            return False

        collection.delete(ids=results["ids"])
        logger.info(f"Удален документ {document_id}: {len(results['ids'])} chunks")
        return True

    async def search(
        self,
        namespace_id: str,
        query: str,
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> List[RAGSearchResult]:
        """Семантический поиск"""
        query_embedding = await self._embedding_service.generate_embedding(query)

        collection_name = self._get_collection_name(namespace_id)
        collection = self._client.get_or_create_collection(name=collection_name)

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=limit,
            where=filters,
            include=["documents", "metadatas", "distances"],
        )

        search_results = []
        if results["ids"] and results["ids"][0]:
            for i, chunk_id in enumerate(results["ids"][0]):
                metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results["distances"] else 0
                # Конвертируем distance в similarity score
                # Используем формулу 1 / (1 + distance) чтобы всегда получать положительное значение
                # distance=0 -> score=1, distance=infinity -> score=0
                score = 1.0 / (1.0 + distance)

                search_results.append(
                    RAGSearchResult(
                        content=results["documents"][0][i] if results["documents"] else "",
                        score=score,
                        document_id=metadata.get("document_id", ""),
                        document_name=metadata.get("document_name", ""),
                        metadata=metadata,
                        namespace=namespace_id,
                    )
                )

        logger.info(f"Поиск '{query[:50]}...' в {namespace_id}: {len(search_results)} результатов")
        return search_results

    async def query_raw(
        self,
        namespace_id: str,
        query_embeddings: Optional[List[List[float]]] = None,
        query_texts: Optional[List[str]] = None,
        n_results: int = 10,
        where: Optional[Dict[str, Any]] = None,
        where_document: Optional[Dict[str, Any]] = None,
        include: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Прямой доступ к ChromaDB query с полным синтаксисом фильтров.
        Для интеграции с CRM (splink).

        Поддерживаемые операторы where:
            - $eq, $ne: равенство/неравенство
            - $gt, $gte, $lt, $lte: сравнения
            - $in, $nin: в списке / не в списке
            - $and, $or: логические операторы

        Поддерживаемые операторы where_document:
            - $contains: содержит текст

        Args:
            namespace_id: ID коллекции
            query_embeddings: Векторы для поиска
            query_texts: Тексты для поиска (будут преобразованы в embeddings)
            n_results: Количество результатов
            where: Фильтр по metadata
            where_document: Фильтр по содержимому документа
            include: Что включить в ответ (documents, metadatas, distances, embeddings)

        Returns:
            Сырой ответ от ChromaDB
        """
        collection_name = self._get_collection_name(namespace_id)
        collection = self._client.get_or_create_collection(name=collection_name)

        if query_texts and not query_embeddings:
            query_embeddings = await self._embedding_service.generate_embeddings(query_texts)

        include = include or ["documents", "metadatas", "distances"]

        return collection.query(
            query_embeddings=query_embeddings,
            n_results=n_results,
            where=where,
            where_document=where_document,
            include=include,
        )

    async def get_raw(
        self,
        namespace_id: str,
        ids: Optional[List[str]] = None,
        where: Optional[Dict[str, Any]] = None,
        where_document: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
        include: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Прямой доступ к ChromaDB get с полным синтаксисом фильтров.
        Для интеграции с CRM (splink).

        Args:
            namespace_id: ID коллекции
            ids: Список ID для получения
            where: Фильтр по metadata
            where_document: Фильтр по содержимому документа
            limit: Лимит результатов
            include: Что включить в ответ

        Returns:
            Сырой ответ от ChromaDB
        """
        collection_name = self._get_collection_name(namespace_id)
        collection = self._client.get_or_create_collection(name=collection_name)

        include = include or ["documents", "metadatas"]

        return collection.get(
            ids=ids,
            where=where,
            where_document=where_document,
            limit=limit,
            include=include,
        )

    async def add_raw(
        self,
        namespace_id: str,
        ids: List[str],
        embeddings: Optional[List[List[float]]] = None,
        documents: Optional[List[str]] = None,
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """
        Прямое добавление в ChromaDB без chunking.
        Для интеграции с CRM (splink) - добавление entities.

        Args:
            namespace_id: ID коллекции
            ids: Список ID
            embeddings: Векторы (если None - генерируются из documents)
            documents: Тексты документов
            metadatas: Метаданные
        """
        collection_name = self._get_collection_name(namespace_id)
        collection = self._client.get_or_create_collection(name=collection_name)

        if documents and not embeddings:
            embeddings = await self._embedding_service.generate_embeddings(documents)

        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

        logger.info(f"Добавлено {len(ids)} записей в {namespace_id}")

    async def update_raw(
        self,
        namespace_id: str,
        ids: List[str],
        embeddings: Optional[List[List[float]]] = None,
        documents: Optional[List[str]] = None,
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """
        Прямое обновление в ChromaDB.
        Для интеграции с CRM (splink).
        """
        collection_name = self._get_collection_name(namespace_id)
        collection = self._client.get_or_create_collection(name=collection_name)

        if documents and not embeddings:
            embeddings = await self._embedding_service.generate_embeddings(documents)

        collection.update(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

        logger.info(f"Обновлено {len(ids)} записей в {namespace_id}")

    async def delete_raw(
        self,
        namespace_id: str,
        ids: Optional[List[str]] = None,
        where: Optional[Dict[str, Any]] = None,
        where_document: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Прямое удаление из ChromaDB с фильтрами.
        Для интеграции с CRM (splink).
        """
        collection_name = self._get_collection_name(namespace_id)
        collection = self._client.get_or_create_collection(name=collection_name)

        collection.delete(
            ids=ids,
            where=where,
            where_document=where_document,
        )

        logger.info(f"Удалены записи из {namespace_id}")

    def _get_collection_name(self, namespace_name: str) -> str:
        """
        Возвращает sanitized имя коллекции = namespace_name.

        Company изоляция через metadata {"company_id": "..."}, не через имя коллекции.
        Это позволяет cross-company access через AccessGrants.

        Args:
            namespace_name: Имя namespace

        Returns:
            Sanitized имя коллекции
        """
        return self._sanitize_collection_name(namespace_name)

    def _sanitize_collection_name(self, name: str) -> str:
        """
        Приводит имя к допустимому формату для ChromaDB.
        ChromaDB требует: 3-63 символа, буквы/цифры/подчеркивания/дефисы.
        """
        sanitized = "".join(c if c.isalnum() or c in "_-" else "_" for c in name)

        sanitized = sanitized.strip("_-")

        if len(sanitized) < 3:
            sanitized = f"ns_{sanitized}"
        elif len(sanitized) > 63:
            sanitized = sanitized[:63]

        if not sanitized[0].isalnum():
            sanitized = f"n{sanitized}"

        return sanitized
