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

_STATUS_KEYS = ("pending", "processing", "completed", "failed")

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
    async def create_status(
        cls,
        document_id: str,
        task_id: str,
        namespace_id: str,
        document_name: str,
        file_size: int | None = None,
        ttl_seconds: int = 864000,
        extra_metadata: JsonObject | None = None,
    ) -> DocumentProcessingStatus:
        """Создаёт или сбрасывает строку статуса в pending."""
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
    async def finalize_enqueued_indexing_task(
        cls,
        document_id: str,
        task_id: str,
    ) -> DocumentProcessingStatus:
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
    async def try_mark_processing(cls, document_id: str) -> None:
        now = datetime.now(timezone.utc)
        _ = await DocumentProcessingStatus.objects.filter(
            document_id=document_id,
            status="pending",
        ).update(returning=False, using="rag", status="processing", updated_at=now)

    @classmethod
    async def record_indexing_done(
        cls,
        document_id: str,
        chunks: int,
        *,
        indexing_runtime: JsonObject | None = None,
    ) -> DocumentProcessingStatus:
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
    async def record_indexing_failed(cls, document_id: str, error: str) -> None:
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
    async def update_status(
        cls,
        document_id: str,
        status: str,
        error: str | None = None,
        s3_key: str | None = None,
        s3_bucket: str | None = None,
        chunks_count: int | None = None,
    ) -> DocumentProcessingStatus:
        now = datetime.now(timezone.utc)
        async with atomic(using="rag"):
            row = await (
                DocumentProcessingStatus.objects.filter(document_id=document_id).for_update().first()
            )
            if row is None:
                raise RuntimeError(f"document status not found: {document_id}")
            row.status = status
            row.updated_at = now
            if error is not None and error != "":
                row.error_message = error
            if s3_key is not None and s3_key != "":
                row.s3_key = s3_key
            if s3_bucket is not None and s3_bucket != "":
                row.s3_bucket = s3_bucket
            if chunks_count is not None:
                row.chunks_count = chunks_count
            if status == "completed":
                row.completed_at = now
            _ = await row.save()
        logger.info("db.event", document_id=document_id, status=status)
        return row

    @classmethod
    async def get_latest_by_namespace_and_document_ids(
        cls,
        namespace_id: str,
        document_ids: list[str],
    ) -> dict[str, DocumentProcessingStatus]:
        """Строки статуса по паре (namespace_id, document_id)."""
        if not document_ids:
            return {}
        rows = await DocumentProcessingStatus.objects.filter(
            namespace_id=namespace_id,
            document_id__in=document_ids,
        ).all()
        return {row.document_id: row for row in rows}

    @classmethod
    async def count_effective_document_status_by_namespace(
        cls, namespace_id: str
    ) -> dict[str, int]:
        """Счётчики статусов одного namespace."""
        counted = await cls.count_effective_document_status_for_namespaces([namespace_id])
        return counted[namespace_id]

    @classmethod
    async def count_effective_document_status_for_namespaces(
        cls, namespace_ids: list[str]
    ) -> dict[str, dict[str, int]]:
        """По каждому namespace_id — счётчики pending, processing, completed, failed."""
        empty = {key: 0 for key in _STATUS_KEYS}
        if not namespace_ids:
            return {}
        placeholders, values = _in_clause(1, namespace_ids)
        second_start = len(values) + 1
        second_placeholders, second_values = _in_clause(second_start, namespace_ids)
        rows = await execute_raw(
            f"""
            WITH from_status AS (
              SELECT namespace_id, document_id, status
              FROM document_processing_status
              WHERE namespace_id IN ({placeholders})
            ),
            from_vectors AS (
              SELECT DISTINCT namespace_id, document_id
              FROM vector_documents
              WHERE namespace_id IN ({second_placeholders})
            ),
            merged AS (
              SELECT namespace_id, document_id, status
              FROM from_status
              UNION ALL
              SELECT from_vectors.namespace_id, from_vectors.document_id, 'completed'::text
              FROM from_vectors
              WHERE NOT EXISTS (
                SELECT 1 FROM from_status
                WHERE from_status.namespace_id = from_vectors.namespace_id
                  AND from_status.document_id = from_vectors.document_id
              )
            )
            SELECT namespace_id, status, COUNT(*)::int AS cnt
            FROM merged
            GROUP BY namespace_id, status
            """,
            [*values, *second_values],
            using="rag",
        )
        out: dict[str, dict[str, int]] = {namespace_id: dict(empty) for namespace_id in namespace_ids}
        for row in rows:
            parsed = require_json_object(row, "document_status_count")
            namespace_id = parsed["namespace_id"]
            status = parsed["status"]
            count = parsed["cnt"]
            if not isinstance(namespace_id, str) or not isinstance(status, str):
                raise TypeError("document status aggregation must return strings")
            if isinstance(count, bool) or not isinstance(count, int):
                raise TypeError("document status aggregation count must be an integer")
            if namespace_id not in out:
                continue
            if status not in out[namespace_id]:
                raise ValueError(f"Unexpected status in aggregation: {status!r}")
            out[namespace_id][status] = count
        return out

    @classmethod
    async def list_by_namespace(
        cls,
        namespace_id: str,
        status: list[str] | None = None,
        limit: int = 100,
    ) -> list[DocumentProcessingStatus]:
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
    async def count_chunks_by_namespace_and_document_ids(
        cls,
        namespace_id: str,
        document_ids: list[str],
    ) -> dict[str, int]:
        """Число чанков ``vector_documents`` на документ в namespace."""
        if not document_ids:
            return {}
        placeholders, values = _in_clause(2, document_ids)
        rows = await execute_raw(
            f"""
            SELECT document_id, COUNT(*)::int AS cnt
            FROM vector_documents
            WHERE namespace_id = $1 AND document_id IN ({placeholders})
            GROUP BY document_id
            """,
            [namespace_id, *values],
            using="rag",
        )
        counts: dict[str, int] = {}
        for row in rows:
            parsed = require_json_object(row, "chunk_count")
            document_id = parsed["document_id"]
            count = parsed["cnt"]
            if not isinstance(document_id, str):
                raise TypeError("vector_documents.document_id must be a string")
            if isinstance(count, bool) or not isinstance(count, int):
                raise TypeError("chunk count must be an integer")
            counts[document_id] = count
        return counts

    @classmethod
    async def list_expired_document_candidates(
        cls,
        *,
        utc_now: datetime,
        limit: int,
    ) -> list[tuple[str, str]]:
        """Пары (namespace_id, document_id) с истёкшим TTL."""
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
