"""
Базовый репозиторий для ChromaDB.

Namespace: просто namespace_name (например "default")
Company изоляция через metadata {"company_id": "..."}
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, date

from core.rag import RAGRepository
from core.context import get_context
from core.logging import get_logger
from apps.crm.models.entity import ChromaDBEntity

logger = get_logger(__name__)


class BaseCRMChromaRepository:
    """
    Базовый репозиторий для CRM в ChromaDB.
    
    Единая модель ChromaDBEntity.
    Company изоляция через metadata {"company_id": "..."}
    """
    
    def __init__(self, rag_repository: RAGRepository):
        self._rag = rag_repository
    
    def _get_namespace(self, namespace_name: Optional[str] = None) -> str:
        """
        Возвращает имя namespace (БЕЗ префикса company_id).
        
        Args:
            namespace_name: Имя namespace. Если None, использует "default"
        
        Returns:
            Имя namespace (например "default")
        """
        return namespace_name or "default"
    
    def _get_company_id(self) -> str:
        context = get_context()
        if not context or not context.active_company:
            raise ValueError("Нет активной компании в контексте")
        return context.active_company.company_id
    
    def _build_search_text(self, entity: ChromaDBEntity) -> str:
        """Формирует текст для семантического поиска"""
        parts = [entity.name]
        
        if entity.description:
            parts.append(entity.description)
        
        for key, value in entity.attributes.items():
            if value:
                parts.append(f"{key}: {value}")
        
        if entity.tags:
            parts.append(f"Теги: {', '.join(entity.tags)}")
        
        if entity.is_note and entity.entity_subtype:
            parts.append(f"Тип: {entity.entity_subtype}")
        
        if entity.is_task:
            if entity.priority:
                parts.append(f"Приоритет: {entity.priority}")
            if entity.due_date:
                parts.append(f"Дедлайн: {entity.due_date}")
        
        return "\n".join(parts)
    
    def _model_to_metadata(self, entity: ChromaDBEntity) -> Dict[str, Any]:
        """Конвертирует ChromaDBEntity в metadata для ChromaDB"""
        data = entity.model_dump(exclude_none=False)
        
        flattened = {}
        for key, value in data.items():
            if isinstance(value, dict):
                for nested_key, nested_value in value.items():
                    flattened[f"{key}.{nested_key}"] = str(nested_value) if nested_value is not None else ""
            elif isinstance(value, list):
                if key == "tags":
                    # Сохраняем каждый тег как отдельное поле tag_0, tag_1 для фильтрации
                    for idx, tag in enumerate(value[:10]):  # Максимум 10 тегов
                        flattened[f"tag_{idx}"] = str(tag)
                # Также сохраняем как строку для полнотекстового поиска
                flattened[key] = ",".join(str(v) for v in value) if value else ""
            elif isinstance(value, (datetime, date)):
                flattened[key] = value.isoformat() if value else ""
            else:
                flattened[key] = str(value) if value is not None else ""
        
        return flattened
    
    def _metadata_to_model(self, metadata: Dict[str, Any]) -> ChromaDBEntity:
        """Конвертирует metadata ChromaDB обратно в ChromaDBEntity"""
        unflattened = {}
        
        for key, value in metadata.items():
            if "." in key:
                parent, child = key.split(".", 1)
                if parent not in unflattened:
                    unflattened[parent] = {}
                unflattened[parent][child] = value
            elif key in ["attachment_ids", "tags", "assignees", "external_relationships"]:
                if key == "external_relationships":
                    unflattened[key] = []
                else:
                    unflattened[key] = value.split(",") if value else []
            elif key in ["created_at", "updated_at"]:
                unflattened[key] = datetime.fromisoformat(value) if value else None
            elif key in ["note_date", "due_date"]:
                unflattened[key] = date.fromisoformat(value) if value else None
            elif key == "relevance":
                unflattened[key] = float(value) if value else 1.0
            else:
                unflattened[key] = value
        
        return ChromaDBEntity.model_validate(unflattened)
    
    async def create(self, entity: ChromaDBEntity) -> ChromaDBEntity:
        """Создает entity в ChromaDB"""
        company_id = self._get_company_id()
        namespace = self._get_namespace()
        
        search_text = self._build_search_text(entity)
        metadata = self._model_to_metadata(entity)
        metadata["document_id"] = entity.entity_id
        
        await self._rag.upload_text(
            namespace_id=namespace,
            text=search_text,
            document_name=entity.entity_id,
            metadata=metadata
        )
        
        logger.info(
            f"Created entity: {entity.entity_id}, type={entity.full_type}"
        )
        return entity
    
    async def get(
        self,
        entity_id: str
    ) -> Optional[ChromaDBEntity]:
        """
        Получает entity по ID БЕЗ company фильтра.
        
        Позволяет cross-company доступ через AccessGrants.
        Использует get_document без embedding.
        """
        namespace = self._get_namespace()
        
        document = await self._rag.get_document(namespace, entity_id)
        
        if not document:
            return None
        
        return self._metadata_to_model(document.metadata)
    
    async def update(self, entity: ChromaDBEntity) -> ChromaDBEntity:
        """Обновляет entity"""
        namespace = self._get_namespace()
        
        await self._rag.delete_document(namespace, entity.entity_id)
        
        search_text = self._build_search_text(entity)
        metadata = self._model_to_metadata(entity)
        metadata["document_id"] = entity.entity_id
        
        await self._rag.upload_text(
            namespace_id=namespace,
            text=search_text,
            document_name=entity.entity_id,
            metadata=metadata
        )
        
        logger.info(f"Updated entity: {entity.entity_id}, type={entity.full_type}")
        return entity
    
    async def delete(
        self,
        entity_id: str
    ) -> bool:
        """Удаляет entity через поиск по metadata"""
        company_id = self._get_company_id()
        namespace = self._get_namespace()
        
        results = await self._rag.search(
            namespace_id=namespace,
            query=entity_id,
            limit=1,
            filters={"entity_id": entity_id}
        )
        
        if not results:
            logger.warning(f"Entity not found for deletion: {entity_id}")
            return False
        
        internal_doc_id = results[0].document_id
        success = await self._rag.delete_document(namespace, internal_doc_id)
        
        if success:
            logger.info(f"Deleted entity: {entity_id}")
        return success
    
    def _build_where_filters(
        self,
        company_id: str,
        entity_type: Optional[str] = None,
        entity_subtype: Optional[str] = None,
        namespace: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """Строит where фильтры для ChromaDB. Returns: (where_dict, date_filters_dict)"""
        where_conditions = [{"company_id": company_id}]
        date_filters = {}
        
        if namespace:
            where_conditions.append({"namespace": namespace})
        
        if entity_type:
            where_conditions.append({"entity_type": entity_type})
        
        if entity_subtype:
            where_conditions.append({"entity_subtype": entity_subtype})
        
        if filters:
            for key, value in filters.items():
                if key == "tags":
                    if isinstance(value, dict) and "$contains" in value:
                        tag_value = value["$contains"]
                        tag_conditions = [{f"tag_{i}": tag_value} for i in range(10)]
                        where_conditions.append({"$or": tag_conditions})
                elif isinstance(value, dict) and key in ["note_date", "due_date", "created_at", "updated_at"]:
                    date_filters[key] = value
                else:
                    if isinstance(value, dict):
                        for op, op_value in value.items():
                            where_conditions.append({key: {op: op_value}})
                    else:
                        where_conditions.append({key: value})
        
        where = {"$and": where_conditions} if len(where_conditions) > 1 else where_conditions[0]
        return where, date_filters
    
    def _apply_date_filters(
        self,
        entities: List[ChromaDBEntity],
        date_filters: Dict[str, Any]
    ) -> List[ChromaDBEntity]:
        """Применяет фильтры по датам (post-filtering)"""
        if not date_filters:
            return entities
        
        filtered = []
        for entity in entities:
            match = True
            for field, conditions in date_filters.items():
                field_value = getattr(entity, field, None)
                if not field_value:
                    match = False
                    break
                
                field_str = field_value.isoformat() if hasattr(field_value, 'isoformat') else str(field_value)
                
                for op, compare_value in conditions.items():
                    if op == "$gte" and field_str < compare_value:
                        match = False
                        break
                    elif op == "$lte" and field_str > compare_value:
                        match = False
                        break
                
                if not match:
                    break
            
            if match:
                filtered.append(entity)
        
        return filtered
    
    async def list_all(
        self,
        entity_type: Optional[str] = None,
        entity_subtype: Optional[str] = None,
        namespace: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100
    ) -> List[ChromaDBEntity]:
        """Получает список entities БЕЗ семантического поиска (прямой get)"""
        company_id = self._get_company_id()
        chroma_namespace = self._get_namespace()
        
        where, date_filters = self._build_where_filters(
            company_id=company_id,
            entity_type=entity_type,
            entity_subtype=entity_subtype,
            namespace=namespace,
            filters=filters
        )
        
        logger.info(f"list_all() - ChromaDB where: {where}, limit: {limit}")
        
        raw_results = await self._rag.provider.get_raw(
            namespace_id=chroma_namespace,
            where=where,
            limit=limit,
            include=["documents", "metadatas"]
        )
        
        entities = []
        if raw_results.get("ids"):
            for i, doc_id in enumerate(raw_results["ids"]):
                metadata = raw_results["metadatas"][i] if raw_results["metadatas"] else {}
                entities.append(self._metadata_to_model(metadata))
        
        entities = self._apply_date_filters(entities, date_filters)
        
        logger.info(f"list_all() возвращает {len(entities)} entities")
        return entities
    
    async def search(
        self,
        query: str,
        entity_type: Optional[str] = None,
        entity_subtype: Optional[str] = None,
        namespace: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 10
    ) -> List[ChromaDBEntity]:
        """Семантический поиск entities с ранжированием по релевантности"""
        company_id = self._get_company_id()
        chroma_namespace = self._get_namespace()
        
        where, date_filters = self._build_where_filters(
            company_id=company_id,
            entity_type=entity_type,
            entity_subtype=entity_subtype,
            namespace=namespace,
            filters=filters
        )
        
        logger.info(f"search() - query: '{query[:50]}...', where: {where}")
        
        results = await self._rag.search(
            namespace_id=chroma_namespace,
            query=query,
            limit=limit * 2 if date_filters else limit,
            filters=where
        )
        
        entities = [self._metadata_to_model(r.metadata) for r in results]
        entities = self._apply_date_filters(entities, date_filters)
        
        if len(entities) > limit:
            entities = entities[:limit]
        
        logger.info(f"search() возвращает {len(entities)} entities")
        return entities

