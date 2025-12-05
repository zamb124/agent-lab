"""
EntityService - работа с сущностями CRM через ChromaDB.

Сущности хранятся в ChromaDB с embeddings для семантического поиска.
Namespace = crm_{company_id}
"""

import logging
import uuid
from typing import List, Optional, Dict, Any

from core.context import get_context
from core.rag import RAGRepository
from apps.crm.db.repositories.entity_type_repository import EntityTypeRepository
from apps.crm.db.repositories.relationship_repository import RelationshipRepository
from apps.crm.models.entity_models import (
    EntityCreate,
    EntityUpdate,
    EntityResponse,
    EntitySearchRequest,
    EntitySearchResponse,
)

logger = logging.getLogger(__name__)


class EntityService:
    """
    Сервис для работы с сущностями CRM.
    
    Сущности хранятся в ChromaDB:
    - namespace = crm_{company_id}
    - embeddings для семантического поиска
    - metadata для фильтрации по типу и атрибутам
    """
    
    def __init__(
        self,
        rag_repository: RAGRepository,
        entity_type_repository: EntityTypeRepository,
        relationship_repository: RelationshipRepository,
    ):
        self._rag = rag_repository
        self._entity_type_repo = entity_type_repository
        self._relationship_repo = relationship_repository
    
    def _get_namespace(self, company_id: Optional[str] = None) -> str:
        """Формирует namespace для ChromaDB"""
        if not company_id:
            context = get_context()
            if not context or not context.active_company:
                raise ValueError("company_id не указан и нет активной компании в контексте")
            company_id = context.active_company.company_id
        return f"crm_{company_id}"
    
    def _get_company_id(self) -> str:
        """Получает company_id из контекста"""
        context = get_context()
        if not context or not context.active_company:
            raise ValueError("Нет активной компании в контексте")
        return context.active_company.company_id
    
    async def ensure_namespace(self, company_id: Optional[str] = None) -> str:
        """Создает namespace если не существует"""
        namespace = self._get_namespace(company_id)
        existing = await self._rag.get_namespace(namespace)
        if not existing:
            await self._rag.create_namespace(
                name=namespace,
                description=f"CRM entities for company"
            )
            logger.info(f"Создан CRM namespace: {namespace}")
        return namespace
    
    async def create_entity(
        self, 
        data: EntityCreate,
        company_id: Optional[str] = None
    ) -> EntityResponse:
        """
        Создает новую сущность в ChromaDB.
        """
        company_id = company_id or self._get_company_id()
        namespace = await self.ensure_namespace(company_id)
        
        entity_type = await self._entity_type_repo.get_by_company(company_id, data.type)
        if not entity_type:
            raise ValueError(f"Тип сущности '{data.type}' не найден")
        
        entity_id = str(uuid.uuid4())
        
        text_for_embedding = self._build_embedding_text(data)
        
        status = data.status.value if hasattr(data.status, 'value') else str(data.status)
        
        metadata = {
            "document_id": entity_id,
            "entity_id": entity_id,
            "company_id": company_id,
            "type": data.type,
            "name": data.name,
            "description": data.description or "",
            "status": status,
            "source_note_id": data.source_note_id or "",
            **{f"attr_{k}": str(v) for k, v in data.attributes.items()}
        }
        
        await self._rag.upload_text(
            namespace_id=namespace,
            text=text_for_embedding,
            document_name=entity_id,
            metadata=metadata
        )
        
        logger.info(f"Создана сущность: {entity_id} ({data.type}: {data.name}) [status={status}]")
        
        return EntityResponse(
            entity_id=entity_id,
            company_id=company_id,
            type=data.type,
            name=data.name,
            description=data.description,
            attributes=data.attributes,
            status=status,
            source_note_id=data.source_note_id,
        )
    
    def _build_embedding_text(self, data: EntityCreate) -> str:
        """Формирует текст для embedding"""
        parts = [data.name]
        if data.description:
            parts.append(data.description)
        for key, value in data.attributes.items():
            parts.append(f"{key}: {value}")
        return "\n".join(parts)
    
    async def get_entity(
        self, 
        entity_id: str,
        company_id: Optional[str] = None
    ) -> Optional[EntityResponse]:
        """Получает сущность по ID"""
        company_id = company_id or self._get_company_id()
        namespace = self._get_namespace(company_id)
        
        doc = await self._rag.get_document(namespace, entity_id)
        if not doc:
            return None
        
        return self._doc_to_response(doc)
    
    def _doc_to_response(self, doc) -> EntityResponse:
        """Конвертирует RAG документ в EntityResponse"""
        metadata = doc.metadata or {}
        
        attributes = {}
        for key, value in metadata.items():
            if key.startswith("attr_"):
                attributes[key[5:]] = value
        
        return EntityResponse(
            entity_id=metadata.get("entity_id", doc.document_id),
            company_id=metadata.get("company_id", ""),
            type=metadata.get("type", ""),
            name=metadata.get("name", ""),
            description=metadata.get("description"),
            attributes=attributes,
            status=metadata.get("status", "pending"),
            source_note_id=metadata.get("source_note_id") or None,
        )
    
    async def update_entity(
        self, 
        entity_id: str,
        data: EntityUpdate,
        company_id: Optional[str] = None
    ) -> Optional[EntityResponse]:
        """Обновляет сущность"""
        company_id = company_id or self._get_company_id()
        namespace = self._get_namespace(company_id)
        
        existing = await self.get_entity(entity_id, company_id)
        if not existing:
            return None
        
        new_name = data.name if data.name is not None else existing.name
        new_description = data.description if data.description is not None else existing.description
        new_attributes = data.attributes if data.attributes is not None else existing.attributes
        
        updated_data = EntityCreate(
            type=existing.type,
            name=new_name,
            description=new_description,
            attributes=new_attributes,
        )
        
        await self._rag.delete_document(namespace, entity_id)
        
        text_for_embedding = self._build_embedding_text(updated_data)
        metadata = {
            "document_id": entity_id,  # Для ChromaDB поиска
            "entity_id": entity_id,
            "company_id": company_id,
            "type": existing.type,
            "name": new_name,
            "description": new_description or "",
            **{f"attr_{k}": str(v) for k, v in new_attributes.items()}
        }
        
        await self._rag.upload_text(
            namespace_id=namespace,
            text=text_for_embedding,
            document_name=entity_id,
            metadata=metadata
        )
        
        logger.info(f"Обновлена сущность: {entity_id}")
        
        return EntityResponse(
            entity_id=entity_id,
            company_id=company_id,
            type=existing.type,
            name=new_name,
            description=new_description,
            attributes=new_attributes,
        )
    
    async def update_entity_status(
        self,
        entity_id: str,
        status: str,
        company_id: Optional[str] = None
    ) -> Optional[EntityResponse]:
        """Обновляет статус сущности"""
        company_id = company_id or self._get_company_id()
        namespace = self._get_namespace(company_id)
        
        existing = await self.get_entity(entity_id, company_id)
        if not existing:
            return None
        
        status_value = status.value if hasattr(status, 'value') else str(status)
        
        await self._rag.delete_document(namespace, entity_id)
        
        updated_data = EntityCreate(
            type=existing.type,
            name=existing.name,
            description=existing.description,
            attributes=existing.attributes,
            status=status_value,
            source_note_id=existing.source_note_id,
        )
        
        text_for_embedding = self._build_embedding_text(updated_data)
        metadata = {
            "document_id": entity_id,
            "entity_id": entity_id,
            "company_id": company_id,
            "type": existing.type,
            "name": existing.name,
            "description": existing.description or "",
            "status": status_value,
            "source_note_id": existing.source_note_id or "",
            **{f"attr_{k}": str(v) for k, v in existing.attributes.items()}
        }
        
        await self._rag.upload_text(
            namespace_id=namespace,
            text=text_for_embedding,
            document_name=entity_id,
            metadata=metadata
        )
        
        logger.info(f"Статус сущности {entity_id} изменен на {status_value}")
        
        return EntityResponse(
            entity_id=entity_id,
            company_id=company_id,
            type=existing.type,
            name=existing.name,
            description=existing.description,
            attributes=existing.attributes,
            status=status_value,
            source_note_id=existing.source_note_id,
        )
    
    async def delete_entity(
        self, 
        entity_id: str,
        company_id: Optional[str] = None
    ) -> bool:
        """Удаляет сущность и все её связи"""
        company_id = company_id or self._get_company_id()
        namespace = self._get_namespace(company_id)
        
        await self._relationship_repo.delete_by_entity(company_id, entity_id)
        
        success = await self._rag.delete_document(namespace, entity_id)
        if success:
            logger.info(f"Удалена сущность: {entity_id}")
        return success
    
    async def list_entities(
        self,
        entity_type: Optional[str] = None,
        limit: int = 100,
        company_id: Optional[str] = None
    ) -> List[EntityResponse]:
        """Получает список сущностей"""
        company_id = company_id or self._get_company_id()
        namespace = self._get_namespace(company_id)
        
        docs = await self._rag.list_documents(namespace, limit=limit)
        
        entities = [self._doc_to_response(doc) for doc in docs]
        
        if entity_type:
            entities = [e for e in entities if e.type == entity_type]
        
        return entities
    
    async def search_entities(
        self,
        request: EntitySearchRequest,
        company_id: Optional[str] = None
    ) -> EntitySearchResponse:
        """Семантический поиск по сущностям"""
        company_id = company_id or self._get_company_id()
        namespace = self._get_namespace(company_id)
        
        filters = {}
        if request.entity_type:
            filters["type"] = request.entity_type
        filters.update(request.filters)
        
        if request.query:
            results = await self._rag.search(
                namespace_id=namespace,
                query=request.query,
                limit=request.limit,
                filters=filters if filters else None
            )
            
            entities = []
            for result in results:
                entities.append(self._search_result_to_response(result))
        else:
            entities = await self.list_entities(
                entity_type=request.entity_type,
                limit=request.limit,
                company_id=company_id
            )
        
        return EntitySearchResponse(
            entities=entities,
            total=len(entities),
            query=request.query,
        )
    
    async def find_duplicates(
        self,
        data: EntityCreate,
        threshold: float = 0.85,
        company_id: Optional[str] = None
    ) -> List[EntityResponse]:
        """Находит потенциальные дубликаты сущности"""
        company_id = company_id or self._get_company_id()
        namespace = self._get_namespace(company_id)
        
        entity_type = await self._entity_type_repo.get_by_company(company_id, data.type)
        if entity_type and not entity_type.check_duplicates:
            return []
        
        query = self._build_embedding_text(data)
        
        results = await self._rag.search(
            namespace_id=namespace,
            query=query,
            limit=5,
            filters={"type": data.type}
        )
        
        duplicates = []
        for result in results:
            if result.score >= threshold:
                duplicates.append(self._search_result_to_response(result))
        
        return duplicates
    
    def _search_result_to_response(self, result) -> EntityResponse:
        """Конвертирует RAGSearchResult в EntityResponse"""
        metadata = result.metadata or {}
        
        attributes = {}
        for key, value in metadata.items():
            if key.startswith("attr_"):
                attributes[key[5:]] = value
        
        return EntityResponse(
            entity_id=metadata.get("entity_id", result.document_id),
            company_id=metadata.get("company_id", ""),
            type=metadata.get("type", ""),
            name=metadata.get("name", ""),
            description=metadata.get("description"),
            attributes=attributes,
        )

