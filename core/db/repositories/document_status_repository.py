"""
Репозиторий для работы со статусами обработки документов в RAG.
"""

from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import DocumentProcessingStatus as DBDocumentStatus
from core.rag.models import DocumentProcessingStatus as DocumentStatusModel
from core.db.database import get_session_factory
from core.logging import get_logger

logger = get_logger(__name__)


class DocumentStatusRepository:
    """
    Репозиторий для управления статусами обработки документов.
    
    Использует SQLAlchemy для работы с БД и возвращает Pydantic модели.
    """
    
    def __init__(self, db_url: str):
        """
        Args:
            db_url: URL базы данных
        """
        self._db_url = db_url
        self._session_factory = None
    
    async def _get_session_factory(self):
        """Получает session factory (с кешированием)"""
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
        extra_metadata: Optional[dict] = None
    ) -> DocumentStatusModel:
        """
        Создает новую запись статуса документа.
        
        Args:
            document_id: ID документа
            task_id: ID задачи TaskIQ
            namespace_id: ID namespace
            document_name: Имя файла
            file_size: Размер файла в байтах
            extra_metadata: Дополнительные метаданные
            
        Returns:
            Созданный статус документа
        """
        session_factory = await self._get_session_factory()
        async with session_factory() as session:
            now = datetime.now(timezone.utc)
            
            db_status = DBDocumentStatus(
                document_id=document_id,
                task_id=task_id,
                namespace_id=namespace_id,
                document_name=document_name,
                status="pending",
                file_size=file_size,
                extra_metadata=extra_metadata or {},
                created_at=now,
                updated_at=now
            )
            
            session.add(db_status)
            await session.commit()
            await session.refresh(db_status)
            
            logger.info(f"Создан статус документа: {document_id} (task={task_id})")
            
            return DocumentStatusModel.model_validate(db_status)
    
    async def get_by_document_id(self, document_id: str) -> Optional[DocumentStatusModel]:
        """
        Получает статус по ID документа.
        
        Args:
            document_id: ID документа
            
        Returns:
            Статус документа или None
        """
        session_factory = await self._get_session_factory()
        async with session_factory() as session:
            result = await session.execute(
                select(DBDocumentStatus).where(DBDocumentStatus.document_id == document_id)
            )
            db_status = result.scalar_one_or_none()
            
            if db_status:
                return DocumentStatusModel.model_validate(db_status)
            return None
    
    async def get_by_task_id(self, task_id: str) -> Optional[DocumentStatusModel]:
        """
        Получает статус по ID задачи.
        
        Args:
            task_id: ID задачи TaskIQ
            
        Returns:
            Статус документа или None
        """
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
        chunks_count: Optional[int] = None
    ) -> DocumentStatusModel:
        """
        Обновляет статус документа.
        
        Args:
            document_id: ID документа
            status: Новый статус (pending, processing, completed, failed)
            error: Сообщение об ошибке (если failed)
            s3_key: Ключ файла в S3
            s3_bucket: Имя bucket в S3
            chunks_count: Количество chunks
            
        Returns:
            Обновленный статус
        """
        session_factory = await self._get_session_factory()
        async with session_factory() as session:
            now = datetime.now(timezone.utc)
            
            values = {
                "status": status,
                "updated_at": now
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
                select(DBDocumentStatus).where(DBDocumentStatus.document_id == document_id)
            )
            db_status = result.scalar_one()
            
            logger.info(f"Обновлен статус документа {document_id}: {status}")
            
            return DocumentStatusModel.model_validate(db_status)
    
    async def list_by_namespace(
        self,
        namespace_id: str,
        status: Optional[List[str]] = None,
        limit: int = 100
    ) -> List[DocumentStatusModel]:
        """
        Получает список статусов документов в namespace.
        
        Args:
            namespace_id: ID namespace
            status: Фильтр по статусам (если None - все)
            limit: Максимальное количество записей
            
        Returns:
            Список статусов документов
        """
        session_factory = await self._get_session_factory()
        async with session_factory() as session:
            query = select(DBDocumentStatus).where(
                DBDocumentStatus.namespace_id == namespace_id
            )
            
            if status:
                query = query.where(DBDocumentStatus.status.in_(status))
            
            query = query.order_by(DBDocumentStatus.created_at.desc()).limit(limit)
            
            result = await session.execute(query)
            db_statuses = result.scalars().all()
            
            return [DocumentStatusModel.model_validate(s) for s in db_statuses]
    
    async def delete_by_document_id(self, document_id: str) -> bool:
        """
        Удаляет статус документа.
        
        Args:
            document_id: ID документа
            
        Returns:
            True если удален, False если не найден
        """
        session_factory = await self._get_session_factory()
        async with session_factory() as session:
            result = await session.execute(
                select(DBDocumentStatus).where(DBDocumentStatus.document_id == document_id)
            )
            db_status = result.scalar_one_or_none()
            
            if db_status:
                await session.delete(db_status)
                await session.commit()
                logger.info(f"Удален статус документа: {document_id}")
                return True
            
            return False

