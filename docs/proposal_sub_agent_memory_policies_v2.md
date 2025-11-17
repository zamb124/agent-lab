# Предложение: Политики памяти для субагентов (v2)

## Архитектурный принцип

**Агент не знает, что он субагент** - он просто обращается к `StateManager` со своим `session_id` и получает память. Вся логика политик управления памятью находится в `StateManager`.

## Решение

### 1. Enum политик памяти

**Файл:** `app/models/core_models.py`

```python
class SubAgentMemoryPolicy(str, Enum):
    """Политики управления памятью для субагентов"""
    ISOLATED = "isolated"      # По умолчанию: каждый вызов - новая сессия
    ACCUMULATED = "accumulated" # Накапливает память между вызовами
    SNAPSHOT = "snapshot"       # Копирует память родителя при вызове
    SHARED = "shared"           # Работает в одной памяти с родителем
```

### 2. Методы в StateManager

**Файл:** `app/core/state_manager.py`

Добавить методы для работы с политиками памяти:

```python
class StateManager:
    # ... существующие методы ...
    
    def _detect_memory_policy(self, session_id: str) -> Optional[SubAgentMemoryPolicy]:
        """
        Определяет политику памяти из формата session_id.
        
        Форматы:
        - parent:sub:agent:accumulated -> ACCUMULATED
        - parent:sub:agent:snapshot:uuid -> SNAPSHOT
        - parent (SHARED использует session_id родителя напрямую)
        - parent:sub:agent:uuid -> ISOLATED (по умолчанию)
        """
        if not session_id or ":sub:" not in session_id:
            return None
        
        parts = session_id.split(":")
        if len(parts) >= 4:
            policy_part = parts[3]
            if policy_part == "accumulated":
                return SubAgentMemoryPolicy.ACCUMULATED
            elif policy_part == "snapshot":
                return SubAgentMemoryPolicy.SNAPSHOT
        
        return SubAgentMemoryPolicy.ISOLATED
    
    async def get_sub_session_id(
        self,
        parent_session_id: str,
        sub_agent_id: str,
        policy: SubAgentMemoryPolicy
    ) -> str:
        """
        Определяет sub_session_id на основе политики.
        
        Args:
            parent_session_id: ID сессии родителя
            sub_agent_id: ID субагента
            policy: Политика памяти
            
        Returns:
            sub_session_id для субагента
        """
        import uuid
        
        if policy == SubAgentMemoryPolicy.SHARED:
            return parent_session_id
        
        if policy == SubAgentMemoryPolicy.ACCUMULATED:
            # Фиксированный ID для накопления памяти
            return f"{parent_session_id}:sub:{sub_agent_id}:accumulated"
        
        if policy == SubAgentMemoryPolicy.SNAPSHOT:
            # Новый ID для каждого вызова, но с маркером snapshot
            unique_id = uuid.uuid4().hex[:8]
            return f"{parent_session_id}:sub:{sub_agent_id}:snapshot:{unique_id}"
        
        # ISOLATED - по умолчанию
        unique_id = uuid.uuid4().hex[:8]
        return f"{parent_session_id}:sub:{sub_agent_id}:{unique_id}"
    
    async def load_state_for_sub_agent(
        self,
        sub_session_id: str,
        parent_state: Optional[State] = None
    ) -> Optional[State]:
        """
        Загружает состояние для субагента с учетом политики памяти.
        
        Агент не знает, что он субагент - он просто вызывает этот метод
        или обычный load_state(), который внутри вызовет этот метод при необходимости.
        
        Args:
            sub_session_id: ID сессии субагента
            parent_state: Состояние родителя (опционально, для SNAPSHOT и SHARED)
            
        Returns:
            Состояние для субагента или None
        """
        policy = self._detect_memory_policy(sub_session_id)
        
        if policy == SubAgentMemoryPolicy.SHARED:
            # Используем состояние родителя напрямую
            if parent_state:
                return parent_state.copy()
            # Или загружаем общее состояние
            return await self.load_state(sub_session_id)
        
        if policy == SubAgentMemoryPolicy.ACCUMULATED:
            # Загружаем накопленное состояние
            saved_state = await self.load_state(sub_session_id)
            if saved_state and parent_state:
                # Наследуем базовые поля от родителя
                saved_state["task_id"] = parent_state.get("task_id", "")
                saved_state["user_id"] = parent_state.get("user_id", "")
            return saved_state
        
        if policy == SubAgentMemoryPolicy.SNAPSHOT:
            # Для SNAPSHOT загружаем или создаем новое, но копируем store от родителя
            saved_state = await self.load_state(sub_session_id)
            if not saved_state and parent_state:
                # Создаем новое состояние с копией store родителя
                saved_state = {
                    "messages": [],
                    "store": parent_state.get("store", {}).copy(),
                    "task_id": parent_state.get("task_id", ""),
                    "session_id": sub_session_id,
                    "user_id": parent_state.get("user_id", ""),
                    "remaining_steps": parent_state.get("remaining_steps", 25),
                }
            elif saved_state and parent_state:
                # Если состояние уже есть, обновляем store из родителя при создании
                # Но только если это первая загрузка (messages пусты)
                if not saved_state.get("messages"):
                    saved_state["store"] = parent_state.get("store", {}).copy()
            return saved_state
        
        # ISOLATED - обычная загрузка или новое состояние
        saved_state = await self.load_state(sub_session_id)
        return saved_state
    
    async def save_state_for_sub_agent(
        self,
        sub_session_id: str,
        sub_state: State,
        parent_state: Optional[State] = None,
        policy: Optional[SubAgentMemoryPolicy] = None
    ) -> None:
        """
        Сохраняет состояние субагента с учетом политики памяти.
        
        Args:
            sub_session_id: ID сессии субагента
            sub_state: Состояние субагента
            parent_state: Состояние родителя (для SHARED)
            policy: Политика памяти (если не указана, определяется из session_id)
        """
        if policy is None:
            policy = self._detect_memory_policy(sub_session_id)
        
        if policy == SubAgentMemoryPolicy.SHARED:
            # Обновляем общее состояние
            if parent_state:
                # Обновляем store родителя из субагента
                parent_state["store"].update(sub_state.get("store", {}))
                await self.save_state(parent_state["session_id"], parent_state)
            else:
                # Сохраняем состояние напрямую
                await self.save_state(sub_session_id, sub_state)
        elif policy == SubAgentMemoryPolicy.ACCUMULATED:
            # Сохраняем накопленное состояние
            await self.save_state(sub_session_id, sub_state)
        # Для ISOLATED и SNAPSHOT состояние не сохраняется (только для interrupt)
```

### 3. Обновление BaseAgent.as_tool

**Файл:** `app/agents/base.py`

Упростить `as_tool` - вся логика в `StateManager`:

```python
def as_tool(self, name: Optional[str] = None, description: Optional[str] = None, memory_policy: Optional[SubAgentMemoryPolicy] = None):
    """
    Превращает агента в инструмент.
    
    Args:
        name: Имя инструмента
        description: Описание инструмента
        memory_policy: Политика памяти (по умолчанию ISOLATED)
    """
    # ... существующий код ...
    
    async def agent_func(request: str, tool_call_id: Optional[str] = None) -> str:
        """Функция-обертка для вызова агента как инструмента"""
        from app.models.core_models import SubAgentMemoryPolicy
        
        parent_state = get_state()
        state_manager = await get_state_manager()
        parent_session_id = parent_state.get("session_id") if parent_state else None
        
        # Определяем политику (из параметра или ToolReference)
        policy = memory_policy or SubAgentMemoryPolicy.ISOLATED
        
        # StateManager определяет sub_session_id на основе политики
        sub_session_id = await state_manager.get_sub_session_id(
            parent_session_id=parent_session_id,
            sub_agent_id=self.config.agent_id,
            policy=policy
        )
        
        # StateManager загружает состояние для субагента с учетом политики
        sub_state = await state_manager.load_state_for_sub_agent(
            sub_session_id=sub_session_id,
            parent_state=parent_state
        )
        
        # Если состояние не найдено, создаем новое
        if not sub_state:
            sub_state = {
                "messages": [],
                "store": {},
                "task_id": parent_state.get("task_id", "") if parent_state else "",
                "session_id": sub_session_id,
                "user_id": parent_state.get("user_id", "") if parent_state else "",
                "remaining_steps": 25,
            }
            
            # Для SNAPSHOT копируем store от родителя
            if policy == SubAgentMemoryPolicy.SNAPSHOT and parent_state:
                sub_state["store"] = parent_state.get("store", {}).copy()
        
        # Добавляем сообщение пользователя
        from langchain_core.messages import HumanMessage
        sub_state["messages"].append(HumanMessage(content=input_text))
        
        try:
            # Вызываем агента - он не знает, что он субагент
            result = await self.ainvoke(
                sub_state,
                config={"configurable": {"thread_id": sub_session_id}}
            )
            
            # Сохраняем состояние с учетом политики (только если нужно)
            if policy in (SubAgentMemoryPolicy.SHARED, SubAgentMemoryPolicy.ACCUMULATED):
                await state_manager.save_state_for_sub_agent(
                    sub_session_id=sub_session_id,
                    sub_state=result if isinstance(result, dict) else sub_state,
                    parent_state=parent_state,
                    policy=policy
                )
            
            # Возвращаем только результат
            if result and result.get("messages"):
                return getattr(result["messages"][-1], "content", "")
            return "Агент выполнен успешно, но не вернул контент."
            
        except AgentInterrupt as sub_interrupt:
            # Стандартная обработка interrupt - сохраняем состояние независимо от политики
            sub_state["interrupt_context"] = {
                "type": "sub_agent",
                "agent_id": self.config.agent_id,
                "tool_name": tool_name,
                "interrupt_message": sub_interrupt.value
            }
            await state_manager.save_state(sub_session_id, sub_state)
            
            # Обновляем родителя
            if parent_state and parent_state.get("session_id"):
                parent_saved = await state_manager.load_state(parent_state["session_id"])
                if not parent_saved:
                    parent_saved = parent_state
                parent_saved["interrupt_context"] = {
                    "type": "tool_call",
                    "tool_name": tool_name,
                    "sub_agent_id": self.config.agent_id,
                    "sub_session_id": sub_session_id,
                    "tool_call_id": tool_call_id or "",
                    "interrupt_message": sub_interrupt.value
                }
                await state_manager.save_state(parent_state["session_id"], parent_saved)
                set_state_in_context(parent_saved)
            
            raise AgentInterrupt(sub_interrupt.value)
```

### 4. Умный load_state

**Файл:** `app/core/state_manager.py`

Можно расширить обычный `load_state`, чтобы он автоматически использовал `load_state_for_sub_agent` для sub-сессий:

```python
async def load_state(self, session_id: str, parent_state: Optional[State] = None) -> Optional[State]:
    """
    Загружает состояние для сессии.
    
    Для sub-сессий автоматически применяется логика политик памяти.
    
    Args:
        session_id: ID сессии
        parent_state: Состояние родителя (опционально, для sub-сессий)
    """
    # Если это sub-сессия и есть parent_state, используем специальную логику
    if ":sub:" in session_id and parent_state:
        return await self.load_state_for_sub_agent(session_id, parent_state)
    
    # Обычная загрузка
    # ... существующий код ...
```

## Преимущества

1. **Агент не знает про политики** - просто вызывает `StateManager.load_state(session_id)` и получает нужное состояние
2. **Вся логика в StateManager** - единое место управления памятью
3. **Политика определяется из session_id** - формат `session_id` сам указывает на политику
4. **Чистая архитектура** - нет отдельных классов для субагентов

## Порядок реализации

1. Добавить `SubAgentMemoryPolicy` enum в `core_models.py`
2. Добавить методы в `StateManager`:
   - `_detect_memory_policy()`
   - `get_sub_session_id()`
   - `load_state_for_sub_agent()`
   - `save_state_for_sub_agent()`
3. Модифицировать `BaseAgent.as_tool` для использования новых методов
4. Добавить поле `memory_policy` в `ToolReference` (опционально)
5. Написать тесты для каждой политики

