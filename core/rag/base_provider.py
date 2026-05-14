"""
Базовый абстрактный класс для всех RAG провайдеров.
Определяет единый интерфейс работы с векторными хранилищами.
"""

import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.files.s3_client import S3ClientFactory
from core.files.types import ext_to_mime
from core.logging import get_logger
from core.rag.models import RAGDocument, RAGNamespace, RAGSearchResult

logger = get_logger(__name__)
_LOGICAL_OPERATORS: frozenset[str] = frozenset({"$and", "$or"})
_COMPARISON_OPERATORS: frozenset[str] = frozenset(
    {"$eq", "$ne", "$gt", "$gte", "$lt", "$lte", "$in", "$nin"}
)

def _is_scalar_filter_value(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    return isinstance(value, (str, int, float))

def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)

def _validate_in_values(field_name: str, operator: str, value: Any) -> None:
    if not isinstance(value, list) or not value:
        raise ValueError(f"RAG filters: {field_name}.{operator} должен быть непустым массивом")
    first = value[0]
    if isinstance(first, bool):
        expected_type = bool
    elif isinstance(first, str):
        expected_type = str
    elif _is_number(first):
        expected_type = (int, float)
    else:
        raise ValueError(
            f"RAG filters: {field_name}.{operator} поддерживает только string/number/boolean"
        )
    for item in value:
        if expected_type == (int, float):
            if not _is_number(item):
                raise ValueError(
                    f"RAG filters: {field_name}.{operator} должен содержать значения одного типа"
                )
            continue
        if not isinstance(item, expected_type):
            raise ValueError(
                f"RAG filters: {field_name}.{operator} должен содержать значения одного типа"
            )

def validate_metadata_filters(filters: Dict[str, Any]) -> None:
    """
    Валидация фильтра метаданных в формате Chroma-like ``where``.

    Поддерживаемые операторы: ``$eq/$ne/$gt/$gte/$lt/$lte/$in/$nin`` и логические ``$and/$or``.
    """

    def _validate_node(node: Any, path: str) -> None:
        if not isinstance(node, dict) or not node:
            raise ValueError(f"RAG filters: {path} должен быть непустым объектом")

        has_operator_key = any(key.startswith("$") for key in node)
        if has_operator_key:
            if len(node) != 1:
                raise ValueError(
                    f"RAG filters: {path} не может смешивать логические операторы и поля"
                )
            logical_op = next(iter(node))
            if logical_op not in _LOGICAL_OPERATORS:
                raise ValueError(f"RAG filters: неподдерживаемый оператор {logical_op}")
            nested_filters = node[logical_op]
            if not isinstance(nested_filters, list) or len(nested_filters) < 2:
                raise ValueError(
                    f"RAG filters: {logical_op} в {path} должен быть массивом минимум из 2 условий"
                )
            for index, child in enumerate(nested_filters):
                _validate_node(child, f"{path}.{logical_op}[{index}]")
            return

        for field_name, field_filter in node.items():
            if field_name.startswith("$"):
                raise ValueError(f"RAG filters: недопустимый ключ {field_name} в {path}")
            if isinstance(field_filter, dict):
                if len(field_filter) != 1:
                    raise ValueError(
                        f"RAG filters: {path}.{field_name} должен содержать ровно один оператор"
                    )
                op, op_value = next(iter(field_filter.items()))
                if op not in _COMPARISON_OPERATORS:
                    raise ValueError(
                        f"RAG filters: неподдерживаемый оператор {op} для поля {field_name}"
                    )
                if op in {"$gt", "$gte", "$lt", "$lte"}:
                    if not _is_number(op_value):
                        raise ValueError(
                            f"RAG filters: {field_name}.{op} поддерживает только number"
                        )
                elif op in {"$in", "$nin"}:
                    _validate_in_values(field_name, op, op_value)
                else:
                    if not _is_scalar_filter_value(op_value):
                        raise ValueError(
                            f"RAG filters: {field_name}.{op} поддерживает только string/number/boolean"
                        )
            else:
                if not _is_scalar_filter_value(field_filter):
                    raise ValueError(
                        f"RAG filters: {path}.{field_name} должен быть string/number/boolean "
                        "или объектом оператора"
                    )

    _validate_node(filters, "filters")

class BaseRAGProvider(ABC):
    """
    Базовый абстрактный класс для всех RAG провайдеров.
    Определяет единый интерфейс для работы с RAG хранилищем.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def _get_content_type(self, file_path: str) -> str:
        """Определяет content type по расширению файла."""
        suffix = Path(file_path).suffix.lower()
        return ext_to_mime(suffix)

    async def _upload_file_to_s3(
        self,
        file_path: str,
        namespace_id: str,
        public: bool = False,
    ) -> tuple[str, str, str]:
        """Загружает файл в S3 и возвращает (s3_key, bucket_name, original_filename)."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Файл не найден: {file_path}")

        s3_client = S3ClientFactory.create_default_client()
        prefix = "rag_public" if public else "rag"
        s3_key = f"{prefix}/{namespace_id}/{uuid.uuid4().hex[:8]}_{path.name}"

        with open(file_path, "rb") as f:
            file_data = f.read()

        try:
            await s3_client.upload_bytes(
                data=file_data,
                key=s3_key,
                content_type=self._get_content_type(file_path),
                public=public,
            )
            bucket_name = s3_client.bucket_name
        finally:
            await s3_client.close()

        logger.info(f"Файл загружен в S3: {s3_key} (public={public})")
        return s3_key, bucket_name, path.name

    async def _download_file_from_s3(
        self,
        s3_key: str,
        bucket_config_key: Optional[str] = None,
    ) -> tuple[bytes, str, str]:
        """Скачивает файл из S3 и возвращает (data, bucket_name, filename)."""
        if bucket_config_key:
            s3_client = S3ClientFactory.create_client_for_bucket(bucket_config_key)
        else:
            s3_client = S3ClientFactory.create_default_client()
        try:
            file_data = await s3_client.download_bytes(s3_key)
            filename = Path(s3_key).name
            bucket_name = s3_client.bucket_name
        finally:
            await s3_client.close()
        return file_data, bucket_name, filename

    async def _generate_signed_url(self, s3_key: str, expiration: int = 3600) -> str:
        """Генерирует временный signed URL для прямого доступа к файлу (внутренний RAG pipeline)."""
        s3_client = S3ClientFactory.create_default_client()
        try:
            signed_url = await s3_client.generate_presigned_url(key=s3_key, expiration=expiration)
        finally:
            await s3_client.close()
        return signed_url

    async def _upload_bytes_to_s3(
        self,
        file_data: bytes,
        namespace_id: str,
        filename: str,
    ) -> tuple[str, str]:
        """Загружает bytes в S3 и возвращает (s3_key, bucket_name)."""
        s3_client = S3ClientFactory.create_default_client()
        path = Path(filename)
        s3_key = f"rag/{namespace_id}/{uuid.uuid4().hex[:8]}_{path.name}"

        try:
            await s3_client.upload_bytes(
                data=file_data,
                key=s3_key,
                content_type=self._get_content_type(filename),
            )
            bucket_name = s3_client.bucket_name
        finally:
            await s3_client.close()

        logger.info(f"Файл загружен в S3: {s3_key}")
        return s3_key, bucket_name

    async def _upload_text_to_s3(
        self,
        text: str,
        namespace_id: str,
        filename: str,
    ) -> tuple[str, str]:
        """Загружает текст как файл в S3 и возвращает (s3_key, bucket_name)."""
        s3_client = S3ClientFactory.create_default_client()

        safe_name = "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_')).strip()
        if not safe_name:
            safe_name = "text"
        safe_name = safe_name[:40]

        s3_key = f"rag_text/{namespace_id}/{uuid.uuid4().hex[:8]}_{safe_name}.txt"

        try:
            await s3_client.upload_bytes(
                data=text.encode('utf-8'),
                key=s3_key,
                content_type="text/plain",
            )
            bucket_name = s3_client.bucket_name
        finally:
            await s3_client.close()

        logger.info(f"Текст загружен в S3: {s3_key}")
        return s3_key, bucket_name


    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Имя провайдера (agentset, pinecone, qdrant)"""
        pass

    @abstractmethod
    async def create_namespace(
        self,
        name: str,
        description: Optional[str] = None,
        **kwargs
    ) -> RAGNamespace:
        """Создает новый namespace для изоляции документов"""
        pass

    @abstractmethod
    async def get_namespace(self, namespace_id: str) -> Optional[RAGNamespace]:
        """Получает информацию о namespace"""
        pass

    @abstractmethod
    async def list_namespaces(self) -> List[RAGNamespace]:
        """Список всех namespaces"""
        pass

    @abstractmethod
    async def delete_namespace(self, namespace_id: str) -> bool:
        """Удаляет namespace и все его документы"""
        pass

    @abstractmethod
    async def upload_document_from_file(
        self,
        namespace_id: str,
        file_path: str,
        document_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> RAGDocument:
        """
        Загружает документ из файла.
        Провайдер сам обрабатывает парсинг, chunking, embedding.
        """
        pass

    @abstractmethod
    async def upload_document_from_s3(
        self,
        namespace_id: str,
        s3_key: str,
        document_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> RAGDocument:
        """
        Загружает документ из S3.
        Провайдер скачивает из S3 и обрабатывает.
        """
        pass

    @abstractmethod
    async def upload_document_from_text(
        self,
        namespace_id: str,
        text: str,
        document_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> RAGDocument:
        """
        Загружает текст напрямую в RAG хранилище.
        """
        pass

    @abstractmethod
    async def get_document(
        self,
        namespace_id: str,
        document_id: str
    ) -> Optional[RAGDocument]:
        """Получает информацию о документе"""
        pass

    @abstractmethod
    async def list_documents(
        self,
        namespace_id: str,
        limit: int = 100
    ) -> List[RAGDocument]:
        """Список документов в namespace"""
        pass

    @abstractmethod
    async def list_documents_with_filters(
        self,
        namespace_id: str,
        where: Optional[Dict[str, Any]] = None,
        limit: int = 100
    ) -> List[RAGDocument]:
        """Список документов с фильтрацией по metadata через where clause"""
        pass

    @abstractmethod
    async def delete_document(
        self,
        namespace_id: str,
        document_id: str
    ) -> bool:
        """Удаляет документ из namespace"""
        pass

    @abstractmethod
    async def search(
        self,
        namespace_id: str,
        query: str,
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> List[RAGSearchResult]:
        """
        Семантический поиск по документам в namespace.
        """
        pass

    async def search_multiple_namespaces(
        self,
        namespace_ids: List[str],
        query: str,
        limit: int = 5,
        **kwargs
    ) -> Dict[str, List[RAGSearchResult]]:
        """
        Поиск сразу по нескольким namespace.
        Базовая реализация вызывает search() для каждого namespace.
        """
        results = {}
        for ns_id in namespace_ids:
            ns_results = await self.search(ns_id, query, limit, **kwargs)
            results[ns_id] = ns_results
            logger.debug(f"Поиск в {ns_id}: найдено {len(ns_results)} результатов")

        return results

    async def close(self):
        """Закрывает соединения"""
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

