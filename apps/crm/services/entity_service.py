"""
Сервис для работы с entities.

Единый сервис для всех типов entities (note, task, contact, organization, etc).
Включает AI анализ с составными промптами и каскадное удаление через Saga.
"""

from collections import deque
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
from apps.crm.services.daily_summary_cache_service import DailySummaryCacheService
from apps.crm.services.saga import EntityDeletionSaga, SagaStep
from core.clients.a2a_client import A2AClient
from core.context import get_context
from core.db.repositories.namespace_repository import NamespaceRepository
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
        namespace_repo: NamespaceRepository,
        attachment_service: AttachmentService,
        a2a_client: A2AClient,
        daily_summary_cache_service: DailySummaryCacheService,
    ):
        self._entity_repo = entity_repo
        self._entity_type_repo = entity_type_repo
        self._relationship_type_repo = relationship_type_repo
        self._relationship_repo = relationship_repo
        self._namespace_repo = namespace_repo
        self._attachment_service = attachment_service
        self._a2a_client = a2a_client
        self._daily_summary_cache_service = daily_summary_cache_service
    
    def _get_company_id(self) -> str:
        context = get_context()
        if not context or not context.active_company:
            raise ValueError("Нет активной компании в контексте")
        return context.active_company.company_id

    @staticmethod
    def _normalize_namespace(namespace: Optional[str]) -> Optional[str]:
        if namespace is None:
            return None
        if namespace.strip() == "":
            return None
        return namespace

    @staticmethod
    def _resolve_namespace_for_write(namespace: Optional[str]) -> str:
        normalized = EntityService._normalize_namespace(namespace)
        if normalized is None:
            return "default"
        return normalized

    async def _ensure_namespace_exists(self, namespace: str) -> None:
        existing_namespace = await self._namespace_repo.get(namespace)
        if existing_namespace is None and namespace == "default":
            await self._namespace_repo.list_all()
            existing_namespace = await self._namespace_repo.get(namespace)
        if existing_namespace is None:
            raise ValueError(f"Namespace not found: {namespace}")

    async def _ensure_entity_type_allowed_in_namespace(
        self,
        entity_type: str,
        namespace: str,
        entity_subtype: Optional[str] = None,
    ) -> None:
        entity_type_model = await self._entity_type_repo.get_by_type_id(entity_type)
        if entity_type_model is None:
            raise ValueError(f"Entity type not found: {entity_type}")
        allowed_namespaces = entity_type_model.namespace_ids or []
        if namespace not in allowed_namespaces:
            raise ValueError(f"Entity type '{entity_type}' is not allowed in namespace '{namespace}'")

        if entity_subtype:
            subtype_model = await self._entity_type_repo.get_by_type_id(entity_subtype)
            if subtype_model is None:
                raise ValueError(f"Entity subtype not found: {entity_subtype}")
            subtype_namespaces = subtype_model.namespace_ids or []
            if namespace not in subtype_namespaces:
                raise ValueError(f"Entity subtype '{entity_subtype}' is not allowed in namespace '{namespace}'")

    async def _list_notes_for_date(self, date_str: str, namespace: Optional[str] = None) -> List[CRMEntity]:
        query_filters: dict[str, Any] = {"note_date": date_str}
        return await self._entity_repo.list_all(
            entity_type="note",
            namespace=self._normalize_namespace(namespace),
            filters=query_filters,
            limit=1000,
        )

    @staticmethod
    def _build_source_version(notes: List[CRMEntity]) -> dict[str, Any]:
        notes_count = len(notes)
        max_updated_at: Optional[str] = None
        for note in notes:
            if note.updated_at is None:
                continue
            note_updated_iso = note.updated_at.isoformat()
            if max_updated_at is None or note_updated_iso > max_updated_at:
                max_updated_at = note_updated_iso
        return {
            "notes_count": notes_count,
            "max_updated_at": max_updated_at,
        }

    async def _collect_notes_and_source_version(
        self,
        date_str: str,
        namespace: Optional[str] = None,
    ) -> tuple[List[CRMEntity], dict[str, Any]]:
        notes = await self._list_notes_for_date(date_str=date_str, namespace=namespace)
        source_version = self._build_source_version(notes)
        return notes, source_version
    
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

        namespace = self._resolve_namespace_for_write(kwargs.get("namespace"))
        kwargs["namespace"] = namespace
        await self._ensure_namespace_exists(namespace)
        await self._ensure_entity_type_allowed_in_namespace(
            entity_type=entity_type,
            namespace=namespace,
            entity_subtype=entity_subtype,
        )
        
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

        if entity.entity_type == "note" and entity.note_date is not None:
            await self.enqueue_daily_summary_rebuild(
                date_str=entity.note_date.isoformat(),
                namespace=entity.namespace,
            )
        
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

        old_note_date = entity.note_date.isoformat() if entity.note_date is not None else None
        old_namespace = entity.namespace
        is_note = entity.entity_type == "note"

        next_namespace = self._resolve_namespace_for_write(
            updates["namespace"] if "namespace" in updates else entity.namespace
        )
        next_entity_type = updates["entity_type"] if "entity_type" in updates else getattr(entity, "entity_type", None)
        next_entity_subtype = (
            updates["entity_subtype"]
            if "entity_subtype" in updates
            else getattr(entity, "entity_subtype", None)
        )
        await self._ensure_namespace_exists(next_namespace)
        await self._ensure_entity_type_allowed_in_namespace(
            entity_type=next_entity_type,
            namespace=next_namespace,
            entity_subtype=next_entity_subtype,
        )
        
        for key, value in updates.items():
            if hasattr(entity, key) and value is not None:
                setattr(entity, key, value)
        entity.namespace = next_namespace
        
        entity.updated_at = datetime.now(timezone.utc)
        await self._entity_repo.update(entity)
        
        logger.info(f"Updated entity: {entity_id}")

        if is_note:
            new_note_date = entity.note_date.isoformat() if entity.note_date is not None else None
            new_namespace = entity.namespace

            if old_note_date is not None:
                await self.enqueue_daily_summary_rebuild(
                    date_str=old_note_date,
                    namespace=old_namespace,
                )
            if new_note_date is not None and (new_note_date != old_note_date or new_namespace != old_namespace):
                await self.enqueue_daily_summary_rebuild(
                    date_str=new_note_date,
                    namespace=new_namespace,
                )
            if new_note_date is not None and new_note_date == old_note_date and new_namespace == old_namespace:
                await self.enqueue_daily_summary_rebuild(
                    date_str=new_note_date,
                    namespace=new_namespace,
                )

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
    
    @staticmethod
    def _get_related_entity_id(relationship: Relationship, current_entity_id: str) -> str:
        if relationship.source_entity_id == current_entity_id:
            return relationship.target_entity_id
        if relationship.target_entity_id == current_entity_id:
            return relationship.source_entity_id
        raise ValueError(
            f"Relationship {relationship.relationship_id} does not include entity {current_entity_id}"
        )

    async def _build_entity_component_relationships(
        self,
        root_entity_id: str,
    ) -> Dict[str, List[Relationship]]:
        queue: deque[str] = deque([root_entity_id])
        visited: set[str] = set()
        relationships_by_entity: Dict[str, List[Relationship]] = {}

        while queue:
            entity_id = queue.popleft()
            if entity_id in visited:
                continue
            visited.add(entity_id)

            relationships = await self._relationship_repo.get_by_entity(entity_id)
            relationships_by_entity[entity_id] = relationships

            for relationship in relationships:
                related_entity_id = self._get_related_entity_id(relationship, entity_id)
                if related_entity_id not in visited:
                    queue.append(related_entity_id)

        return relationships_by_entity

    async def _collect_exclusive_related_entities_for_note(
        self,
        note_entity_id: str,
    ) -> List[str]:
        relationships_by_entity = await self._build_entity_component_relationships(note_entity_id)
        component_order = list(relationships_by_entity.keys())
        entities_to_delete: set[str] = {note_entity_id}

        changed = True
        while changed:
            changed = False
            for entity_id in component_order:
                if entity_id in entities_to_delete:
                    continue

                relationships = relationships_by_entity.get(entity_id, [])
                has_surviving_relationship = False
                for relationship in relationships:
                    related_entity_id = self._get_related_entity_id(relationship, entity_id)
                    if related_entity_id not in entities_to_delete:
                        has_surviving_relationship = True
                        break

                if not has_surviving_relationship:
                    entities_to_delete.add(entity_id)
                    changed = True

        return [
            entity_id
            for entity_id in component_order
            if entity_id in entities_to_delete and entity_id != note_entity_id
        ]

    async def _delete_entity_with_saga(
        self,
        entity_id: str,
    ) -> CRMEntity:
        entity = await self._entity_repo.get(entity_id)
        if not entity:
            raise ValueError(f"Entity not found for deletion: {entity_id}")

        saga = EntityDeletionSaga()
        deleted_relationships: List[Relationship] = []
        async def delete_relationships() -> None:
            nonlocal deleted_relationships
            relationships = await self._relationship_repo.get_by_entity(entity_id)
            deleted_relationships = relationships.copy()
            await self._relationship_repo.delete_by_entity(entity_id)

        async def restore_relationships() -> None:
            for relationship in deleted_relationships:
                await self._relationship_repo.create(relationship)

        async def delete_attachments() -> None:
            await self._attachment_service.delete_all_attachments(entity_id)

        async def restore_attachments() -> None:
            pass

        async def delete_entity_from_db() -> None:
            await self._entity_repo.delete(entity_id)

        async def restore_entity_to_db() -> None:
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
        return entity

    async def delete_entity(
        self,
        entity_id: str,
    ) -> bool:
        """
        Каскадное удаление entity через Saga pattern.

        Для note: удаляет саму заметку и эксклюзивно связанные сущности.
        Эксклюзивная сущность - та, у которой после удаления note не остается связей
        с сущностями вне удаляемого подграфа.
        """
        entity = await self._entity_repo.get(entity_id)
        if not entity:
            logger.warning(f"Entity not found for deletion: {entity_id}")
            return False

        if entity.entity_type == "note":
            exclusive_related_entity_ids = await self._collect_exclusive_related_entities_for_note(entity_id)
            for related_entity_id in exclusive_related_entity_ids:
                await self._delete_entity_with_saga(related_entity_id)
                logger.info(f"Deleted exclusive related entity for note {entity_id}: {related_entity_id}")

            await self._delete_entity_with_saga(entity_id)
            logger.info(
                f"Successfully deleted note {entity_id} with {len(exclusive_related_entity_ids)} exclusive entities"
            )
        else:
            await self._delete_entity_with_saga(entity_id)
            logger.info(f"Successfully deleted entity: {entity_id} (cascade)")

        if entity.entity_type == "note" and entity.note_date is not None:
            await self.enqueue_daily_summary_rebuild(
                date_str=entity.note_date.isoformat(),
                namespace=entity.namespace,
            )

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
        namespace = self._resolve_namespace_for_write(request.namespace)
        await self._ensure_namespace_exists(namespace)
        entity_types = await self._entity_type_repo.get_all_for_company(namespace=namespace)
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
            mentioned_entity_ids=request.mentioned_entity_ids,
            entity_types=entity_types,
            relationship_types=relationship_types,
        )
        
        if check_duplicates and ai_result.entities:
            dedup_results = await self._deduplicate_entities(
                extracted_entities=ai_result.entities,
                namespace=namespace,
            )
            
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
        mentioned_entity_ids: Optional[List[str]],
        entity_types: List,
        relationship_types: List,
    ) -> AIAnalyzeResponse:
        """Вызывает AI agent через A2A API для анализа"""
        from core.config import get_settings
        
        settings = get_settings()
        
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
        
        # Извлекаем и нормализуем данные из A2A response
        result_data = self._extract_data_from_a2a_response(response)
        normalized_result = self._normalize_analyze_result(result_data)
        
        return AIAnalyzeResponse(
            note=normalized_result.get("note"),
            entities=normalized_result.get("entities", []),
            relationships=normalized_result.get("relationships", [])
        )

    def _normalize_entity_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Приводит entity payload к ожидаемому контракту CRM."""
        normalized = dict(payload)
        if "entity_type" not in normalized and "type" in normalized:
            normalized["entity_type"] = normalized["type"]
        return normalized

    def _normalize_analyze_result(self, result_data: Dict[str, Any]) -> Dict[str, Any]:
        """Нормализует ответ analyze от flows перед Pydantic-валидацией."""
        normalized = dict(result_data)

        note_data = normalized.get("note")
        if isinstance(note_data, dict):
            normalized["note"] = self._normalize_entity_payload(note_data)

        entities_data = normalized.get("entities")
        if isinstance(entities_data, list):
            normalized["entities"] = [
                self._normalize_entity_payload(entity)
                if isinstance(entity, dict)
                else entity
                for entity in entities_data
            ]

        return normalized
    
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
        artifacts = task_result.get("artifacts")
        if artifacts is None:
            artifacts = []

        if not artifacts:
            plain = (response.get("response") or "").strip()
            if plain:
                extracted = self._extract_json_from_text(plain)
                if extracted:
                    return extracted
            return {}

        for artifact in artifacts:
            if "parts" not in artifact:
                continue
            
            for part in artifact["parts"]:
                part_kind = part.get("kind") or part.get("type")
                
                if part_kind == "data" and "data" in part:
                    data = part["data"]
                    if not isinstance(data, dict):
                        continue
                    if "res" in data:
                        try:
                            parsed = json.loads(data["res"])
                        except (json.JSONDecodeError, TypeError):
                            parsed = None
                        if isinstance(parsed, dict):
                            return parsed
                        continue
                    if any(
                        k in data
                        for k in (
                            "entities",
                            "relationships",
                            "note",
                            "is_duplicate",
                            "summary",
                            "structured_output",
                        )
                    ):
                        return data
                    content = data.get("content")
                    if isinstance(content, str) and content.strip():
                        extracted = self._extract_json_from_text(content)
                        if extracted:
                            return extracted
                    continue

                if part_kind == "text" and "text" in part:
                    text = part["text"]
                    extracted = self._extract_json_from_text(text)
                    if extracted:
                        return extracted

        plain = (response.get("response") or "").strip()
        if plain:
            extracted = self._extract_json_from_text(plain)
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

    def _extract_summary_from_payload(self, payload: Any) -> Optional[str]:
        """Извлекает summary из вложенного payload A2A ответа."""
        if isinstance(payload, dict):
            summary_value = payload.get("summary")
            if isinstance(summary_value, str) and summary_value.strip():
                return summary_value

            if "structured_output" in payload:
                nested_summary = self._extract_summary_from_payload(payload["structured_output"])
                if nested_summary is not None:
                    return nested_summary

            for nested_value in payload.values():
                nested_summary = self._extract_summary_from_payload(nested_value)
                if nested_summary is not None:
                    return nested_summary
            return None

        if isinstance(payload, list):
            for item in payload:
                nested_summary = self._extract_summary_from_payload(item)
                if nested_summary is not None:
                    return nested_summary
            return None

        return None

    def _extract_string_list_from_payload(self, payload: Any, key: str) -> list[str]:
        """Извлекает список строк по ключу из вложенного payload."""
        if isinstance(payload, dict):
            raw_value = payload.get(key)
            if isinstance(raw_value, list):
                collected: list[str] = []
                for item in raw_value:
                    if isinstance(item, str):
                        normalized = item.strip()
                        if normalized:
                            collected.append(normalized)
                if collected:
                    return collected
            if "structured_output" in payload:
                nested = self._extract_string_list_from_payload(payload["structured_output"], key)
                if nested:
                    return nested
            for nested_value in payload.values():
                nested = self._extract_string_list_from_payload(nested_value, key)
                if nested:
                    return nested
            return []

        if isinstance(payload, list):
            for item in payload:
                nested = self._extract_string_list_from_payload(item, key)
                if nested:
                    return nested
            return []

        return []

    @staticmethod
    def _normalize_entity_name(entity_name: str) -> Optional[str]:
        normalized = entity_name.strip()
        if not normalized:
            return None
        if normalized.startswith("@"):
            normalized = normalized[1:]
        normalized = normalized.strip(".,;:!?()[]{}\"'")
        if not normalized:
            return None
        return normalized

    def _extract_entities_from_text_mentions(self, text: str) -> list[str]:
        if not text:
            return []
        mention_matches = re.findall(r"@([^\s,.;:!?(){}\[\]]+)", text)
        entities: list[str] = []
        seen: set[str] = set()
        for mention in mention_matches:
            normalized = self._normalize_entity_name(mention)
            if normalized is None:
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            entities.append(normalized)
        return entities

    def _extract_entities_from_notes(self, notes: list[CRMEntity]) -> list[str]:
        entities: list[str] = []
        seen: set[str] = set()

        def append_entity(raw_name: str) -> None:
            normalized = self._normalize_entity_name(raw_name)
            if normalized is None:
                return
            key = normalized.lower()
            if key in seen:
                return
            seen.add(key)
            entities.append(normalized)

        for note in notes:
            note_tags = getattr(note, "tags", [])
            if isinstance(note_tags, list):
                for tag in note_tags:
                    if isinstance(tag, str):
                        append_entity(tag)

            note_name = getattr(note, "name", "")
            if isinstance(note_name, str):
                for entity_name in self._extract_entities_from_text_mentions(note_name):
                    append_entity(entity_name)

            note_description = getattr(note, "description", "")
            if isinstance(note_description, str):
                for entity_name in self._extract_entities_from_text_mentions(note_description):
                    append_entity(entity_name)

            attributes = getattr(note, "attributes", {})
            if isinstance(attributes, dict):
                mentioned_entities = attributes.get("mentioned_entities")
                if isinstance(mentioned_entities, list):
                    for entity_name in mentioned_entities:
                        if isinstance(entity_name, str):
                            append_entity(entity_name)

        return entities
    
    async def compute_daily_summary(
        self,
        date_str: str,
        namespace: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Синхронно вычисляет summary для даты и namespace."""
        company_id = self._get_company_id()
        dt.fromisoformat(date_str)

        notes, source_version = await self._collect_notes_and_source_version(
            date_str=date_str,
            namespace=namespace,
        )

        if not notes:
            return {
                "date": date_str,
                "namespace": self._normalize_namespace(namespace),
                "summary": f"За {date_str} заметок не найдено.",
                "entities": [],
                "entities_count": 0,
                "source_version": source_version,
            }

        input_entities = self._extract_entities_from_notes(notes)
        payload = {
            "notes": [self._entity_to_dict(note) for note in notes],
            "date": date_str,
            "namespace": self._normalize_namespace(namespace),
            "entities": input_entities,
        }

        settings = get_settings()
        flows_url = settings.server.get_flows_service_url()
        response = await self._a2a_client.send_task(
            base_url=f"{flows_url}/flows/api/v1/crm",
            content=json.dumps(payload),
            skill_id="summarize",
            metadata={"company_id": company_id},
        )

        structured = self._extract_data_from_a2a_response(response)
        raw = (response.get("response") or "").strip()
        parsed = self._extract_json_from_text(raw) if raw else {}
        summary_text = self._extract_summary_from_payload(structured)
        if summary_text is None:
            summary_text = self._extract_summary_from_payload(parsed)
        if summary_text is None:
            summary_text = raw
        summary_entities = self._extract_string_list_from_payload(structured, "entities")
        if not summary_entities:
            summary_entities = self._extract_string_list_from_payload(parsed, "entities")
        if not summary_entities:
            summary_entities = self._extract_entities_from_text_mentions(summary_text)
        if not summary_entities:
            summary_entities = input_entities

        return {
            "date": date_str,
            "namespace": self._normalize_namespace(namespace),
            "summary": summary_text,
            "entities": summary_entities[:8],
            "entities_count": len(notes),
            "source_version": source_version,
        }

    async def rebuild_daily_summary(
        self,
        date_str: str,
        namespace: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Пересчитывает и сохраняет daily summary в Redis state."""
        company_id = self._get_company_id()
        lock_acquired = await self._daily_summary_cache_service.acquire_rebuild_lock(
            company_id=company_id,
            namespace=namespace,
            date_str=date_str,
        )
        if not lock_acquired:
            state = await self._daily_summary_cache_service.get_state(
                company_id=company_id,
                namespace=namespace,
                date_str=date_str,
            )
            if state is None:
                return {
                    "date": date_str,
                    "namespace": self._normalize_namespace(namespace),
                    "summary": "",
                    "entities": [],
                    "entities_count": 0,
                    "revalidating": True,
                    "generated_at": None,
                    "source_version": {
                        "notes_count": 0,
                        "max_updated_at": None,
                    },
                    "stale": True,
                }
            if not isinstance(state.get("entities"), list):
                state["entities"] = []
            state["revalidating"] = True
            state["stale"] = True
            return state
        try:
            summary = await self.compute_daily_summary(date_str=date_str, namespace=namespace)
            state = {
                **summary,
                "revalidating": False,
                "stale": False,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            await self._daily_summary_cache_service.set_state(
                company_id=company_id,
                namespace=namespace,
                date_str=date_str,
                state=state,
            )
            await self._daily_summary_cache_service.clear_revalidating(
                company_id=company_id,
                namespace=namespace,
                date_str=date_str,
            )
            return state
        except Exception:
            await self._daily_summary_cache_service.clear_revalidating(
                company_id=company_id,
                namespace=namespace,
                date_str=date_str,
            )
            raise
        finally:
            await self._daily_summary_cache_service.release_rebuild_lock(
                company_id=company_id,
                namespace=namespace,
                date_str=date_str,
            )

    async def enqueue_daily_summary_rebuild(
        self,
        date_str: str,
        namespace: Optional[str] = None,
    ) -> bool:
        """Ставит задачу пересчета summary, если она ещё не в процессе."""
        company_id = self._get_company_id()
        became_revalidating = await self._daily_summary_cache_service.set_revalidating(
            company_id=company_id,
            namespace=namespace,
            date_str=date_str,
        )
        if not became_revalidating:
            return False

        from apps.crm_worker.tasks.daily_summary_tasks import rebuild_daily_summary_task
        context = get_context()
        auth_token = context.auth_token if context else None
        user_id = context.user.user_id if context and context.user else None

        await rebuild_daily_summary_task.kiq(
            company_id=company_id,
            date_str=date_str,
            namespace=self._normalize_namespace(namespace),
            reason="event",
            auth_token=auth_token,
            user_id=user_id,
        )
        return True

    async def mark_daily_summary_dirty(
        self,
        date_str: str,
        namespace: Optional[str] = None,
    ) -> bool:
        """Публичный alias для event-driven invalidation."""
        return await self.enqueue_daily_summary_rebuild(date_str=date_str, namespace=namespace)

    async def get_daily_summary_cached(
        self,
        date_str: str,
        namespace: Optional[str] = None,
        force_rebuild: bool = False,
    ) -> Dict[str, Any]:
        """Возвращает summary по SWR: stale-while-revalidate."""
        company_id = self._get_company_id()
        dt.fromisoformat(date_str)

        _, current_version = await self._collect_notes_and_source_version(
            date_str=date_str,
            namespace=namespace,
        )
        cached_state = await self._daily_summary_cache_service.get_state(
            company_id=company_id,
            namespace=namespace,
            date_str=date_str,
        )
        is_revalidating = await self._daily_summary_cache_service.is_revalidating(
            company_id=company_id,
            namespace=namespace,
            date_str=date_str,
        )

        if force_rebuild and not is_revalidating:
            await self.enqueue_daily_summary_rebuild(date_str=date_str, namespace=namespace)
            is_revalidating = True

        if cached_state is None:
            if not is_revalidating:
                await self.enqueue_daily_summary_rebuild(date_str=date_str, namespace=namespace)
            return {
                "date": date_str,
                "namespace": self._normalize_namespace(namespace),
                "summary": "",
                "entities": [],
                "entities_count": 0,
                "generated_at": None,
                "source_version": current_version,
                "revalidating": True,
                "stale": True,
            }

        cached_version = cached_state.get("source_version")
        cached_stale = cached_state.get("stale") is True
        is_stale = cached_version != current_version
        cached_entities = cached_state.get("entities")
        normalized_entities: list[str] = []
        if isinstance(cached_entities, list):
            for entity_name in cached_entities:
                if isinstance(entity_name, str):
                    normalized = entity_name.strip()
                    if normalized:
                        normalized_entities.append(normalized)

        if is_stale and not is_revalidating:
            await self.enqueue_daily_summary_rebuild(date_str=date_str, namespace=namespace)
            is_revalidating = True

        return {
            **cached_state,
            "entities": normalized_entities,
            "source_version": current_version if is_stale else cached_version,
            "revalidating": is_revalidating,
            "stale": is_stale or force_rebuild or cached_stale or is_revalidating,
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
                    "company_id": rel.company_id,
                    "namespace": rel.namespace,
                    "source_entity_id": rel.source_entity_id,
                    "target_entity_id": rel.target_entity_id,
                    "relationship_type": rel.relationship_type,
                    "weight": rel.weight,
                    "attributes": rel.attributes,
                    "created_at": rel.created_at.isoformat() if rel.created_at else None,
                    "updated_at": rel.updated_at.isoformat() if rel.updated_at else None,
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
        extracted_entities: List[AIExtractedEntity],
        namespace: str,
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
                namespace=namespace,
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