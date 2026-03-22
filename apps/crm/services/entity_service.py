"""
Сервис для работы с entities.

Единый сервис для всех типов entities (note, task, contact, organization, etc).
Включает AI анализ с составными промптами и каскадное удаление через Saga.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import uuid
import re

from apps.crm.db.models import CRMEntity
from apps.crm.models.api import (
    AIAnalyzeRequest, 
    AIAnalyzeResponse, 
    AIExtractedEntity,
    DeduplicateResult
)
from apps.crm.db.repositories.entity_repository import EntityRepository
from apps.crm.db.repositories.entity_type_repository import EntityTypeRepository
from apps.crm.db.repositories.relationship_type_repository import RelationshipTypeRepository
from apps.crm.db.repositories.relationship_repository import RelationshipRepository
from apps.crm.db.models import Relationship
from apps.crm.services.attachment_service import AttachmentService
from apps.crm.services.saga import EntityDeletionSaga, SagaStep
from core.clients.a2a_client import A2AClient
from core.context import get_context
from core.logging import get_logger
import json
from datetime import datetime as dt
logger = get_logger(__name__)
from core.config import get_settings

class EntityService:
    """
    Сервис для работы с entities в CRM.
    
    Основные функции:
    - CRUD operations для любого типа entity
    - AI анализ текста с составными промптами
    - Извлечение entities и relationships
    - Каскадное удаление через Saga pattern
    """
    
    def __init__(
        self,
        entity_repo: EntityRepository,
        entity_type_repo: EntityTypeRepository,
        relationship_type_repo: RelationshipTypeRepository,
        relationship_repo: RelationshipRepository,
        attachment_service: AttachmentService,
        a2a_client: A2AClient
    ):
        self._entity_repo = entity_repo
        self._entity_type_repo = entity_type_repo
        self._relationship_type_repo = relationship_type_repo
        self._relationship_repo = relationship_repo
        self._attachment_service = attachment_service
        self._a2a_client = a2a_client
    
    def _get_company_id(self) -> str:
        context = get_context()
        if not context or not context.active_company:
            raise ValueError("Нет активной компании в контексте")
        return context.active_company.company_id
    
    async def create_entity(
        self, 
        entity_type: str,
        name: str,
        description: Optional[str] = None,
        entity_subtype: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        
        **kwargs
    ) -> CRMEntity:
        """Создает новую entity"""
        
        # user_id ОБЯЗАТЕЛЕН - берем из kwargs или из контекста
        user_id = kwargs.pop("user_id", None)
        if not user_id:
            context = get_context()
            if not context or not context.user:
                raise ValueError("user_id is required (no user in context)")
            user_id = context.user.user_id
        
        entity = CRMEntity(
            user_id=user_id,
            entity_id=str(uuid.uuid4()),
            entity_type=entity_type,
            entity_subtype=entity_subtype,
            name=name,
            description=description,
            attributes=attributes or {},
            tags=tags or [],
            company_id=self._get_company_id(),
            **kwargs
        )
        
        await self._entity_repo.create(entity)
        logger.info(f"Created entity: {entity.entity_id}, type={entity.full_type}")
        
        return entity
    
    async def get_entity(
        self, 
        entity_id: str,
        
    ) -> Optional[CRMEntity]:
        """Получает entity по ID"""
        
        return await self._entity_repo.get(entity_id)
    
    async def update_entity(
        self, 
        entity_id: str,
        updates: Dict[str, Any],
        
    ) -> CRMEntity:
        """Обновляет entity"""
        
        
        entity = await self._entity_repo.get(entity_id)
        if not entity:
            raise ValueError(f"Entity not found: {entity_id}")
        
        for key, value in updates.items():
            if hasattr(entity, key) and value is not None:
                setattr(entity, key, value)
        
        entity.updated_at = datetime.now(timezone.utc)
        await self._entity_repo.update(entity)
        
        logger.info(f"Updated entity: {entity_id}")
        return entity
    
    async def list_entities(
        self,
        entity_type: Optional[str] = None,
        entity_subtype: Optional[str] = None,
        namespace: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
    ) -> List[CRMEntity]:
        """Получает список entities БЕЗ семантического поиска"""
        return await self._entity_repo.list_all(
            entity_type=entity_type,
            entity_subtype=entity_subtype,
            namespace=namespace,
            filters=filters,
            limit=limit,
        )
    
    async def delete_entity(
        self,
        entity_id: str,
        
    ) -> bool:
        """
        Каскадное удаление entity через Saga pattern.
        
        Шаги:
        1. Удалить все relationships
        2. Удалить все attachments
        3. Удалить entity из БД + vector_documents
        """
        
        
        entity = await self._entity_repo.get(entity_id)
        if not entity:
            logger.warning(f"Entity not found for deletion: {entity_id}")
            return False
        
        saga = EntityDeletionSaga()
        
        deleted_relationships = []
        deleted_attachments = []
        
        async def delete_relationships():
            nonlocal deleted_relationships
            rels = await self._relationship_repo.get_by_entity(entity_id)
            deleted_relationships = rels.copy()
            await self._relationship_repo.delete_by_entity(entity_id)
        
        async def restore_relationships():
            for rel in deleted_relationships:
                await self._relationship_repo.create(rel)
    
        async def delete_attachments():
            nonlocal deleted_attachments
            deleted_count = await self._attachment_service.delete_all_attachments(
                entity_id
            )
            deleted_attachments = entity.attachment_ids.copy()
        
        async def restore_attachments():
            pass
        
        async def delete_entity_from_db():
            await self._entity_repo.delete(entity_id)
        
        async def restore_entity_to_db():
            await self._entity_repo.create(entity)
        
        saga.add_step(SagaStep(
            name="Delete relationships",
            execute_fn=delete_relationships,
            compensate_fn=restore_relationships
        ))
        
        saga.add_step(SagaStep(
            name="Delete attachments",
            execute_fn=delete_attachments,
            compensate_fn=restore_attachments
        ))
        
        saga.add_step(SagaStep(
            name="Delete entity",
            execute_fn=delete_entity_from_db,
            compensate_fn=restore_entity_to_db
        ))
        
        await saga.execute()
        logger.info(f"Successfully deleted entity: {entity_id} (cascade)")
        
        return True
    
    async def search_entities(
        self,
        query: str,
        entity_type: Optional[str] = None,
        entity_subtype: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        
    ) -> List[CRMEntity]:
        """Семантический поиск entities с поддержкой всех фильтров"""
        
        return await self._entity_repo.search(
            query=query,
            entity_type=entity_type,
            entity_subtype=entity_subtype,
            filters=filters,
            limit=limit,
            
        )
    
    async def search_mentions(
        self,
        text: str,
        limit: int = 20
    ) -> List[CRMEntity]:
        """
        Real-time поиск упоминаний entities в тексте для подсветки.
        
        Использует семантический поиск + keyword matching для быстрого поиска.
        """
        if not text or len(text) < 3:
            return []
        
        words = text.lower().split()
        search_phrases = []
        
        for i in range(len(words)):
            if i + 1 < len(words):
                search_phrases.append(f"{words[i]} {words[i+1]}")
            search_phrases.append(words[i])
        
        unique_phrases = list(set(search_phrases))[:5]
        
        combined_query = " ".join(unique_phrases)
        
        try:
            entities = await self._entity_repo.search(
                query=combined_query,
                limit=limit
            )
            
            entities_with_keyword_match = []
            for entity in entities:
                name_lower = entity.name.lower()
                if any(phrase in name_lower for phrase in unique_phrases):
                    entities_with_keyword_match.append(entity)
            
            if entities_with_keyword_match:
                return entities_with_keyword_match
            
            return entities[:10]
            
        except Exception as e:
            logger.error(f"Failed to search mentions: {e}")
            return []
    
    async def analyze_text_with_ai(
        self,
        request: AIAnalyzeRequest,
        check_duplicates: bool = True
    ) -> AIAnalyzeResponse:
        """
        AI анализ текста с составными промптами.
        
        Строит промпт из:
        1. EntityType.prompt для базовых типов (note, task)
        2. EntityType.prompt для подтипов (meeting, call)
        3. RelationshipType.prompt для связей (mentions, works_for)
        
        Args:
            request: Запрос на анализ
            check_duplicates: Проверять ли дубликаты (по умолчанию True)
        """
        entity_types = await self._entity_type_repo.get_all_for_company()
        relationship_types = await self._relationship_type_repo.get_with_prompts()
        
        prompt = self._build_composite_prompt(
            entity_types,
            relationship_types,
            request.extract_entity_types,
            request.extract_relationship_types
        )
        
        ai_result = await self._call_ai_agent(
            text=request.text,
            prompt=prompt,
            mentioned_entity_ids=request.mentioned_entity_ids
        )
        
        if check_duplicates and ai_result.entities:
            dedup_results = await self._deduplicate_entities(ai_result.entities)
            
            for i, entity in enumerate(ai_result.entities):
                if i < len(dedup_results):
                    result = dedup_results[i]
                    entity.dedup_action = result.action
                    entity.dedup_confidence = result.confidence
                    if result.is_duplicate:
                        entity.dedup_existing_id = result.existing_entity_id
                        entity.dedup_existing_name = result.existing_entity_name
        
        return ai_result
    
    def _build_composite_prompt(
        self,
        entity_types: List,
        relationship_types: List,
        extract_entity_types: Optional[List[str]],
        extract_relationship_types: Optional[List[str]]
    ) -> str:
        """Строит составной промпт из типов"""
        prompt_parts = [
            "Проанализируй текст и извлеки следующие сущности и связи:",
            "",
            "ТИПЫ СУЩНОСТЕЙ:"
        ]
        
        for et in entity_types:
            if extract_entity_types and et.type_id not in extract_entity_types:
                continue
            
            if et.prompt:
                prompt_parts.append(f"\n{et.name} ({et.type_id}):")
                prompt_parts.append(et.prompt)
        
        prompt_parts.append("\nТИПЫ СВЯЗЕЙ:")
        
        for rt in relationship_types:
            if extract_relationship_types and rt.type_id not in extract_relationship_types:
                continue
            
            if rt.prompt:
                prompt_parts.append(f"\n{rt.name} ({rt.type_id}):")
                prompt_parts.append(rt.prompt)
        
        return "\n".join(prompt_parts)
    
    async def _call_ai_agent(
        self,
        text: str,
        prompt: str,
        mentioned_entity_ids: Optional[List[str]]
    ) -> AIAnalyzeResponse:
        """Вызывает AI agent через A2A API для анализа"""
        from core.config import get_settings
        
        settings = get_settings()
        
        # Получаем типы из БД (уже с company_id из контекста)
        entity_types = await self._entity_type_repo.get_all_for_company()
        relationship_types = await self._relationship_type_repo.get_with_prompts()
        
        # Формируем переменные для агента
        variables = {
            "text": text,
            "entity_types": [
                {"type": et.type_id, "prompt": et.prompt or ""}
                for et in entity_types if et.prompt
            ],
            "relationship_types": [
                {"type": rt.type_id, "prompt": rt.prompt or ""}
                for rt in relationship_types if rt.prompt
            ]
        }
        
        flows_base_url = settings.server.get_flows_service_url().rstrip("/")

        response = await self._a2a_client.send_task(
            base_url=f"{flows_base_url}/flows/api/v1/crm",
            content=text,
            skill_id="analyze",
            metadata={
                "variables": variables
            }
        )
        
        # Извлекаем данные из A2A response
        result_data = self._extract_data_from_a2a_response(response)
        
        return AIAnalyzeResponse(
            note=result_data.get("note"),
            entities=result_data.get("entities", []),
            relationships=result_data.get("relationships", [])
        )
    
    def _extract_data_from_a2a_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Извлекает структурированные данные из A2A response.
        
        Поддерживает:
        1. data parts в artifacts
        2. text parts с JSON в markdown (```json ... ```)
        """
        # A2AClient возвращает нормализованный ответ с полем raw
        raw_response = response.get("raw", response)
        
        if "result" not in raw_response:
            return {}
        
        task_result = raw_response["result"]
        
        if "artifacts" not in task_result:
            return {}
        
        for artifact in task_result["artifacts"]:
            if "parts" not in artifact:
                continue
            
            for part in artifact["parts"]:
                part_kind = part.get("kind") or part.get("type")
                
                if part_kind == "data" and "data" in part:
                    data = part["data"]
                    if "res" in data:
                        try:
                            return json.loads(data["res"])
                        except (json.JSONDecodeError, TypeError):
                            pass
                    return data
                
                if part_kind == "text" and "text" in part:
                    text = part["text"]
                    extracted = self._extract_json_from_text(text)
                    if extracted:
                        return extracted
        
        return {}
    
    def _extract_json_from_text(self, text: str) -> Dict[str, Any]:
        """Извлекает JSON из текста (включая markdown code blocks)."""
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
        if json_match:
            try:
                return json.loads(json_match.group(1).strip())
            except (json.JSONDecodeError, TypeError):
                pass
        
        try:
            return json.loads(text.strip())
        except (json.JSONDecodeError, TypeError):
            pass
        
        return {}
    
    async def generate_daily_summary(
        self,
        date_str: str
    ) -> Dict[str, Any]:
        """
        Генерирует daily саммари заметок через crm_summarizer агент.
        
        Args:
            date_str: Дата в формате ISO (YYYY-MM-DD)
        
        Returns:
            Dict с полями: date, summary, entities_count
        """
        company_id = self._get_company_id()
        
        
        date_obj = dt.fromisoformat(date_str).date() if isinstance(date_str, str) else date_str
        
        notes = await self._entity_repo.list_all(
            entity_type="note",
            filters={"note_date": date_str},
            limit=1000,
            
        )
        
        if not notes:
            return {
                "date": date_str,
                "summary": f"За {date_str} заметок не найдено.",
                "entities_count": 0
            }
        
        payload = {
            "notes": [self._entity_to_dict(n) for n in notes],
            "date": date_str
        }
        
        
        settings = get_settings()
        flows_url = settings.server.get_flows_service_url()
        
        response = await self._a2a_client.send_task(
            base_url=f"{flows_url}/flows/api/v1/crm",
            content=json.dumps(payload),
            skill_id="summarize",
            metadata={"company_id": company_id}
        )
        
        return {
            "date": date_str,
            "summary": response.get("response", ""),
            "entities_count": len(notes)
        }
    
    async def get_entity_card(
        self,
        entity_id: str,
        
    ) -> Dict[str, Any]:
        """
        Получает полную карточку entity с контекстом:
        - Данные entity
        - Все relationships
        - Связанные entities
        - Attachments
        
        Args:
            entity_id: ID entity
            company_id: ID компании
        
        Returns:
            Dict с полной информацией о entity
        """
        
        
        entity = await self._entity_repo.get(entity_id)
        if not entity:
            raise ValueError(f"Entity not found: {entity_id}")
        
        relationships = await self._relationship_repo.get_by_entity(entity_id)
        
        related_entity_ids = set()
        for rel in relationships:
            if rel.source_entity_id == entity_id:
                related_entity_ids.add(rel.target_entity_id)
            else:
                related_entity_ids.add(rel.source_entity_id)
        
        related_entities = []
        for rel_entity_id in related_entity_ids:
            rel_entity = await self._entity_repo.get(rel_entity_id)
            if rel_entity:
                related_entities.append(rel_entity)
        
        attachments = await self._attachment_service.get_attachments(entity_id)
        
        return {
            "entity": self._entity_to_dict(entity),
            "relationships": [
                {
                    "relationship_id": rel.relationship_id,
                    "source_entity_id": rel.source_entity_id,
                    "target_entity_id": rel.target_entity_id,
                    "relationship_type": rel.relationship_type,
                    "weight": rel.weight,
                    "attributes": rel.attributes
                }
                for rel in relationships
            ],
            "related_entities": [self._entity_to_dict(e) for e in related_entities],
            "attachments": attachments
        }
    
    @staticmethod
    def _entity_to_dict(entity: CRMEntity) -> Dict[str, Any]:
        """Конвертирует SQLAlchemy CRMEntity в dict."""
        return {
            "entity_id": entity.entity_id,
            "company_id": entity.company_id,
            "namespace": entity.namespace,
            "entity_type": entity.entity_type,
            "entity_subtype": entity.entity_subtype,
            "name": entity.name,
            "description": entity.description,
            "status": entity.status,
            "tags": entity.tags or [],
            "attributes": entity.attributes or {},
            "priority": entity.priority,
            "due_date": entity.due_date.isoformat() if entity.due_date else None,
            "note_date": entity.note_date.isoformat() if entity.note_date else None,
            "assignees": entity.assignees or [],
            "attachment_ids": entity.attachment_ids or [],
            "user_id": entity.user_id,
            "source_entity_id": entity.source_entity_id,
            "source_company_id": entity.source_company_id,
            "relevance": entity.relevance,
            "created_at": entity.created_at.isoformat() if entity.created_at else None,
            "updated_at": entity.updated_at.isoformat() if entity.updated_at else None,
        }

    def _parse_explicit_links(self, text: str) -> List[str]:
        """
        Парсит явные ссылки @entity:id из текста.
        
        Создает связи типа "linked" (НЕ через AI!)
        """
        pattern = r'@entity:([a-f0-9-]+)'
        matches = re.findall(pattern, text)
        return matches
    
    async def _deduplicate_entities(
        self,
        extracted_entities: List[AIExtractedEntity]
    ) -> List[DeduplicateResult]:
        """
        Проверяет каждую entity на дубликат.
        
        Логика:
        1. Семантический поиск по name + description
        2. similarity > 0.95 -> точный дубликат, merge сразу
        3. similarity 0.7-0.95 -> вызов LLM для уточнения
        4. similarity < 0.7 -> новая entity
        """
        results = []
        
        for entity in extracted_entities:
            search_query = f"{entity.name} {entity.description or ''}"
            candidates = await self._entity_repo.search(
                query=search_query,
                entity_type=entity.entity_type,
                limit=3
            )
            
            if not candidates:
                results.append(DeduplicateResult(
                    is_duplicate=False,
                    confidence=0.0,
                    reason="No candidates found",
                    action="create"
                ))
                continue
            
            top_candidate = candidates[0]
            similarity = top_candidate.relevance
            
            if similarity > 0.95:
                merged_attrs = {**(top_candidate.attributes or {}), **(entity.attributes or {})}
                results.append(DeduplicateResult(
                    is_duplicate=True,
                    confidence=similarity,
                    reason="High similarity match",
                    action="merge",
                    existing_entity_id=top_candidate.entity_id,
                    existing_entity_name=top_candidate.name,
                    merged_attributes=merged_attrs,
                    merged_description=self._merge_descriptions(
                        top_candidate.description, entity.description
                    )
                ))
            elif similarity >= 0.7:
                dedup_result = await self._call_deduplicate_agent(entity, top_candidate)
                results.append(dedup_result)
            else:
                results.append(DeduplicateResult(
                    is_duplicate=False,
                    confidence=similarity,
                    reason="Low similarity",
                    action="create"
                ))
        
        return results
    
    def _merge_descriptions(self, existing: Optional[str], new: Optional[str]) -> str:
        """Объединяет описания"""
        if not existing:
            return new or ""
        if not new:
            return existing
        if new.lower() in existing.lower():
            return existing
        return f"{existing}\n\n{new}"
    
    async def _call_deduplicate_agent(
        self,
        extracted: AIExtractedEntity,
        candidate: CRMEntity
    ) -> DeduplicateResult:
        """Вызывает агента со skill deduplicate для сравнения сущностей"""
        settings = get_settings()
        flows_base_url = settings.server.get_flows_service_url().rstrip("/")

        variables = {
            "extracted_entity": {
                "type": extracted.entity_type,
                "name": extracted.name,
                "description": extracted.description,
                "attributes": extracted.attributes
            },
            "candidate_entity": {
                "entity_id": candidate.entity_id,
                "type": candidate.entity_type,
                "name": candidate.name,
                "description": candidate.description,
                "attributes": candidate.attributes
            }
        }
        
        response = await self._a2a_client.send_task(
            base_url=f"{flows_base_url}/flows/api/v1/crm",
            content=f"Compare: {extracted.name} vs {candidate.name}",
            skill_id="deduplicate",
            metadata={"variables": variables}
        )
        
        result_data = self._extract_data_from_a2a_response(response)
        
        return DeduplicateResult(
            is_duplicate=result_data.get("is_duplicate", False),
            confidence=result_data.get("confidence", 0.0),
            reason=result_data.get("reason", ""),
            action=result_data.get("action", "create"),
            existing_entity_id=candidate.entity_id if result_data.get("is_duplicate") else None,
            existing_entity_name=candidate.name if result_data.get("is_duplicate") else None,
            merged_attributes=result_data.get("merged_attributes"),
            merged_description=result_data.get("merged_description")
        )