"""
Репозиторий для работы со статусами обработки документов в RAG.
"""

from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import bindparam, delete, func, literal_column, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.db.database import get_session_factory
from core.db.models import DocumentProcessingStatus as DBDocumentStatus
from core.db.models.rag import VectorDocument
from core.logging import get_logger
from core.rag.models import DocumentProcessingStatus as DocumentStatusModel

logger = get_logger(__name__)


class DocumentStatusRepository:
    """
    Репозиторий для управления статусами обработки документов.

    Одна строка на document_id; повторная загрузка того же файла обновляет её (UPSERT).
    """

    def __init__(self, db_url: str):
        self._db_url = db_url
        self._session_factory = None

    async def _get_session_factory(self):
        if self._session_factory is None:
            self._session_factory = await get_session_factory(self._db_url)
        return self._session_factory

    async def create_status(
        self,
        document_id: str,
        task_id: str,
        namespace_id: str,
        document_name: str,
        file_size: Optional[int] = None,
        ttl_seconds: int = 864000,
        extra_metadata: Optional[dict] = None,
    ) -> DocumentStatusModel:
        """Создаёт или сбрасывает строку статуса в pending (повторная загрузка)."""
        if int(ttl_seconds) < 0:
            raise ValueError("ttl_seconds не может быть отрицательным")
        session_factory = await self._get_session_factory()
        async with session_factory() as session:
            now = datetime.now(timezone.utc)
            existing_result = await session.execute(
                select(DBDocumentStatus).where(
                    DBDocumentStatus.document_id == document_id
                )
            )
            existing = existing_result.scalar_one_or_none()
            em = dict(extra_metadata or {})
            if existing is not None and existing.extra_metadata:
                em = {**dict(existing.extra_metadata), **em}
            stmt = pg_insert(DBDocumentStatus).values(
                document_id=document_id,
                task_id=task_id,
                namespace_id=namespace_id,
                document_name=document_name,
                status="pending",
                file_size=file_size,
                ttl_seconds=int(ttl_seconds),
                extra_metadata=em,
                created_at=now,
                updated_at=now,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["document_id"],
                set_={
                    "task_id": task_id,
                    "namespace_id": namespace_id,
                    "document_name": document_name,
                    "status": "pending",
                    "file_size": file_size,
                    "ttl_seconds": int(ttl_seconds),
                    "extra_metadata": em,
                    "updated_at": now,
                    "completed_at": None,
                    "error_message": None,
                    "s3_key": None,
                    "s3_bucket": None,
                    "chunks_count": None,
                },
            )
            await session.execute(stmt)
            await session.commit()
            result = await session.execute(
                select(DBDocumentStatus).where(
                    DBDocumentStatus.document_id == document_id
                )
            )
            db_status = result.scalar_one()
            logger.info(
                "Статус документа: document_id=%s task=%s (создан или сброшен в pending)",
                document_id,
                task_id,
            )
            return DocumentStatusModel.model_validate(db_status)

    async def finalize_enqueued_indexing_task(
        self,
        document_id: str,
        task_id: str,
    ) -> DocumentStatusModel:
        if not task_id:
            raise ValueError("task_id обязателен")
        session_factory = await self._get_session_factory()
        async with session_factory() as session:
            now = datetime.now(timezone.utc)
            result = await session.execute(
                select(DBDocumentStatus).where(
                    DBDocumentStatus.document_id == document_id
                )
            )
            row = result.scalar_one()
            row.task_id = task_id
            row.updated_at = now
            await session.commit()
            await session.refresh(row)
            logger.info(
                "Документ %s: поставлена задача индексации task_id=%s",
                document_id,
                task_id,
            )
            return DocumentStatusModel.model_validate(row)

    async def try_mark_processing(self, document_id: str) -> None:
        session_factory = await self._get_session_factory()
        async with session_factory() as session:
            now = datetime.now(timezone.utc)
            await session.execute(
                update(DBDocumentStatus)
                .where(
                    DBDocumentStatus.document_id == document_id,
                    DBDocumentStatus.status == "pending",
                )
                .values(status="processing", updated_at=now)
            )
            await session.commit()

    async def record_indexing_done(
        self,
        document_id: str,
        chunks: int,
        *,
        indexing_runtime: Optional[dict[str, Any]] = None,
    ) -> DocumentStatusModel:
        session_factory = await self._get_session_factory()
        async with session_factory() as session:
            now = datetime.now(timezone.utc)
            result = await session.execute(
                select(DBDocumentStatus)
                .where(DBDocumentStatus.document_id == document_id)
                .with_for_update()
            )
            row = result.scalar_one()
            if row.status == "failed":
                await session.commit()
                return DocumentStatusModel.model_validate(row)

            row.chunks_count = int(chunks)
            row.status = "completed"
            row.completed_at = now
            row.updated_at = now
            em = dict(row.extra_metadata or {})
            prev_runs = int(em.get("indexing_run_count", 0))
            em["indexing_run_count"] = prev_runs + 1
            if indexing_runtime is not None:
                em["indexing_runtime"] = indexing_runtime
            row.extra_metadata = em
            await session.commit()
            await session.refresh(row)
            logger.info(
                "Документ %s: индексация завершена, чанков=%s",
                document_id,
                chunks,
            )
            return DocumentStatusModel.model_validate(row)

    async def record_indexing_failed(self, document_id: str, error: str) -> None:
        session_factory = await self._get_session_factory()
        async with session_factory() as session:
            now = datetime.now(timezone.utc)
            msg = str(error)
            if len(msg) > 5000:
                msg = msg[:4997] + "..."
            await session.execute(
                update(DBDocumentStatus)
                .where(DBDocumentStatus.document_id == document_id)
                .values(
                    status="failed",
                    error_message=msg,
                    updated_at=now,
                )
            )
            await session.commit()
            logger.error(
                "Индексация документа %s провалилась: %s",
                document_id,
                msg,
            )

    async def get_by_document_id(self, document_id: str) -> Optional[DocumentStatusModel]:
        session_factory = await self._get_session_factory()
        async with session_factory() as session:
            result = await session.execute(
                select(DBDocumentStatus).where(
                    DBDocumentStatus.document_id == document_id
                )
            )
            db_status = result.scalar_one_or_none()

            if db_status:
                return DocumentStatusModel.model_validate(db_status)
            return None

    async def get_by_task_id(self, task_id: str) -> Optional[DocumentStatusModel]:
        session_factory = await self._get_session_factory()
        async with session_factory() as session:
            result = await session.execute(
                select(DBDocumentStatus).where(DBDocumentStatus.task_id == task_id)
            )
            db_status = result.scalar_one_or_none()

            if db_status:
                return DocumentStatusModel.model_validate(db_status)
            return None

    async def update_status(
        self,
        document_id: str,
        status: str,
        error: Optional[str] = None,
        s3_key: Optional[str] = None,
        s3_bucket: Optional[str] = None,
        chunks_count: Optional[int] = None,
    ) -> DocumentStatusModel:
        session_factory = await self._get_session_factory()
        async with session_factory() as session:
            now = datetime.now(timezone.utc)

            values = {
                "status": status,
                "updated_at": now,
            }

            if error:
                values["error_message"] = error

            if s3_key:
                values["s3_key"] = s3_key

            if s3_bucket:
                values["s3_bucket"] = s3_bucket

            if chunks_count is not None:
                values["chunks_count"] = chunks_count

            if status == "completed":
                values["completed_at"] = now

            await session.execute(
                update(DBDocumentStatus)
                .where(DBDocumentStatus.document_id == document_id)
                .values(**values)
            )
            await session.commit()

            result = await session.execute(
                select(DBDocumentStatus).where(
                    DBDocumentStatus.document_id == document_id
                )
            )
            db_status = result.scalar_one()

            logger.info(
                "Обновлен статус документа %s: %s",
                document_id,
                status,
            )

            return DocumentStatusModel.model_validate(db_status)

    async def get_latest_by_namespace_and_document_ids(
        self,
        namespace_id: str,
        document_ids: List[str],
    ) -> dict[str, DocumentStatusModel]:
        """Строки статуса по паре (namespace_id, document_id)."""
        if not document_ids:
            return {}
        session_factory = await self._get_session_factory()
        async with session_factory() as session:
            result = await session.execute(
                select(DBDocumentStatus).where(
                    DBDocumentStatus.namespace_id == namespace_id,
                    DBDocumentStatus.document_id.in_(document_ids),
                )
            )
            rows = result.scalars().all()
            return {str(r.document_id): DocumentStatusModel.model_validate(r) for r in rows}

    async def count_effective_document_status_by_namespace(
        self, namespace_id: str
    ) -> dict[str, int]:
        """
        Число уникальных document_id в namespace по эффективному статусу:
        строка в document_processing_status, плюс документы
        только в vector_documents без строки статуса (считаются completed).
        """
        multi = await self.count_effective_document_status_for_namespaces([namespace_id])
        return multi.get(
            namespace_id,
            {"pending": 0, "processing": 0, "completed": 0, "failed": 0},
        )

    async def count_effective_document_status_for_namespaces(
        self, namespace_ids: List[str]
    ) -> dict[str, dict[str, int]]:
        """По каждому namespace_id — счётчики pending, processing, completed, failed."""
        keys = ("pending", "processing", "completed", "failed")
        empty = {k: 0 for k in keys}
        if not namespace_ids:
            return {}

        session_factory = await self._get_session_factory()
        async with session_factory() as session:
            stmt = text(
                """
                WITH from_status AS (
                  SELECT namespace_id, document_id, status
                  FROM document_processing_status
                  WHERE namespace_id IN :ns_a
                ),
                from_vectors AS (
                  SELECT DISTINCT vd.namespace_id, vd.document_id
                  FROM vector_documents vd
                  WHERE vd.namespace_id IN :ns_b
                ),
                merged AS (
                  SELECT fs.namespace_id, fs.document_id, fs.status
                  FROM from_status fs
                  UNION ALL
                  SELECT fv.namespace_id, fv.document_id, 'completed'::text AS status
                  FROM from_vectors fv
                  WHERE NOT EXISTS (
                    SELECT 1 FROM from_status fs2
                    WHERE fs2.namespace_id = fv.namespace_id
                      AND fs2.document_id = fv.document_id
                  )
                )
                SELECT m.namespace_id, m.status, COUNT(*)::int AS cnt
                FROM merged m
                GROUP BY m.namespace_id, m.status
                """
            ).bindparams(
                bindparam("ns_a", expanding=True),
                bindparam("ns_b", expanding=True),
            )
            result = await session.execute(
                stmt,
                {"ns_a": namespace_ids, "ns_b": namespace_ids},
            )
            rows = result.mappings().all()

        out: dict[str, dict[str, int]] = {ns: dict(empty) for ns in namespace_ids}
        for row in rows:
            ns = str(row["namespace_id"])
            status = str(row["status"])
            cnt = int(row["cnt"])
            if ns not in out:
                continue
            if status not in out[ns]:
                raise ValueError(f"Неожиданный статус в агрегации: {status!r}")
            out[ns][status] = cnt

        return out

    async def list_by_namespace(
        self,
        namespace_id: str,
        status: Optional[List[str]] = None,
        limit: int = 100,
    ) -> List[DocumentStatusModel]:
        session_factory = await self._get_session_factory()
        async with session_factory() as session:
            q = select(DBDocumentStatus).where(
                DBDocumentStatus.namespace_id == namespace_id
            )
            if status:
                q = q.where(DBDocumentStatus.status.in_(status))
            q = q.order_by(DBDocumentStatus.updated_at.desc().nulls_last()).limit(limit)
            result = await session.execute(q)
            db_statuses = result.scalars().all()

            return [DocumentStatusModel.model_validate(s) for s in db_statuses]

    async def count_chunks_by_namespace_and_document_ids(
        self,
        namespace_id: str,
        document_ids: List[str],
    ) -> dict[str, int]:
        """Число строк vector_documents (чанков) на документ в namespace."""
        if not document_ids:
            return {}
        session_factory = await self._get_session_factory()
        async with session_factory() as session:
            stmt = (
                select(VectorDocument.document_id, func.count().label("cnt"))
                .where(
                    VectorDocument.namespace_id == namespace_id,
                    VectorDocument.document_id.in_(document_ids),
                )
                .group_by(VectorDocument.document_id)
            )
            result = await session.execute(stmt)
            rows = result.all()
        return {str(r.document_id): int(r.cnt) for r in rows}

    async def delete_by_document_id(self, document_id: str) -> int:
        session_factory = await self._get_session_factory()
        async with session_factory() as session:
            result = await session.execute(
                delete(DBDocumentStatus).where(
                    DBDocumentStatus.document_id == document_id
                )
            )
            await session.commit()
            n = int(result.rowcount or 0)
            if n:
                logger.info(
                    "Удалена строка статуса документа document_id=%s",
                    document_id,
                )
            return n

    async def list_expired_document_candidates(
        self,
        *,
        utc_now: datetime,
        limit: int,
    ) -> List[tuple[str, str]]:
        """
        Пары (namespace_id, document_id) с истёкшим TTL (UTC).

        Учитываются завершённые документы со строкой статуса (`completed_at` + `ttl_seconds`)
        и чанки только в ``vector_documents`` без строки статуса (`min(created_at)` + TTL из metadata).
        """
        if limit < 1:
            raise ValueError("limit должен быть >= 1")

        expiry_status = DBDocumentStatus.completed_at + DBDocumentStatus.ttl_seconds * literal_column(
            "interval '1 second'"
        )

        session_factory = await self._get_session_factory()
        async with session_factory() as session:
            q_status = (
                select(DBDocumentStatus.namespace_id, DBDocumentStatus.document_id)
                .where(
                    DBDocumentStatus.status == "completed",
                    DBDocumentStatus.completed_at.isnot(None),
                    DBDocumentStatus.ttl_seconds > 0,
                    expiry_status <= utc_now,
                )
                .order_by(DBDocumentStatus.completed_at.asc())
                .limit(limit)
            )
            r1 = await session.execute(q_status)
            from_status_rows = [(str(ns), str(d)) for ns, d in r1.all()]

        remain = limit - len(from_status_rows)
        from_vector_rows: List[tuple[str, str]] = []
        if remain > 0:
            orphan_sql = text(
                """
                WITH per_doc AS (
                  SELECT vd.namespace_id AS namespace_id,
                         vd.document_id AS document_id,
                         MIN(vd.created_at) AS anchor_at,
                         MIN((vd.metadata->>'ttl_seconds')::bigint) AS ttl_eff
                  FROM vector_documents vd
                  WHERE NOT EXISTS (
                    SELECT 1 FROM document_processing_status dps
                    WHERE dps.document_id = vd.document_id
                  )
                  GROUP BY vd.namespace_id, vd.document_id
                )
                SELECT namespace_id, document_id
                FROM per_doc
                WHERE ttl_eff > 0
                  AND ttl_eff IS NOT NULL
                  AND anchor_at + (ttl_eff * interval '1 second') <= :boundary
                ORDER BY anchor_at ASC
                LIMIT :lim
                """
            )
            async with session_factory() as session:
                r2 = await session.execute(
                    orphan_sql,
                    {"boundary": utc_now, "lim": remain},
                )
                from_vector_rows = [(str(row[0]), str(row[1])) for row in r2.all()]

        merged: List[tuple[str, str]] = []

        merged.extend(from_status_rows)
        merged.extend(from_vector_rows)
        return merged
