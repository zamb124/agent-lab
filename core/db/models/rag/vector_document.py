"""Чанк векторного индекса."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index, atomic, execute_raw

from core.logging import get_logger
from core.models.platform_model import PlatformModel
from core.types import JsonObject, JsonValue, require_json_object

logger = get_logger(__name__)

_STATUS_KEYS = ("pending", "processing", "completed", "failed")

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
    async def count_rows_for_namespace(cls, namespace_id: str) -> int:
        """Число строк чанков в namespace, не разных document_id."""
        return await cls.objects.filter(namespace_id=namespace_id).count()

    @classmethod
    async def chunk_counts_by_namespace(cls) -> list[tuple[str, int]]:
        """Число строк чанков по namespace_id. Порядка нет."""
        rows = await execute_raw(
            """
            SELECT namespace_id, COUNT(*)::int AS chunk_count
            FROM vector_documents
            GROUP BY namespace_id
            """,
            using="rag",
        )
        counts: list[tuple[str, int]] = []
        for row in rows:
            parsed = require_json_object(row, "rag_namespace")
            namespace_id = parsed["namespace_id"]
            chunk_count = parsed["chunk_count"]
            if not isinstance(namespace_id, str):
                raise TypeError("vector_documents.namespace_id must be a string")
            if isinstance(chunk_count, bool) or not isinstance(chunk_count, int):
                raise TypeError("namespace chunk count must be an integer")
            counts.append((namespace_id, chunk_count))
        return counts

    @classmethod
    async def delete_by_namespace(cls, namespace_id: str) -> int:
        """Удаляет строки namespace. Возвращает число удалённых. Нет строк — 0."""
        return await cls.objects.filter(namespace_id=namespace_id).delete(using="rag")

    @classmethod
    async def delete_by_namespace_and_document_id(cls, namespace_id: str, document_id: str) -> int:
        """Удаляет чанки пары namespace_id и document_id. Возвращает число удалённых строк. Нет строк — 0."""
        return await cls.objects.filter(
            namespace_id=namespace_id,
            document_id=document_id,
        ).delete(using="rag")

    @classmethod
    async def replace_chunks(cls, rows: list[Self]) -> int:
        """Удаляет чанки namespace_id и document_id первой строки, затем вставляет все rows. Возвращает число удалённых, не вставленных. Пустой список — ValueError."""
        if len(rows) == 0:
            raise ValueError("replace_chunks requires at least one chunk")
        namespace_id = rows[0].namespace_id
        document_id = rows[0].document_id
        async with atomic(using="rag"):
            _ = await execute_raw(
                "SELECT pg_advisory_xact_lock(hashtext($1))",
                [f"{namespace_id}:{document_id}"],
                using="rag",
            )
            deleted_count = await cls.delete_by_namespace_and_document_id(namespace_id, document_id)
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
    async def list_by_namespace_and_document_id(
        cls,
        namespace_id: str,
        document_id: str,
        *,
        limit: int | None = None,
    ) -> list[VectorDocument]:
        """Чанки пары namespace_id и document_id, ORDER BY chunk_index ASC. limit None не ограничивает. Нет строк — []."""
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
    async def any_chunk_rows_by_document_id(cls, namespace_id: str, *, limit: int) -> list[VectorDocument]:
        """По одной строке чанка на document_id, ORDER BY document_id, не больше limit. Какой чанк внутри документа, не задано."""
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
    async def any_chunk_rows_by_document_id_where(
        cls,
        namespace_id: str,
        *,
        filter_sql: str,
        filter_params: list[str | int | float | bool | datetime | None],
        limit: int,
        limit_placeholder: int,
    ) -> list[VectorDocument]:
        """По одной строке чанка на document_id в namespace с filter_sql, ORDER BY document_id, не больше limit. Какой чанк внутри документа, не задано. filter_sql дописывается к предикату namespace."""
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
    async def chunk_and_null_count_rows(
        cls,
        keys: list[tuple[str, str, str]],
    ) -> list[tuple[str, str, str, int, int]]:
        """Строки (namespace_id, document_id, company_id, chunk_count, null_chunks). Пустые keys — []. Ключ без чанков не входит. Порядка нет. company_id не строка — строка пропускается."""
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
    async def stale_id_content_company_rows(
        cls,
        *,
        limit: int,
        target_embedding_model: str,
    ) -> list[tuple[str, str, str]]:
        """Строки (id, content, company_id) для перевекторизации: модель пустая или не target, content непустой. Порядок company_rank, company_id, id. limit <= 0 — ValueError."""
        if limit <= 0:
            raise ValueError("stale_id_content_company_rows: limit must be positive")
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
                raise ValueError("stale_id_content_company_rows returned row without company_id")
            stale_chunks.append((chunk_id, content, company_id))
        return stale_chunks

    @classmethod
    async def update_embedding_and_model(
        cls,
        doc_embeddings: list[tuple[str, list[float]]],
        target_embedding_model: str,
    ) -> int:
        """Пишет embedding, embedding_model и updated_at по id. Пустой список — 0. Нет строки — она не входит в число."""
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
    async def delete_without_company_id(cls, *, limit: int) -> int:
        """Удаляет строки с пустым company_id, ORDER BY id ASC, не больше limit. Возвращает число выбранных id. Нет строк — 0. limit <= 0 — ValueError."""
        if limit <= 0:
            raise ValueError("delete_without_company_id: limit must be positive")
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
    async def semantic_and_lexical_chunk_ids(
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
        """Два списка id: семантический по расстоянию embedding и лексический по ts_rank_cd DESC. Каждый не длиннее per_channel."""
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
    async def rows_with_similarity(
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
        """Пары (строка, similarity) ближайших чанков, ORDER BY embedding <=> query. filter_sql дописывается к предикату. similarity не число — TypeError."""
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
    async def found_by_ids(cls, chunk_ids: list[str]) -> dict[str, VectorDocument]:
        """Найденные строки по id. Пустой список — {}. Отсутствующие id не входят. Порядка нет. Пустой id не отклоняется."""
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
    async def stripped_headlines_by_id(
        cls,
        *,
        doc_ids: list[str],
        query: str,
        lexical_config: str,
        headline_options: str,
    ) -> dict[str, str]:
        """id к ts_headline после strip. Заголовок не строка или пустой не входит. Порядка нет."""
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


def _row_id(row: JsonValue) -> str:
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


def _chunk_from_row(row: JsonValue) -> VectorDocument:
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
