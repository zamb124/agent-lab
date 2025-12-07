"""
AgentsClient - HTTP клиент для вызова AI агентов из apps/agents.

CRM вызывает apps/agents через Flow API с синхронным ожиданием результата.
"""

import json
import logging
import re
import uuid
from typing import Dict, Any, List, Optional

from core.http import get_httpx_client
from core.context import get_context

logger = logging.getLogger(__name__)


class AgentsUnavailableError(Exception):
    """AI сервис агентов недоступен или flow не найден"""
    pass


class AgentsClient:
    """
    HTTP клиент для вызова CRM агентов в apps/agents через Flow API.
    
    Flows:
    - crm_entity_extractor - извлечение сущностей из текста
    - crm_entity_comparison - сравнение/дедупликация сущностей
    """
    
    DEFAULT_TIMEOUT = 180.0  # 3 минуты на выполнение AI
    
    def __init__(self, agents_base_url: str):
        self._base_url = agents_base_url.rstrip("/")
    
    def _get_headers(self) -> Dict[str, str]:
        """Формирует заголовки с контекстом"""
        headers = {"Content-Type": "application/json"}
        
        context = get_context()
        logger.info(f"AgentsClient context: {context is not None}, auth_token: {bool(context.auth_token) if context else False}")
        if context:
            if context.trace_id:
                headers["X-Trace-Id"] = context.trace_id
            if context.active_company:
                headers["X-Company-Id"] = context.active_company.company_id
            if context.user:
                headers["X-User-Id"] = context.user.user_id
            if context.auth_token:
                headers["Authorization"] = f"Bearer {context.auth_token}"
        
        logger.info(f"AgentsClient headers: {list(headers.keys())}")
        return headers
    
    async def _call_flow(
        self, 
        flow_id: str, 
        message: str,
        timeout: float = DEFAULT_TIMEOUT
    ) -> Dict[str, Any]:
        """
        Вызывает flow синхронно с ожиданием результата.
        
        Args:
            flow_id: ID flow
            message: Текст сообщения
            timeout: Максимальное время ожидания
            
        Returns:
            Результат выполнения flow
            
        Raises:
            AgentsUnavailableError: Если сервис агентов недоступен или flow не найден
        """
        headers = self._get_headers()
        url = f"{self._base_url}/agents/api/v1/flows/{flow_id}/message"
        
        # Генерируем уникальный session_id для каждого запроса
        unique_session_id = f"crm:{flow_id}:{uuid.uuid4().hex[:12]}"
        
        payload = {
            "message": message,
            "role": "user",
            "user_id": headers.get("X-User-Id", "crm_service"),
            "session_id": unique_session_id,
            "wait_timeout": timeout,
        }
        
        try:
            async with get_httpx_client(timeout=timeout + 10, use_proxy_from_config=False) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                result = response.json()
        except Exception as e:
            logger.warning(f"Agents service unavailable for flow {flow_id}: {e}")
            raise AgentsUnavailableError(f"AI сервис недоступен: {e}")
        
        if result.get("status") != "completed":
            raise ValueError(f"Flow {flow_id} не завершился: {result}")
        
        return result.get("result", {})
    
    async def extract_entities(
        self,
        text: str,
        entity_types: Optional[List[Dict[str, Any]]] = None,
        generate_summary: bool = False,
        author_info: Optional[Dict[str, Any]] = None,
        note_context: Optional[Dict[str, Any]] = None,
        existing_entities: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Извлекает сущности из текста через Flow API.
        
        Args:
            text: Текст для анализа
            entity_types: Список типов с полями и промптами (опционально)
            generate_summary: Генерировать резюме текста
            author_info: Информация об авторе заметки (name, user_id)
            note_context: Контекст заметки (note_type, title, date)
            existing_entities: Список уже существующих сущностей (упомянутых через @)
            
        Returns:
            {
                "entities": [...],
                "relationships": [...],
                "summary": "..." (если generate_summary=True)
            }
        """
        message_parts = []
        
        # Контекст заметки
        if note_context:
            context_info = self._format_note_context(note_context, author_info, entity_types)
            message_parts.append(context_info)
        
        # Информация о существующих сущностях (упомянутых через @mention)
        if existing_entities:
            existing_info = self._format_existing_entities(existing_entities)
            message_parts.append(existing_info)
        
        # Основной текст
        message_parts.append(f"\n## Текст для анализа:\n{text}")
        
        # Инструкция по ai_description и relevance
        message_parts.append("""
ВАЖНО: Для КАЖДОЙ извлеченной сущности ОБЯЗАТЕЛЬНО заполни поля:

1. **ai_description** - контекст: откуда сущность появилась, на какой встрече/в каком документе упоминалась, 
из какой компании, какую роль играет.

2. **relevance** (число от 0.0 до 1.0) - насколько важна эта сущность в данном тексте:
   - 1.0 = главный объект обсуждения, центральная тема
   - 0.7-0.9 = активный участник, важная сущность
   - 0.4-0.6 = упомянут в контексте, косвенное отношение
   - 0.1-0.3 = второстепенное упоминание, мимоходом""")
        
        if generate_summary:
            message_parts.append("\n\nТакже создай краткое резюме текста.")
        
        if entity_types:
            types_info = self._format_entity_types_prompt(entity_types)
            message_parts.append(f"\n\n## Доступные типы сущностей:\n{types_info}")
            
            # Добавляем инструкции по связям
            relationships_info = self._format_relationships_prompt(entity_types)
            message_parts.append(f"\n\n## Связи между сущностями:\n{relationships_info}")
        
        message = "\n".join(message_parts)
        
        result = await self._call_flow("crm_entity_extractor", message)
        
        parsed = self._parse_extraction_result(result)
        entities_list = parsed.get('entities', [])
        logger.info(f"AI extraction result - entities: {len(entities_list)}, relationships: {len(parsed.get('relationships', []))}")
        if entities_list:
            first_entity = entities_list[0]
            logger.info(f"First entity keys: {list(first_entity.keys())}, relevance: {first_entity.get('relevance', 'NOT_SET')}")
        
        # Валидация: каждая сущность должна иметь хотя бы одну связь
        entities = parsed.get("entities", [])
        relationships = parsed.get("relationships", [])
        
        if entities and len(entities) > 1:
            orphan_entities = self._find_orphan_entities(entities, relationships)
            
            if orphan_entities:
                logger.warning(f"Found {len(orphan_entities)} entities without relationships: {orphan_entities}")
                # Перезапрос AI для добавления связей
                parsed = await self._request_missing_relationships(
                    parsed, orphan_entities, text, note_context
                )
        
        return parsed
    
    def _format_note_context(
        self,
        note_context: Dict[str, Any],
        author_info: Optional[Dict[str, Any]] = None,
        entity_types: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Форматирует контекст заметки для AI."""
        parts = ["## Контекст документа:"]
        
        note_type = note_context.get("note_type", "freeform")
        title = note_context.get("title", "")
        note_date = note_context.get("note_date", "")
        
        # Формируем лейблы динамически из event типов
        type_labels = {"freeform": "Заметка"}
        
        if entity_types:
            for et in entity_types:
                if et.get("is_event"):
                    type_id = et.get("type_id", "")
                    name = et.get("name", type_id)
                    # Маппинг note_type -> entity_type
                    if type_id == "meeting":
                        type_labels["meeting_minutes"] = f"Протокол встречи ({name})"
                    elif type_id == "call":
                        type_labels["call_log"] = f"Лог звонка ({name})"
                    elif type_id == "email":
                        type_labels["email"] = f"Письмо ({name})"
                    else:
                        # Кастомные event типы
                        type_labels[type_id] = name
        
        parts.append(f"- Тип: {type_labels.get(note_type, note_type)}")
        if title:
            parts.append(f"- Название: {title}")
        if note_date:
            parts.append(f"- Дата: {note_date}")
        
        # Определяем является ли заметка событием
        is_event_note = note_type in ["meeting_minutes", "call_log"] or any(
            et.get("type_id") == note_type and et.get("is_event")
            for et in (entity_types or [])
        )
        
        if author_info:
            author_name = author_info.get("name", "")
            if author_name:
                parts.append(f"- Автор/организатор: {author_name}")
                
                if is_event_note:
                    parts.append(f"\nАвтор '{author_name}' является организатором этого события.")
                    parts.append("Учти это при создании связей (organized_by).")
        
        return "\n".join(parts)
    
    def _format_existing_entities(self, existing_entities: List[Dict[str, Any]]) -> str:
        """Форматирует информацию о существующих сущностях для AI."""
        if not existing_entities:
            return ""
        
        parts = ["\n## Уже существующие сущности (упомянуты автором через @):"]
        parts.append("Эти сущности уже есть в системе. НЕ создавай их как новые!")
        parts.append("Используй их для создания связей (relationships) с другими сущностями.")
        parts.append("Рассчитай их relevance на основе контекста упоминания в тексте.\n")
        
        for entity in existing_entities:
            entity_id = entity.get("entity_id", "")
            name = entity.get("name", "")
            entity_type = entity.get("type", "")
            description = entity.get("description", "")
            
            parts.append(f"- **{name}** (ID: {entity_id}, тип: {entity_type})")
            if description:
                parts.append(f"  Описание: {description}")
        
        return "\n".join(parts)
    
    def _format_entity_types_prompt(self, entity_types: List[Dict[str, Any]]) -> str:
        """
        Форматирует промпт для типов сущностей с учетом полей.
        
        Разделяет на обычные типы и event типы.
        """
        regular_parts = []
        event_parts = []
        
        for entity_type in entity_types:
            type_id = entity_type.get("type_id", "unknown")
            name = entity_type.get("name", type_id)
            prompt = entity_type.get("prompt", entity_type.get("description", ""))
            is_event = entity_type.get("is_event", False)
            
            type_section = [f"### {type_id} ({name})"]
            if is_event:
                type_section.append("*Это тип события*")
            if prompt:
                type_section.append(prompt)
            
            required_fields = entity_type.get("required_fields", {})
            optional_fields = entity_type.get("optional_fields", {})
            
            if required_fields or optional_fields:
                type_section.append("Поля для извлечения:")
                
                for field_id, field_def in required_fields.items():
                    field_prompt = self._get_field_prompt(field_def)
                    label = field_def.get("label", field_id) if isinstance(field_def, dict) else field_id
                    type_section.append(f"- {field_id} (обязательное): {field_prompt}")
                
                for field_id, field_def in optional_fields.items():
                    field_prompt = self._get_field_prompt(field_def)
                    label = field_def.get("label", field_id) if isinstance(field_def, dict) else field_id
                    type_section.append(f"- {field_id}: {field_prompt}")
            
            section_text = "\n".join(type_section)
            if is_event:
                event_parts.append(section_text)
            else:
                regular_parts.append(section_text)
        
        result_parts = []
        if regular_parts:
            result_parts.append("**Обычные сущности:**\n" + "\n\n".join(regular_parts))
        if event_parts:
            result_parts.append("**События (meeting, call, email):**\n" + "\n\n".join(event_parts))
        
        return "\n\n".join(result_parts)
    
    def _format_relationships_prompt(self, entity_types: List[Dict[str, Any]]) -> str:
        """
        Форматирует инструкции по связям между сущностями.
        """
        # Проверяем есть ли event типы
        has_events = any(t.get("is_event", False) for t in entity_types)
        
        prompt = """Извлекай связи между сущностями. Формат связи:
```json
{
    "source": "Имя/название исходной сущности",
    "target": "Имя/название целевой сущности",
    "type": "тип_связи",
    "weight": 1.0,
    "attributes": {"context": "контекст связи из текста"}
}
```

**Типы связей между обычными сущностями:**
- `works_for` / `works_at`: человек работает в организации (weight: 1.0)
- `works_on`: человек работает над проектом (weight: 0.8-1.0)
- `knows`: люди знакомы друг с другом (weight: 0.5-1.0)
- `manages` / `owns`: управляет/владеет (weight: 1.0)
- `related_to`: общая связь (weight: 0.5)
- `assigned_to`: задача назначена человеку (weight: 1.0)"""

        if has_events:
            prompt += """

**Связи с событиями (meeting, call, email):**
- `participated_in`: человек участвовал в событии (weight: 1.0)
- `mentioned_in`: сущность упомянута в событии (weight: 0.5-0.8)
- `organized_by`: событие организовано человеком (weight: 1.0)

Если текст - это протокол встречи или лог звонка:
1. Извлеки всех упомянутых людей и организации
2. Определи связи между ними (works_for, knows)
3. Укажи weight в зависимости от контекста:
   - 1.0 - явно указано в тексте
   - 0.8 - подразумевается из контекста
   - 0.5 - предположение"""
        
        return prompt
    
    def _get_field_prompt(self, field_def: Any) -> str:
        """Извлекает промпт из определения поля"""
        if isinstance(field_def, dict):
            return field_def.get("prompt", "")
        return ""
    
    def _parse_extraction_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Парсит результат извлечения сущностей из ответа агента"""
        # Если результат уже в нужном формате
        if "entities" in result:
            return result
        
        # Ответ агента в поле response или message
        response_text = result.get("response") or result.get("message") or ""
        
        # Пробуем извлечь JSON из ответа
        json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Пробуем парсить весь ответ как JSON
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            pass
        
        # Возвращаем пустой результат
        logger.warning(f"Не удалось распарсить ответ агента: {response_text[:200]}")
        return {"entities": [], "relationships": [], "summary": response_text}
    
    def _find_orphan_entities(
        self,
        entities: List[Dict[str, Any]],
        relationships: List[Dict[str, Any]]
    ) -> List[str]:
        """Находит сущности без связей."""
        entity_names = {e.get("name", "").lower().strip() for e in entities}
        
        # Собираем имена сущностей участвующих в связях
        connected_names = set()
        for rel in relationships:
            source = rel.get("source", "").lower().strip()
            target = rel.get("target", "").lower().strip()
            connected_names.add(source)
            connected_names.add(target)
        
        # Находим сироты
        orphans = []
        for entity in entities:
            name = entity.get("name", "").lower().strip()
            if name and name not in connected_names:
                orphans.append(entity.get("name", ""))
        
        return orphans
    
    async def _request_missing_relationships(
        self,
        parsed: Dict[str, Any],
        orphan_entities: List[str],
        original_text: str,
        note_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Запрашивает у AI связи для сущностей-сирот."""
        entities = parsed.get("entities", [])
        existing_relationships = parsed.get("relationships", [])
        
        entity_names = [e.get("name") for e in entities if e.get("name")]
        
        message = f"""У тебя есть список извлеченных сущностей из текста:
{json.dumps(entity_names, ensure_ascii=False, indent=2)}

Некоторые сущности остались без связей: {orphan_entities}

Исходный текст:
{original_text[:2000]}

ЗАДАЧА: Добавь связи для КАЖДОЙ сущности из списка сирот. 
Каждая сущность ОБЯЗАТЕЛЬНО должна быть связана хотя бы с одной другой сущностью.

Верни ТОЛЬКО новые связи в формате JSON:
```json
{{
    "relationships": [
        {{
            "source": "Имя источника",
            "target": "Имя цели",
            "type": "тип_связи",
            "weight": 0.8,
            "attributes": {{"context": "почему эта связь существует"}}
        }}
    ]
}}
```

Типы связей: works_for, works_at, works_on, knows, manages, owns, related_to, participated_in, assigned_to"""

        result = await self._call_flow("crm_entity_extractor", message, timeout=60.0)
        new_parsed = self._parse_extraction_result(result)
        
        new_relationships = new_parsed.get("relationships", [])
        logger.info(f"Got {len(new_relationships)} additional relationships for orphans")
        
        # Объединяем связи
        parsed["relationships"] = existing_relationships + new_relationships
        
        return parsed
    
    async def compare_entities(
        self,
        entity_1: Dict[str, Any],
        entity_2: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Сравнивает две сущности для определения дубликатов.
        """
        message = f"""Сравни две сущности и определи, являются ли они дубликатами:

Сущность 1:
{json.dumps(entity_1, ensure_ascii=False, indent=2)}

Сущность 2:
{json.dumps(entity_2, ensure_ascii=False, indent=2)}

Ответь в формате JSON:
```json
{{
    "is_duplicate": true/false,
    "confidence": 0.0-1.0,
    "reason": "объяснение"
}}
```"""
        
        result = await self._call_flow("crm_entity_comparison", message, timeout=30.0)
        return self._parse_comparison_result(result)
    
    def _parse_comparison_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Парсит результат сравнения сущностей"""
        if "is_duplicate" in result:
            return result
        
        response_text = result.get("response") or result.get("message") or ""
        
        json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        return {"is_duplicate": False, "confidence": 0.0, "reason": "Не удалось определить"}
    
    async def health_check(self) -> bool:
        """Проверяет доступность сервиса агентов"""
        url = f"{self._base_url}/agents/health"
        
        async with get_httpx_client(timeout=5.0, use_proxy_from_config=False) as client:
            response = await client.get(url)
            response.raise_for_status()
            return True
