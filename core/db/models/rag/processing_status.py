"""Статус индексации документа."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import ClassVar

from oxyde import Field as DbField
from oxyde import Index, atomic, execute_raw

from core.logging import get_logger
from core.models.platform_model import PlatformModel
from core.types import JsonObject, JsonValue, parse_json_object, require_json_object

logger = get_logger(__name__)


def _in_clause(start: int, values: list[str]) -> tuple[str, list[str]]:
    if not values:
        raise ValueError("IN clause requires at least one value")
    placeholders = ", ".join(f"${start + index}" for index in range(len(values)))
    return placeholders, values


def _status_from_row(row: JsonObject) -> DocumentProcessingStatus:
    raw = row["document_status"]
    if isinstance(raw, str):
        payload = parse_json_object(raw, "document_status")
    else:
        payload = require_json_object(raw, "document_status")
    return DocumentProcessingStatus.model_validate(payload)



class DocumentProcessingStatus(PlatformModel):
    """Статус индексации документа. Таблица ``document_processing_status``."""

    __database_alias__: ClassVar[str | None] = "rag"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "document_processing_status"
        indexes: list[Index] = [
            Index(["namespace_id", "status"]),
        ]

    document_id: str = DbField(db_pk=True, max_length=255)
    task_id: str = DbField(db_unique=True, db_index=True, max_length=255)
    namespace_id: str = DbField(db_index=True, max_length=255)
    document_name: str = DbField(max_length=500)
    status: str = DbField(db_index=True, max_length=50)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    error_message: str | None = DbField(default=None)
    s3_key: str | None = DbField(default=None, max_length=1000)
    s3_bucket: str | None = DbField(default=None, max_length=255)
    file_size: int | None = DbField(default=None)
    chunks_count: int | None = DbField(default=None)
    completed_at: datetime | None = DbField(default=None)
    extra_metadata: JsonObject | None = DbField(default=None, db_type="JSONB")
    ttl_seconds: int = DbField(default=864000, db_default="864000")

    @classmethod
    async def upsert_pending(
        cls,
        document_id: str,
        task_id: str,
        namespace_id: str,
        document_name: str,
        file_size: int | None = None,
        ttl_seconds: int = 864000,
        extra_metadata: JsonObject | None = None,
    ) -> DocumentProcessingStatus:
        """Вставляет pending или сбрасывает существующую строку в pending: чистит ошибку, S3, chunks_count и completed_at, сливает extra_metadata. ttl_seconds < 0 — ValueError. После записи строки нет — RuntimeError."""
        if ttl_seconds < 0:
            raise ValueError("ttl_seconds cannot be negative")
        now = datetime.now(timezone.utc)
        incoming = dict(extra_metadata) if extra_metadata is not None else {}
        async with atomic(using="rag"):
            existing = await (
                DocumentProcessingStatus.objects.filter(document_id=document_id).for_update().first()
            )
            merged = incoming
            if existing is not None and existing.extra_metadata is not None:
                merged = {**existing.extra_metadata, **incoming}
            if existing is None:
                row = DocumentProcessingStatus(
                    document_id=document_id,
                    task_id=task_id,
                    namespace_id=namespace_id,
                    document_name=document_name,
                    status="pending",
                    created_at=now,
                    updated_at=now,
                    file_size=file_size,
                    ttl_seconds=ttl_seconds,
                    extra_metadata=merged if merged else None,
                )
                _ = await DocumentProcessingStatus.objects.create(instance=row)
            else:
                existing.task_id = task_id
                existing.namespace_id = namespace_id
                existing.document_name = document_name
                existing.status = "pending"
                existing.file_size = file_size
                existing.ttl_seconds = ttl_seconds
                existing.extra_metadata = merged if merged else None
                existing.updated_at = now
                existing.completed_at = None
                existing.error_message = None
                existing.s3_key = None
                existing.s3_bucket = None
                existing.chunks_count = None
                _ = await existing.save()
        loaded = await DocumentProcessingStatus.objects.filter(document_id=document_id).first()
        if loaded is None:
            raise RuntimeError(f"document status was not stored: {document_id}")
        logger.info("db.document_id.task.pending", document_id=document_id, task=task_id)
        return loaded

    @classmethod
    async def update_task_id(
        cls,
        document_id: str,
        task_id: str,
    ) -> DocumentProcessingStatus:
        """Пишет task_id и updated_at. Пустой task_id — ValueError. Нет строки — RuntimeError."""
        if task_id == "":
            raise ValueError("task_id is required")
        now = datetime.now(timezone.utc)
        async with atomic(using="rag"):
            row = await (
                DocumentProcessingStatus.objects.filter(document_id=document_id).for_update().first()
            )
            if row is None:
                raise RuntimeError(f"document status not found: {document_id}")
            row.task_id = task_id
            row.updated_at = now
            _ = await row.save()
        logger.info("db.task_id", document_id=document_id, task_id=task_id)
        return row

    @classmethod
    async def mark_processing(cls, document_id: str) -> None:
        """Переводит pending в processing. Нет строки или статус уже не pending — ничего не меняет."""
        now = datetime.now(timezone.utc)
        _ = await DocumentProcessingStatus.objects.filter(
            document_id=document_id,
            status="pending",
        ).update(returning=False, using="rag", status="processing", updated_at=now)

    @classmethod
    async def mark_indexing_completed(
        cls,
        document_id: str,
        chunks: int,
        *,
        indexing_runtime: JsonObject | None = None,
    ) -> DocumentProcessingStatus:
        """Ставит completed, chunks_count и увеличивает indexing_run_count. Нет строки — RuntimeError. Уже failed — строка не меняется."""
        now = datetime.now(timezone.utc)
        async with atomic(using="rag"):
            row = await (
                DocumentProcessingStatus.objects.filter(document_id=document_id).for_update().first()
            )
            if row is None:
                raise RuntimeError(f"document status not found: {document_id}")
            if row.status == "failed":
                return row
            extra: JsonObject = dict(row.extra_metadata) if row.extra_metadata is not None else {}
            raw_prev_runs = extra.get("indexing_run_count", 0)
            if not isinstance(raw_prev_runs, int) or isinstance(raw_prev_runs, bool):
                raise ValueError("extra_metadata.indexing_run_count must be an integer")
            extra["indexing_run_count"] = raw_prev_runs + 1
            if indexing_runtime is not None:
                extra["indexing_runtime"] = indexing_runtime
            row.chunks_count = chunks
            row.status = "completed"
            row.completed_at = now
            row.updated_at = now
            row.extra_metadata = extra
            _ = await row.save()
        logger.info("db.event", document_id=document_id, chunks=chunks)
        return row

    @classmethod
    async def mark_indexing_failed(cls, document_id: str, error: str) -> None:
        """Ставит failed и error_message. Сообщение длиннее 5000 символов обрезается. Нет строки — ничего не меняет."""
        now = datetime.now(timezone.utc)
        message = error
        if len(message) > 5000:
            message = message[:4997] + "..."
        _ = await DocumentProcessingStatus.objects.filter(document_id=document_id).update(
            returning=False,
            using="rag",
            status="failed",
            error_message=message,
            updated_at=now,
        )
        logger.error("db.event", document_id=document_id, msg=message)

    @classmethod
    async def by_task_id(cls, task_id: str) -> DocumentProcessingStatus | None:
        if task_id == "":
            raise ValueError("task_id is required")
        return await cls.objects.filter(task_id=task_id).get_or_none()

    @classmethod
    async def found_by_namespace_and_document_ids(
        cls,
        namespace_id: str,
        document_ids: list[str],
    ) -> dict[str, DocumentProcessingStatus]:
        """Найденные строки namespace по document_id. Пустой список — {}. Чужой namespace и отсутствующие id не входят. Несколько строк одного document_id: какая осталась, не задано. Порядка нет. Пустые поля не проверяются."""
        if not document_ids:
            return {}
        rows = await DocumentProcessingStatus.objects.filter(
            namespace_id=namespace_id,
            document_id__in=document_ids,
        ).all()
        return {row.document_id: row for row in rows}

    @classmethod
    async def list_for_namespace_by_updated_at_desc(
        cls,
        namespace_id: str,
        status: list[str] | None = None,
        limit: int = 100,
    ) -> list[DocumentProcessingStatus]:
        """Строки namespace, ORDER BY updated_at DESC NULLS LAST, не больше limit. status None или [] не фильтрует."""
        params: list[str | int] = [namespace_id]
        status_sql = ""
        if status is not None and status != []:
            placeholders, values = _in_clause(2, status)
            status_sql = f" AND status IN ({placeholders})"
            params.extend(values)
        params.append(limit)
        rows = await execute_raw(
            f"""
            SELECT row_to_json(document_processing_status) AS document_status
            FROM document_processing_status
            WHERE namespace_id = $1{status_sql}
            ORDER BY updated_at DESC NULLS LAST
            LIMIT ${len(params)}
            """,
            params,
            using="rag",
        )
        return [_status_from_row(require_json_object(row, "document_status")) for row in rows]

    @classmethod
    async def list_expired_namespace_document_pairs_by_completed_at_then_anchor_at_asc(
        cls,
        *,
        utc_now: datetime,
        limit: int,
    ) -> list[tuple[str, str]]:
        """Пары (namespace_id, document_id) с истёкшим TTL. Сначала completed-статусы по completed_at, затем vector_documents без строки статуса. limit < 1 — ValueError."""
        if limit < 1:
            raise ValueError("limit must be >= 1")
        status_rows = await execute_raw(
            """
            SELECT namespace_id, document_id
            FROM document_processing_status
            WHERE status = 'completed'
              AND completed_at IS NOT NULL
              AND ttl_seconds > 0
              AND completed_at + (ttl_seconds * interval '1 second') <= $1
            ORDER BY completed_at ASC
            LIMIT $2
            """,
            [utc_now, limit],
            using="rag",
        )
        from_status = [_namespace_document_pair(row) for row in status_rows]
        remain = limit - len(from_status)
        if remain <= 0:
            return from_status
        vector_rows = await execute_raw(
            """
            WITH per_doc AS (
              SELECT namespace_id,
                     document_id,
                     MIN(created_at) AS anchor_at,
                     MIN((metadata->>'ttl_seconds')::bigint) AS ttl_eff
              FROM vector_documents
              WHERE NOT EXISTS (
                SELECT 1 FROM document_processing_status
                WHERE document_processing_status.document_id = vector_documents.document_id
              )
              GROUP BY namespace_id, document_id
            )
            SELECT namespace_id, document_id
            FROM per_doc
            WHERE ttl_eff > 0
              AND ttl_eff IS NOT NULL
              AND anchor_at + (ttl_eff * interval '1 second') <= $1
            ORDER BY anchor_at ASC
            LIMIT $2
            """,
            [utc_now, remain],
            using="rag",
        )
        return [*from_status, *[_namespace_document_pair(row) for row in vector_rows]]


def _namespace_document_pair(row: JsonValue) -> tuple[str, str]:
    parsed = require_json_object(row, "expired_document")
    namespace_id = parsed["namespace_id"]
    document_id = parsed["document_id"]
    if not isinstance(namespace_id, str) or not isinstance(document_id, str):
        raise TypeError("expired document pair must be strings")
    return namespace_id, document_id
