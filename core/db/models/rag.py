"""Таблицы ``platform_rag``: статус индексации и чанки ``vector_documents``."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index, atomic, execute_raw

from core.logging import get_logger
from core.models.platform_model import PlatformModel
from core.types import JsonObject, parse_json_object, require_json_object

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


def _namespace_document_pair(row: object) -> tuple[str, str]:
    parsed = require_json_object(row, "expired_document")
    namespace_id = parsed["namespace_id"]
    document_id = parsed["document_id"]
    if not isinstance(namespace_id, str) or not isinstance(document_id, str):
        raise TypeError("expired document pair must be strings")
    return namespace_id, document_id


class VectorDocument(PlatformModel):
    """Чанк семантического индекса. Таблица ``vector_documents``.

    ``content_tsv`` — generated-колонка ``tsvector`` и в INSERT не пишется.
    ``embedding`` — ``vector(1024)``. Поиск по косинусу и FTS идёт сырым SQL.
    """

    __database_alias__: ClassVar[str | None] = "rag"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "vector_documents"
        indexes: list[Index] = [
            Index(["namespace_id", "company_id"]),
            Index(["content_tsv"], method="gin"),
        ]

    id: str = DbField(db_pk=True, max_length=100)
    namespace_id: str = DbField(db_index=True, max_length=255)
    document_id: str = DbField(db_index=True, max_length=255)
    content: str = DbField(db_type="TEXT")
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    company_id: str | None = DbField(default=None, db_index=True, max_length=100)
    document_name: str | None = DbField(default=None, max_length=500)
    embedding: list[float] | None = DbField(default=None, db_type="vector(1024)")
    embedding_model: str | None = DbField(default=None, db_index=True, max_length=255)
    chunk_index: int = DbField(default=0)
    total_chunks: int = DbField(default=1)
    metadata: JsonObject = DbField(default_factory=dict, db_type="JSONB")
    content_tsv: str | None = DbField(default=None, db_type="tsvector")

    @classmethod
    async def count_in_namespace(cls, namespace_id: str) -> int:
        return await cls.objects.filter(namespace_id=namespace_id).count()

    @classmethod
    async def namespace_document_counts(cls) -> list[tuple[str, int]]:
        rows = await execute_raw(
            """
            SELECT namespace_id, COUNT(*)::int AS doc_count
            FROM vector_documents
            GROUP BY namespace_id
            """,
            using="rag",
        )
        counts: list[tuple[str, int]] = []
        for row in rows:
            parsed = require_json_object(row, "rag_namespace")
            namespace_id = parsed["namespace_id"]
            doc_count = parsed["doc_count"]
            if not isinstance(namespace_id, str):
                raise TypeError("vector_documents.namespace_id must be a string")
            if isinstance(doc_count, bool) or not isinstance(doc_count, int):
                raise TypeError("namespace document count must be an integer")
            counts.append((namespace_id, doc_count))
        return counts

    @classmethod
    async def delete_namespace_chunks(cls, namespace_id: str) -> int:
        return await cls.objects.filter(namespace_id=namespace_id).delete(using="rag")

    @classmethod
    async def delete_document_chunks(cls, namespace_id: str, document_id: str) -> int:
        return await cls.objects.filter(
            namespace_id=namespace_id,
            document_id=document_id,
        ).delete(using="rag")

    @classmethod
    async def replace_document_chunks(cls, rows: list[Self]) -> int:
        if len(rows) == 0:
            raise ValueError("replace_document_chunks requires at least one chunk")
        namespace_id = rows[0].namespace_id
        document_id = rows[0].document_id
        async with atomic(using="rag"):
            _ = await execute_raw(
                "SELECT pg_advisory_xact_lock(hashtext($1))",
                [f"{namespace_id}:{document_id}"],
                using="rag",
            )
            deleted_count = await cls.delete_document_chunks(namespace_id, document_id)
            for row in rows:
                embedding = None if row.embedding is None else _vector_literal(row.embedding)
                _ = await execute_raw(
                    """
                    INSERT INTO vector_documents (
                        id, namespace_id, company_id, document_id, document_name, content,
                        embedding, embedding_model, chunk_index, total_chunks, metadata,
                        created_at, updated_at
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7::vector, $8, $9, $10, $11::jsonb, $12, $13
                    )
                    """,
                    [
                        row.id,
                        row.namespace_id,
                        row.company_id,
                        row.document_id,
                        row.document_name,
                        row.content,
                        embedding,
                        row.embedding_model,
                        row.chunk_index,
                        row.total_chunks,
                        json.dumps(row.metadata),
                        row.created_at,
                        row.updated_at,
                    ],
                    using="rag",
                )
        return deleted_count

    @classmethod
    async def chunks_for_document(
        cls,
        namespace_id: str,
        document_id: str,
        *,
        limit: int | None = None,
    ) -> list[VectorDocument]:
        sql = (
            f"SELECT {_CHUNK_COLUMNS} FROM vector_documents "
            "WHERE namespace_id = $1 AND document_id = $2 ORDER BY chunk_index ASC"
        )
        params: list[str | int] = [namespace_id, document_id]
        if limit is not None:
            sql = f"{sql} LIMIT $3"
            params.append(limit)
        rows = await execute_raw(sql, params, using="rag")
        return [_chunk_from_row(row) for row in rows]

    @classmethod
    async def distinct_documents(cls, namespace_id: str, *, limit: int) -> list[VectorDocument]:
        rows = await execute_raw(
            f"""
            SELECT DISTINCT ON (document_id) {_CHUNK_COLUMNS}
            FROM vector_documents
            WHERE namespace_id = $1
            ORDER BY document_id
            LIMIT $2
            """,
            [namespace_id, limit],
            using="rag",
        )
        return [_chunk_from_row(row) for row in rows]

    @classmethod
    async def distinct_documents_where(
        cls,
        namespace_id: str,
        *,
        filter_sql: str,
        filter_params: list[str | int | float | bool | datetime | None],
        limit: int,
        limit_placeholder: int,
    ) -> list[VectorDocument]:
        rows = await execute_raw(
            f"""
            SELECT DISTINCT ON (document_id) {_CHUNK_COLUMNS}
            FROM vector_documents
            WHERE namespace_id = $1{filter_sql}
            ORDER BY document_id
            LIMIT ${limit_placeholder}
            """,
            [namespace_id, *filter_params, limit],
            using="rag",
        )
        return [_chunk_from_row(row) for row in rows]

    @classmethod
    async def semantic_index_counts(
        cls,
        keys: list[tuple[str, str, str]],
    ) -> list[tuple[str, str, str, int, int]]:
        if len(keys) == 0:
            return []
        tuple_sql: list[str] = []
        params: list[str] = []
        for namespace_id, document_id, company_id in keys:
            base = len(params)
            tuple_sql.append(f"(${base + 1}, ${base + 2}, ${base + 3})")
            params.extend([namespace_id, document_id, company_id])
        rows = await execute_raw(
            f"""
            SELECT namespace_id, document_id, company_id,
                   COUNT(*)::int AS chunk_count,
                   COALESCE(SUM(CASE WHEN embedding IS NULL THEN 1 ELSE 0 END), 0)::int AS null_chunks
            FROM vector_documents
            WHERE (namespace_id, document_id, company_id) IN ({", ".join(tuple_sql)})
            GROUP BY namespace_id, document_id, company_id
            """,
            params,
            using="rag",
        )
        counts: list[tuple[str, str, str, int, int]] = []
        for row in rows:
            parsed = require_json_object(row, "semantic_index_status")
            namespace_id = parsed["namespace_id"]
            document_id = parsed["document_id"]
            company_id = parsed["company_id"]
            chunk_count = parsed["chunk_count"]
            null_chunks = parsed["null_chunks"]
            if not isinstance(namespace_id, str) or not isinstance(document_id, str):
                raise TypeError("semantic index status ids must be strings")
            if not isinstance(company_id, str):
                continue
            if isinstance(chunk_count, bool) or not isinstance(chunk_count, int):
                raise TypeError("chunk_count must be an integer")
            if isinstance(null_chunks, bool) or not isinstance(null_chunks, int):
                raise TypeError("null_chunks must be an integer")
            counts.append((namespace_id, document_id, company_id, chunk_count, null_chunks))
        return counts

    @classmethod
    async def stale_chunks_for_reembed(
        cls,
        *,
        limit: int,
        target_embedding_model: str,
    ) -> list[tuple[str, str, str]]:
        if limit <= 0:
            raise ValueError("fetch_stale_chunks_for_reembed: limit must be positive")
        rows = await execute_raw(
            """
            SELECT id, content, company_id
            FROM (
                SELECT id, content, company_id,
                       row_number() OVER (PARTITION BY company_id ORDER BY id ASC) AS company_rank
                FROM vector_documents
                WHERE (embedding_model IS NULL OR embedding_model <> $1)
                  AND content IS NOT NULL
                  AND content <> ''
                  AND company_id IS NOT NULL
                  AND company_id <> ''
            ) ranked
            ORDER BY company_rank ASC, company_id ASC, id ASC
            LIMIT $2
            """,
            [target_embedding_model, limit],
            using="rag",
        )
        stale_chunks: list[tuple[str, str, str]] = []
        for row in rows:
            parsed = require_json_object(row, "stale_chunk")
            chunk_id = parsed["id"]
            content = parsed["content"]
            company_id = parsed["company_id"]
            if not isinstance(chunk_id, str) or not isinstance(content, str) or not isinstance(company_id, str):
                raise TypeError("stale chunk row must contain strings")
            if company_id == "":
                raise ValueError("fetch_stale_chunks_for_reembed returned chunk without company_id")
            stale_chunks.append((chunk_id, content, company_id))
        return stale_chunks

    @classmethod
    async def write_reembed_embeddings(
        cls,
        doc_embeddings: list[tuple[str, list[float]]],
        target_embedding_model: str,
    ) -> int:
        if len(doc_embeddings) == 0:
            return 0
        updated = 0
        now = datetime.now(timezone.utc)
        async with atomic(using="rag"):
            for chunk_id, embedding in doc_embeddings:
                rows = await execute_raw(
                    """
                    UPDATE vector_documents
                    SET embedding = $2::vector, embedding_model = $3, updated_at = $4
                    WHERE id = $1
                    RETURNING id
                    """,
                    [chunk_id, _vector_literal(embedding), target_embedding_model, now],
                    using="rag",
                )
                updated += len(rows)
        return updated

    @classmethod
    async def delete_orphan_company_chunks(cls, *, limit: int) -> int:
        if limit <= 0:
            raise ValueError("delete_orphan_company_chunks: limit must be positive")
        async with atomic(using="rag"):
            rows = await execute_raw(
                """
                SELECT id
                FROM vector_documents
                WHERE company_id IS NULL OR company_id = ''
                ORDER BY id ASC
                LIMIT $1
                """,
                [limit],
                using="rag",
            )
            chunk_ids: list[str] = []
            for row in rows:
                parsed = require_json_object(row, "orphan_chunk")
                chunk_id = parsed["id"]
                if not isinstance(chunk_id, str):
                    raise TypeError("vector_documents.id must be a string")
                chunk_ids.append(chunk_id)
            if len(chunk_ids) == 0:
                return 0
            placeholders = ", ".join(f"${index}" for index in range(1, len(chunk_ids) + 1))
            _ = await execute_raw(
                f"DELETE FROM vector_documents WHERE id IN ({placeholders})",
                chunk_ids,
                using="rag",
            )
        return len(chunk_ids)

    @classmethod
    async def hybrid_channel_ids(
        cls,
        *,
        namespace_id: str,
        embedding_model: str,
        query_embedding: list[float],
        query: str,
        lexical_config: str,
        semantic_filter_sql: str,
        semantic_params: list[str | int | float | bool | datetime | None],
        semantic_limit_placeholder: int,
        lexical_filter_sql: str,
        lexical_params: list[str | int | float | bool | datetime | None],
        lexical_limit_placeholder: int,
        per_channel: int,
    ) -> tuple[list[str], list[str]]:
        async with atomic(using="rag"):
            _ = await execute_raw("SET hnsw.iterative_scan = relaxed_order", using="rag")
            semantic_rows = await execute_raw(
                f"""
                SELECT id, (1 - (embedding <=> $1::vector)) AS similarity
                FROM vector_documents
                WHERE namespace_id = $2
                  AND embedding IS NOT NULL
                  AND embedding_model = $3
                  {semantic_filter_sql}
                ORDER BY embedding <=> $1::vector
                LIMIT ${semantic_limit_placeholder}
                """,
                [
                    _vector_literal(query_embedding),
                    namespace_id,
                    embedding_model,
                    *semantic_params,
                    per_channel,
                ],
                using="rag",
            )
            lexical_rows = await execute_raw(
                f"""
                SELECT id
                FROM vector_documents
                WHERE namespace_id = $3
                  AND content_tsv @@ websearch_to_tsquery($1::regconfig, $2)
                  {lexical_filter_sql}
                ORDER BY ts_rank_cd(content_tsv, websearch_to_tsquery($1::regconfig, $2)) DESC
                LIMIT ${lexical_limit_placeholder}
                """,
                [lexical_config, query, namespace_id, *lexical_params, per_channel],
                using="rag",
            )
        return ([_row_id(row) for row in semantic_rows], [_row_id(row) for row in lexical_rows])

    @classmethod
    async def semantic_hits(
        cls,
        *,
        namespace_id: str,
        embedding_model: str,
        query_embedding: list[float],
        filter_sql: str,
        filter_params: list[str | int | float | bool | datetime | None],
        limit: int,
        limit_placeholder: int,
    ) -> list[tuple[VectorDocument, float]]:
        async with atomic(using="rag"):
            _ = await execute_raw("SET hnsw.iterative_scan = relaxed_order", using="rag")
            rows = await execute_raw(
                f"""
                SELECT {_CHUNK_COLUMNS}, (1 - (embedding <=> $1::vector)) AS similarity
                FROM vector_documents
                WHERE namespace_id = $2
                  AND embedding IS NOT NULL
                  AND embedding_model = $3
                  {filter_sql}
                ORDER BY embedding <=> $1::vector
                LIMIT ${limit_placeholder}
                """,
                [
                    _vector_literal(query_embedding),
                    namespace_id,
                    embedding_model,
                    *filter_params,
                    limit,
                ],
                using="rag",
            )
        hits: list[tuple[VectorDocument, float]] = []
        for row in rows:
            parsed = require_json_object(row, "semantic_hit")
            score = parsed["similarity"]
            if isinstance(score, bool) or not isinstance(score, (int, float)):
                raise TypeError("semantic similarity must be a number")
            hits.append((_chunk_from_row(row), float(score)))
        return hits

    @classmethod
    async def chunks_by_ids(cls, chunk_ids: list[str]) -> dict[str, VectorDocument]:
        if len(chunk_ids) == 0:
            return {}
        placeholders = ", ".join(f"${index}" for index in range(1, len(chunk_ids) + 1))
        rows = await execute_raw(
            f"SELECT {_CHUNK_COLUMNS} FROM vector_documents WHERE id IN ({placeholders})",
            chunk_ids,
            using="rag",
        )
        documents = [_chunk_from_row(row) for row in rows]
        return {document.id: document for document in documents}

    @classmethod
    async def lexical_headlines(
        cls,
        *,
        doc_ids: list[str],
        query: str,
        lexical_config: str,
        headline_options: str,
    ) -> dict[str, str]:
        placeholders = ", ".join(f"${index}" for index in range(4, len(doc_ids) + 4))
        rows = await execute_raw(
            f"""
            SELECT id, ts_headline($1::regconfig, content, websearch_to_tsquery($1::regconfig, $2), $3) AS headline
            FROM vector_documents
            WHERE id IN ({placeholders})
            """,
            [lexical_config, query, headline_options, *doc_ids],
            using="rag",
        )
        headlines: dict[str, str] = {}
        for row in rows:
            parsed = require_json_object(row, "lexical_headline")
            chunk_id = parsed["id"]
            headline = parsed["headline"]
            if not isinstance(chunk_id, str):
                raise TypeError("vector_documents.id must be a string")
            if not isinstance(headline, str):
                continue
            normalized = headline.strip()
            if normalized != "":
                headlines[chunk_id] = normalized
        return headlines


def _row_id(row: object) -> str:
    parsed = require_json_object(row, "vector_document_id")
    chunk_id = parsed["id"]
    if not isinstance(chunk_id, str):
        raise TypeError("vector_documents.id must be a string")
    return chunk_id


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(str(item) for item in values) + "]"


def _parse_vector(value: str) -> list[float]:
    body = value.strip()
    if body.startswith("[") and body.endswith("]"):
        body = body[1:-1]
    if body == "":
        return []
    return [float(item) for item in body.split(",")]


def _chunk_from_row(row: object) -> VectorDocument:
    parsed = dict(require_json_object(row, "vector_document"))
    embedding = parsed.get("embedding")
    if isinstance(embedding, str):
        parsed["embedding"] = _parse_vector(embedding)
    _ = parsed.pop("similarity", None)
    return VectorDocument.model_validate(parsed)


_CHUNK_COLUMNS = (
    "id, namespace_id, company_id, document_id, document_name, content, "
    "embedding::text AS embedding, embedding_model, chunk_index, total_chunks, "
    "metadata, created_at, updated_at"
)
