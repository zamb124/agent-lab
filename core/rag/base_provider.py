"""
Базовый абстрактный класс для всех RAG провайдеров.
Определяет единый интерфейс работы с векторными хранилищами.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from types import TracebackType

from core.config.models import RAGProviderConfig
from core.context import get_context, require_active_company, reset_context, set_context
from core.files.create_spec import FileCreateSpec, FileSourceKind
from core.files.hooks import bind_document_placement
from core.files.models import FileRecord
from core.files.object_storage import PLATFORM_STORAGE_ID
from core.files.object_store.gate import FileGate
from core.files.object_store.pool import client_for
from core.files.object_store.resolver import resolve_for_record, resolve_for_write
from core.files.service import FilesService
from core.files.types import ext_to_mime
from core.logging import get_logger
from core.rag.models import (
    RAGDocument,
    RAGDocumentContent,
    RAGMetadata,
    RAGMetadataFilter,
    RAGNamespace,
    RAGSearchOptions,
    RAGSearchResult,
)
from core.rag.upload_profile_binding import UploadProfileBinding
from core.types import JsonValue

logger = get_logger(__name__)
_LOGICAL_OPERATORS: frozenset[str] = frozenset({"$and", "$or"})
_COMPARISON_OPERATORS: frozenset[str] = frozenset(
    {"$eq", "$ne", "$gt", "$gte", "$lt", "$lte", "$in", "$nin"}
)


def _is_scalar_filter_value(value: JsonValue) -> bool:
    if isinstance(value, bool):
        return True
    return isinstance(value, (str, int, float))


def _is_number(value: JsonValue) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_in_values(field_name: str, operator: str, value: JsonValue) -> None:
    if not isinstance(value, list) or not value:
        raise ValueError(f"RAG filters: {field_name}.{operator} must be a non-empty array")
    first = value[0]
    if isinstance(first, bool):
        for item in value:
            if not isinstance(item, bool):
                raise ValueError(
                    f"RAG filters: {field_name}.{operator} must contain values of one type"
                )
        return
    elif isinstance(first, str):
        for item in value:
            if not isinstance(item, str):
                raise ValueError(
                    f"RAG filters: {field_name}.{operator} must contain values of one type"
                )
        return
    elif _is_number(first):
        for item in value:
            if not _is_number(item):
                raise ValueError(
                    f"RAG filters: {field_name}.{operator} must contain values of one type"
                )
        return
    else:
        raise ValueError(
            f"RAG filters: {field_name}.{operator} supports only string/number/boolean"
        )


def validate_metadata_filters(filters: RAGMetadataFilter) -> None:
    """
    Валидация фильтра метаданных в формате Chroma-like ``where``.

    Поддерживаемые операторы: ``$eq/$ne/$gt/$gte/$lt/$lte/$in/$nin`` и логические ``$and/$or``.
    """

    def _validate_node(node: JsonValue, path: str) -> None:
        if not isinstance(node, dict) or not node:
            raise ValueError(f"RAG filters: {path} must be a non-empty object")

        has_operator_key = any(key.startswith("$") for key in node)
        if has_operator_key:
            if len(node) != 1:
                raise ValueError(
                    f"RAG filters: {path} cannot mix logical operators and fields"
                )
            logical_op = next(iter(node))
            if logical_op not in _LOGICAL_OPERATORS:
                raise ValueError(f"RAG filters: unsupported operator {logical_op}")
            nested_filters = node[logical_op]
            if not isinstance(nested_filters, list) or len(nested_filters) < 2:
                raise ValueError(
                    f"RAG filters: {logical_op} in {path} must be an array of at least 2 conditions"
                )
            for index, child in enumerate(nested_filters):
                _validate_node(child, f"{path}.{logical_op}[{index}]")
            return

        for field_name, field_filter in node.items():
            if field_name.startswith("$"):
                raise ValueError(f"RAG filters: invalid key {field_name} in {path}")
            if isinstance(field_filter, dict):
                if len(field_filter) != 1:
                    raise ValueError(
                        f"RAG filters: {path}.{field_name} must contain exactly one operator"
                    )
                op, op_value = next(iter(field_filter.items()))
                if op not in _COMPARISON_OPERATORS:
                    raise ValueError(
                        f"RAG filters: unsupported operator {op} for field {field_name}"
                    )
                if op in {"$gt", "$gte", "$lt", "$lte"}:
                    if not _is_number(op_value):
                        raise ValueError(
                            f"RAG filters: {field_name}.{op} supports only number"
                        )
                elif op in {"$in", "$nin"}:
                    _validate_in_values(field_name, op, op_value)
                else:
                    if not _is_scalar_filter_value(op_value):
                        raise ValueError(
                            f"RAG filters: {field_name}.{op} supports only string/number/boolean"
                        )
            else:
                if not _is_scalar_filter_value(field_filter):
                    raise ValueError(
                        f"RAG filters: {path}.{field_name} must be string/number/boolean or an operator object"
                    )

    _validate_node(filters, "filters")

class BaseRAGProvider(ABC):
    """
    Базовый абстрактный класс для всех RAG провайдеров.
    Определяет единый интерфейс для работы с RAG хранилищем.
    """

    def __init__(self, config: RAGProviderConfig) -> None:
        self.config: RAGProviderConfig = config

    def _get_content_type(self, file_path: str) -> str:
        """Определяет content type по расширению файла."""
        suffix = Path(file_path).suffix.lower()
        return ext_to_mime(suffix)

    def _rag_files(self) -> FilesService:
        return FilesService(
            files_route_segment="rag",
            docs_bind_hook=bind_document_placement,
        )

    async def _store_rag_bytes(
        self,
        data: bytes,
        *,
        namespace_id: str,
        original_name: str,
        content_type: str,
        is_public: bool,
    ) -> FileRecord:
        spec = FileCreateSpec.model_validate(
            {
                "source_kind": "rag_document",
                "source_ref": {"namespace_id": namespace_id},
                "retention": {"kind": "rag_document"},
                "post_create": {"is_public": is_public},
            }
        )
        token = None
        context = get_context()
        if context is not None and context.active_namespace != namespace_id:
            token = set_context(context.model_copy(update={"active_namespace": namespace_id}))
        try:
            return await self._rag_files().create(
                spec,
                data,
                original_name=original_name,
                content_type=content_type,
            )
        finally:
            if token is not None:
                reset_context(token)

    async def _upload_file_to_s3(
        self,
        file_path: str,
        namespace_id: str,
        public: bool = False,
    ) -> FileRecord:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        data = path.read_bytes()
        record = await self._store_rag_bytes(
            data,
            namespace_id=namespace_id,
            original_name=path.name,
            content_type=self._get_content_type(file_path),
            is_public=public,
        )
        logger.info("rag.file.stored", file_id=record.file_id, public=public)
        return record

    async def _download_file_from_s3(
        self,
        s3_key: str,
        bucket_config_key: str | None = None,
    ) -> tuple[bytes, str, str]:
        """Скачивает файл из S3 и возвращает (data, bucket_name, filename)."""
        company_id = require_active_company().company_id
        if bucket_config_key:
            resolved = await resolve_for_write(company_id, FileSourceKind.RAG_DOCUMENT)
            if bucket_config_key not in (resolved.storage_id, resolved.bucket_name, PLATFORM_STORAGE_ID):
                raise ValueError(f"unknown storage for RAG download: {bucket_config_key}")
            s3_client = await client_for(resolved)
            storage_id = resolved.storage_id
        else:
            resolved, s3_client = await FileGate().client_for_write(
                company_id,
                FileSourceKind.RAG_DOCUMENT,
            )
            storage_id = resolved.storage_id
        file_data = await s3_client.download_bytes(s3_key)
        filename = Path(s3_key).name
        return file_data, storage_id, filename

    async def _signed_url_for_file(self, file_id: str, expiration: int = 3600) -> str:
        """Временный URL для внешнего индексатора. В метаданные чанка не пишется."""
        company_id = require_active_company().company_id
        record = await self._rag_files().get(file_id)
        if record.company_id != company_id:
            raise ValueError(f"RAG file not found: {file_id}")
        client = await client_for(await resolve_for_record(record))
        return await client.generate_presigned_url(key=record.s3_key, expiration=expiration)

    async def _generate_signed_url(self, s3_key: str, expiration: int = 3600) -> str:
        """URL уже существующего объекта (index-file). Новые записи его не сохраняют."""
        company_id = require_active_company().company_id
        _, s3_client = await FileGate().client_for_write(company_id, FileSourceKind.RAG_DOCUMENT)
        return await s3_client.generate_presigned_url(key=s3_key, expiration=expiration)

    async def _upload_bytes_to_s3(
        self,
        file_data: bytes,
        namespace_id: str,
        filename: str,
    ) -> FileRecord:
        record = await self._store_rag_bytes(
            file_data,
            namespace_id=namespace_id,
            original_name=Path(filename).name,
            content_type=self._get_content_type(filename),
            is_public=False,
        )
        logger.info("rag.file.stored", file_id=record.file_id)
        return record

    async def _upload_text_to_s3(
        self,
        text: str,
        namespace_id: str,
        filename: str,
    ) -> FileRecord:
        safe_name = "".join(c for c in filename if c.isalnum() or c in (" ", "-", "_")).strip()
        if not safe_name:
            safe_name = "text"
        record = await self._store_rag_bytes(
            text.encode("utf-8"),
            namespace_id=namespace_id,
            original_name=f"{safe_name[:40]}.txt",
            content_type="text/plain",
            is_public=False,
        )
        logger.info("rag.file.stored", file_id=record.file_id)
        return record


    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Имя провайдера (agentset, pinecone, qdrant)"""
        pass

    @abstractmethod
    async def create_namespace(
        self,
        name: str,
        description: str | None = None,
    ) -> RAGNamespace:
        """Создает новый namespace для изоляции документов"""
        pass

    @abstractmethod
    async def get_namespace(self, namespace_id: str) -> RAGNamespace | None:
        """Получает информацию о namespace"""
        pass

    @abstractmethod
    async def list_namespaces(self) -> list[RAGNamespace]:
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
        document_name: str | None = None,
        metadata: RAGMetadata | None = None,
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
        document_name: str | None = None,
        metadata: RAGMetadata | None = None,
        *,
        upload_profile: UploadProfileBinding | None = None,
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
        document_name: str | None = None,
        metadata: RAGMetadata | None = None,
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
    ) -> RAGDocument | None:
        """Получает информацию о документе"""
        pass

    @abstractmethod
    async def get_document_content(
        self,
        namespace_id: str,
        document_id: str,
    ) -> RAGDocumentContent | None:
        """Собирает полный текст документа из чанков индекса."""
        pass

    @abstractmethod
    async def list_documents(
        self,
        namespace_id: str,
        limit: int = 100
    ) -> list[RAGDocument]:
        """Список документов в namespace"""
        pass

    @abstractmethod
    async def list_documents_with_filters(
        self,
        namespace_id: str,
        where: RAGMetadataFilter | None = None,
        limit: int = 100
    ) -> list[RAGDocument]:
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
        filters: RAGMetadataFilter | None = None,
        search_options: RAGSearchOptions | None = None,
    ) -> list[RAGSearchResult]:
        """
        Семантический поиск по документам в namespace.
        """
        pass

    async def search_multiple_namespaces(
        self,
        namespace_ids: list[str],
        query: str,
        limit: int = 5,
        filters: RAGMetadataFilter | None = None,
        search_options: RAGSearchOptions | None = None,
    ) -> dict[str, list[RAGSearchResult]]:
        """
        Поиск сразу по нескольким namespace.
        Базовая реализация вызывает search() для каждого namespace.
        """
        results: dict[str, list[RAGSearchResult]] = {}
        for ns_id in namespace_ids:
            ns_results = await self.search(
                ns_id,
                query,
                limit,
                filters=filters,
                search_options=search_options,
            )
            results[ns_id] = ns_results
            logger.debug("rag.search.namespace_hits", namespace_id=ns_id, count=len(ns_results))

        return results

    async def delete_orphan_company_chunks(self, *, limit: int) -> int:
        """Удаляет chunks без company_id, если backend хранит company-scoped chunks."""
        raise NotImplementedError(
            f"{self.provider_name} does not support orphan chunks cleanup (limit={limit})"
        )

    async def close(self) -> None:
        """Закрывает соединения"""
        pass

    async def __aenter__(self) -> "BaseRAGProvider":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()
