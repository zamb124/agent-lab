"""
Менеджер состояния для агентов.
Простой и прозрачный PostgreSQL чекпоинтер без зависимости от LangGraph.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from app.core.config import get_settings
from app.core.state import State
from app.core.tracing.decorators import trace_span
from app.models.trace_models import SpanType
from app.db.database import get_engine
from app.db.models import Stores, AgentStates
from app.models.core_models import SubAgentMemoryPolicy

logger = logging.getLogger(__name__)



def _messages_to_dicts(messages: List[BaseMessage]) -> List[Dict[str, Any]]:
    """Конвертирует сообщения в словари для сериализации"""
    result = []
    for msg in messages:
        msg_dict = {
            "type": msg.__class__.__name__,
            "content": msg.content,
            "additional_kwargs": dict(msg.additional_kwargs) if msg.additional_kwargs else {},
            "response_metadata": dict(msg.response_metadata) if msg.response_metadata else {},
        }
        if hasattr(msg, "id") and msg.id:
            msg_dict["id"] = str(msg.id)
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            tool_calls_list = []
            for tc in msg.tool_calls:
                if isinstance(tc, dict):
                    # Санитизируем args - конвертируем несериализуемые объекты в строки
                    sanitized_tc = tc.copy()
                    if "args" in sanitized_tc:
                        args = sanitized_tc["args"]
                        if isinstance(args, dict):
                            sanitized_args = {}
                            for key, value in args.items():
                                if isinstance(value, (str, int, float, bool, type(None))):
                                    sanitized_args[key] = value
                                elif isinstance(value, BaseMessage):
                                    sanitized_args[key] = str(value)
                                else:
                                    sanitized_args[key] = str(value)
                            sanitized_tc["args"] = sanitized_args
                    tool_calls_list.append(sanitized_tc)
                else:
                    # Извлекаем args и санитизируем
                    args = getattr(tc, "args", {})
                    if isinstance(args, dict):
                        sanitized_args = {}
                        for key, value in args.items():
                            if isinstance(value, (str, int, float, bool, type(None))):
                                sanitized_args[key] = value
                            elif isinstance(value, BaseMessage):
                                sanitized_args[key] = str(value)
                            else:
                                sanitized_args[key] = str(value)
                    else:
                        sanitized_args = str(args) if args else {}
                    
                    tc_dict = {
                        "name": getattr(tc, "name", ""),
                        "args": sanitized_args,
                        "id": str(getattr(tc, "id", "")),
                    }
                    tool_calls_list.append(tc_dict)
            msg_dict["tool_calls"] = tool_calls_list
        if hasattr(msg, "tool_call_id") and msg.tool_call_id:
            msg_dict["tool_call_id"] = str(msg.tool_call_id)
        if hasattr(msg, "name") and msg.name:
            msg_dict["name"] = str(msg.name)
        result.append(msg_dict)
    return result


def _dicts_to_messages(msg_dicts: List[Dict[str, Any]]) -> List[BaseMessage]:
    """Конвертирует словари обратно в сообщения"""
    result = []
    for msg_dict in msg_dicts:
        msg_type = msg_dict.get("type", "HumanMessage")
        content = msg_dict.get("content", "")
        additional_kwargs = msg_dict.get("additional_kwargs", {})
        response_metadata = msg_dict.get("response_metadata", {})
        
        if msg_type == "HumanMessage":
            msg = HumanMessage(content=content, additional_kwargs=additional_kwargs, response_metadata=response_metadata)
        elif msg_type == "AIMessage":
            msg = AIMessage(content=content, additional_kwargs=additional_kwargs, response_metadata=response_metadata)
            if "tool_calls" in msg_dict:
                msg.tool_calls = msg_dict["tool_calls"]
        elif msg_type == "SystemMessage":
            msg = SystemMessage(content=content, additional_kwargs=additional_kwargs, response_metadata=response_metadata)
        elif msg_type == "ToolMessage":
            tool_call_id = msg_dict.get("tool_call_id", "")
            name = msg_dict.get("name", "")
            msg = ToolMessage(content=content, tool_call_id=tool_call_id, name=name, additional_kwargs=additional_kwargs, response_metadata=response_metadata)
        else:
            msg = HumanMessage(content=content, additional_kwargs=additional_kwargs, response_metadata=response_metadata)
        
        if "id" in msg_dict and hasattr(msg, "id"):
            msg.id = msg_dict["id"]
        
        result.append(msg)
    return result


class StateManager:
    """
    Простой и прозрачный менеджер состояния для агентов.
    Интегрирован с database.py - использует общий engine и создание таблиц через create_tables().
    """

    def __init__(self):
        pass

    @trace_span(
        name="state_manager.load_state",
        span_type=SpanType.OTHER,
        metadata={"component": "state_manager", "operation": "load"}
    )
    async def load_state(self, session_id: str, parent_state: Optional[State] = None) -> Optional[State]:
        """
        Загружает состояние для сессии.
        
        Для sub-сессий автоматически определяет политику памяти из формата session_id
        и применяет соответствующую логику.

        Args:
            session_id: ID сессии
            parent_state: Состояние родителя (опционально, для sub-сессий с политиками)

        Returns:
            Состояние агента или None, если состояние не найдено
        """
        if not session_id:
            logger.debug("session_id пустой, возвращаем None")
            return None

        # Если это sub-сессия, используем специальную логику политик
        if ":sub:" in session_id:
            # Получаем parent_state из контекста (если установлен) или из parent_session_id
            if not parent_state:
                from app.core.variables import get_state
                context_state = get_state()
                # Если context_state - это parent_state (не sub-сессия), используем его
                if context_state and context_state.get("session_id") and ":sub:" not in context_state.get("session_id", ""):
                    parent_state = context_state
                else:
                    # Иначе загружаем из БД
                    parent_session_id = self._extract_parent_session_id(session_id)
                    if parent_session_id:
                        # Используем _load_state_direct чтобы избежать рекурсии
                        parent_state = await self._load_state_direct(parent_session_id)
            
            if parent_state:
                return await self.load_state_for_sub_agent(session_id, parent_state)

        # Обычная загрузка для обычных сессий
        state = await self._load_state_direct(session_id)
        if state:
            logger.debug(f"Состояние загружено для session_id={session_id}: {len(state.get('messages', []))} сообщений")
        return state

    @trace_span(
        name="state_manager.save_state",
        span_type=SpanType.OTHER,
        metadata={"component": "state_manager", "operation": "save"}
    )
    async def save_state(self, session_id: str, state: State) -> None:
        """
        Сохраняет состояние для сессии и синхронизирует store в контексте.
        
        ЕДИНОЕ МЕСТО СОХРАНЕНИЯ STORE:
        1. Получает store из state (который должен быть из контекста)
        2. Сохраняет store в БД по store_id (для sub-сессий наследуется от родителя)
        3. После сохранения автоматически обновляет parent_state["store"] в контексте для sub-сессий
        """
        if not session_id:
            logger.warning("session_id пустой, состояние не сохранено")
            return
        
        # Получаем store из контекста (обновлен через session_set)
        # Только если контекст соответствует текущей сессии
        from app.core.variables import get_state
        context_state = get_state()
        if context_state and "store" in context_state:
            context_session_id = context_state.get("session_id")
            # Используем store из контекста только если это та же сессия или контекст для sub-сессии
            if context_session_id == session_id or (":sub:" in session_id and context_session_id and ":sub:" not in context_session_id):
                state["store"] = context_state["store"]
        
        # Сохраняем в БД
        await self._save_state_direct(session_id, state)
        
        # Для sub-сессий синхронизируем store родителя в контексте
        if ":sub:" in session_id:
            await self._sync_parent_store_to_context(session_id)

    async def _save_state_direct(self, session_id: str, state: State) -> None:
        """
        Прямое сохранение состояния в БД (внутренний метод).
        Сохраняет store отдельно в Stores и state_data в AgentStates с store_id.
        Для sub-сессий наследует store_id от родителя.
        """
        engine = await get_engine()

        # Определяем store_id: для sub-сессий наследуем от родителя, для родительских - используем session_id
        store_id = state.get("store_id")
        if not store_id:
            if ":sub:" in session_id:
                # Для sub-сессий извлекаем store_id из родителя
                parent_session_id = self._extract_parent_session_id(session_id)
                if parent_session_id:
                    parent_state = await self._load_state_direct(parent_session_id)
                    if parent_state:
                        store_id = parent_state.get("store_id", parent_session_id)
                    else:
                        store_id = parent_session_id
                else:
                    store_id = session_id
            else:
                # Для родительских сессий используем session_id как store_id
                store_id = session_id
        
        # Сохраняем store отдельно в Stores (единый для всего flow)
        store_data = state.get("store", {})
        store_data_json = json.dumps(store_data, default=str)
        
        messages = state.get("messages", [])
        if messages:
            # Фильтруем только объекты сообщений (не строки)
            valid_messages = [msg for msg in messages if not isinstance(msg, str) and hasattr(msg, "content")]
            if valid_messages:
                messages_data = _messages_to_dicts(valid_messages)
            else:
                messages_data = []
        else:
            messages_data = []
        
        state_data = {
            "messages": messages_data,
            "task_id": state.get("task_id", ""),
            "session_id": state.get("session_id", session_id),
            "user_id": state.get("user_id", ""),
            "remaining_steps": state.get("remaining_steps", 25),
        }
        
        if "interrupt_context" in state:
            state_data["interrupt_context"] = state["interrupt_context"]

        state_data_json = json.dumps(state_data, default=str)
        
        async with engine.begin() as conn:
            # Сохраняем store в Stores (единый для всего flow)
            await conn.execute(
                text("""
                    INSERT INTO stores (store_id, store_data, updated_at)
                    VALUES (:store_id, CAST(:store_data AS JSONB), CURRENT_TIMESTAMP)
                    ON CONFLICT (store_id)
                    DO UPDATE SET
                        store_data = CAST(:store_data AS JSONB),
                        updated_at = CURRENT_TIMESTAMP
                """),
                {
                    "store_id": store_id,
                    "store_data": store_data_json
                }
            )
            
            # Сохраняем state_data в AgentStates с store_id
            await conn.execute(
                text("""
                    INSERT INTO agent_states (session_id, store_id, state_data, updated_at)
                    VALUES (:session_id, :store_id, CAST(:state_data AS JSONB), CURRENT_TIMESTAMP)
                    ON CONFLICT (session_id)
                    DO UPDATE SET
                        store_id = :store_id,
                        state_data = CAST(:state_data AS JSONB),
                        updated_at = CURRENT_TIMESTAMP
                """),
                {
                    "session_id": session_id,
                    "store_id": store_id,
                    "state_data": state_data_json
                }
            )

        logger.debug(f"Состояние сохранено для session_id={session_id}, store_id={store_id}: {len(state.get('messages', []))} сообщений")

    async def delete_state(self, session_id: str) -> None:
        """
        Удаляет состояние для сессии.

        Args:
            session_id: ID сессии
        """
        if not session_id:
            return

        engine = await get_engine()
        async with engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM agent_states WHERE session_id = :session_id"),
                {"session_id": session_id}
            )
        logger.debug(f"Состояние удалено для session_id={session_id}")

    def _extract_parent_session_id(self, session_id: str) -> Optional[str]:
        """
        Извлекает parent_session_id из sub_session_id.
        
        Форматы:
        - parent:sub:agent:accumulated -> parent
        - parent:sub:agent:snapshot:uuid -> parent
        - parent:sub:agent:uuid -> parent
        
        Args:
            session_id: ID sub-сессии
            
        Returns:
            parent_session_id или None
        """
        if not session_id or ":sub:" not in session_id:
            return None
        
        # Находим позицию :sub: и берем все что до него
        sub_pos = session_id.find(":sub:")
        if sub_pos > 0:
            return session_id[:sub_pos]
        
        return None
    
    def _detect_memory_policy(self, session_id: str) -> Optional[SubAgentMemoryPolicy]:
        """
        Определяет политику памяти из формата session_id.
        
        Форматы:
        - parent:sub:agent:accumulated -> ACCUMULATED
        - parent:sub:agent:snapshot:uuid -> SNAPSHOT
        - parent (SHARED использует session_id родителя напрямую)
        - parent:sub:agent:uuid -> ISOLATED (по умолчанию)
        
        Args:
            session_id: ID сессии
            
        Returns:
            Политика памяти или None если это не sub-сессия
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
        
        ВСЕ sub_session_id наследуют parent_session_id для отслеживания ветвлений.
        
        Args:
            parent_session_id: ID сессии родителя (ОБЯЗАТЕЛЬНО, не может быть пустым)
            sub_agent_id: ID субагента
            policy: Политика памяти
            
        Returns:
            sub_session_id для субагента (всегда начинается с parent_session_id:)
        """
        import uuid
        
        if not parent_session_id:
            raise ValueError("parent_session_id не может быть пустым для создания sub_session_id")
        
        if policy == SubAgentMemoryPolicy.SHARED:
            # Используем session_id родителя напрямую
            return parent_session_id
        
        if policy == SubAgentMemoryPolicy.ACCUMULATED:
            # Фиксированный ID для накопления памяти (наследуется от родителя)
            return f"{parent_session_id}:sub:{sub_agent_id}:accumulated"
        
        if policy == SubAgentMemoryPolicy.SNAPSHOT:
            # Новый ID для каждого вызова, но с маркером snapshot (наследуется от родителя)
            unique_id = uuid.uuid4().hex[:8]
            return f"{parent_session_id}:sub:{sub_agent_id}:snapshot:{unique_id}"
        
        # ISOLATED - по умолчанию (наследуется от родителя)
        unique_id = uuid.uuid4().hex[:8]
        return f"{parent_session_id}:sub:{sub_agent_id}:{unique_id}"
    
    async def load_state_for_sub_agent(
        self,
        sub_session_id: str,
        parent_state: Optional[State] = None
    ) -> Optional[State]:
        """
        Загружает состояние для субагента с учетом политики памяти.
        
        ВАЖНО: store всегда берется из родительской сессии (единый для всего flow).
        Различаются только messages в зависимости от политики памяти.
        
        Args:
            sub_session_id: ID сессии субагента (всегда наследует parent_session_id)
            parent_state: Состояние родителя (обязательно для получения store)
            
        Returns:
            Состояние для субагента или None
        """
        if not parent_state:
            parent_session_id = self._extract_parent_session_id(sub_session_id)
            if parent_session_id:
                parent_state = await self._load_state_direct(parent_session_id)
        
        if not parent_state:
            logger.warning(f"Не удалось загрузить parent_state для {sub_session_id}")
            return None
        
        parent_store_id = parent_state.get("store_id", parent_state.get("session_id"))
        
        # Используем store из parent_state напрямую как ссылку (единый для всего flow)
        # Это гарантирует, что изменения субагента в памяти будут видны родителю
        store_data = parent_state["store"]
        
        policy = self._detect_memory_policy(sub_session_id)
        
        if policy == SubAgentMemoryPolicy.SHARED:
            result = parent_state.copy()
            result["session_id"] = sub_session_id
            return result
        
        if policy == SubAgentMemoryPolicy.ACCUMULATED:
            saved_state = await self._load_state_direct(sub_session_id)
            if not saved_state:
                saved_state = {
                    "messages": [],
                    "store": store_data,
                    "store_id": parent_store_id,
                    "task_id": parent_state.get("task_id", ""),
                    "session_id": sub_session_id,
                    "user_id": parent_state.get("user_id", ""),
                    "remaining_steps": parent_state.get("remaining_steps", 25),
                }
            else:
                saved_state["store"] = store_data
                saved_state["store_id"] = parent_store_id
            return saved_state
        
        if policy == SubAgentMemoryPolicy.SNAPSHOT:
            saved_state = await self._load_state_direct(sub_session_id)
            if not saved_state:
                saved_state = {
                    "messages": [],
                    "store": store_data,
                    "store_id": parent_store_id,
                    "task_id": parent_state.get("task_id", ""),
                    "session_id": sub_session_id,
                    "user_id": parent_state.get("user_id", ""),
                    "remaining_steps": parent_state.get("remaining_steps", 25),
                }
            else:
                saved_state["store"] = store_data
                saved_state["store_id"] = parent_store_id
            return saved_state
        
        # ISOLATED - новый messages для каждого вызова, но store единый через ссылку
        saved_state = await self._load_state_direct(sub_session_id)
        if not saved_state:
            saved_state = {
                "messages": [],
                "store": store_data,
                "store_id": parent_store_id,
                "task_id": parent_state.get("task_id", ""),
                "session_id": sub_session_id,
                "user_id": parent_state.get("user_id", ""),
                "remaining_steps": parent_state.get("remaining_steps", 25),
            }
        else:
            saved_state["store"] = store_data
            saved_state["store_id"] = parent_store_id
        return saved_state
    
    async def _load_state_direct(self, session_id: str) -> Optional[State]:
        """
        Прямая загрузка состояния из БД без проверки политик (внутренний метод).
        Загружает state_data из AgentStates и store из Stores по store_id.
        """
        if not session_id:
            return None

        engine = await get_engine()

        async with engine.begin() as conn:
            result = await conn.execute(
                text("""
                    SELECT a.state_data, a.store_id, s.store_data
                    FROM agent_states a
                    LEFT JOIN stores s ON a.store_id = s.store_id
                    WHERE a.session_id = :session_id
                """),
                {"session_id": session_id}
            )
            row = result.first()

        if not row:
            return None

        state_data, store_id, store_data = row[0], row[1], row[2]
        
        messages_data = state_data.get("messages", [])
        if messages_data and len(messages_data) > 0 and isinstance(messages_data[0], dict):
            messages = _dicts_to_messages(messages_data)
        else:
            messages = messages_data

        state = {
            "messages": messages,
            "store": store_data if store_data else {},
            "task_id": state_data.get("task_id", ""),
            "session_id": state_data.get("session_id", session_id),
            "user_id": state_data.get("user_id", ""),
            "remaining_steps": state_data.get("remaining_steps", 25),
            "store_id": store_id,
        }
        
        if "interrupt_context" in state_data:
            state["interrupt_context"] = state_data["interrupt_context"]

        return state
    
    async def load_store(self, store_id: str) -> Dict[str, Any]:
        """
        Загружает store по store_id из Stores.
        
        Args:
            store_id: ID store
            
        Returns:
            store или пустой словарь
        """
        if not store_id:
            return {}
        
        engine = await get_engine()
        async with engine.begin() as conn:
            result = await conn.execute(
                text("SELECT store_data FROM stores WHERE store_id = :store_id"),
                {"store_id": store_id}
            )
            row = result.first()
        
        if not row:
            return {}
        
        return row[0] if row[0] else {}
    
    async def _sync_parent_store_to_context(self, sub_session_id: str) -> None:
        """
        ЕДИНОЕ МЕСТО ОБНОВЛЕНИЯ STORE В КОНТЕКСТЕ.
        
        После сохранения sub-агента обновляет parent_state["store"] в контексте
        актуальным значением из БД.
        
        Args:
            sub_session_id: ID sub-сессии
        """
        from app.core.variables import get_state, set_state_in_context
        
        # Получаем parent_session_id
        parent_session_id = self._extract_parent_session_id(sub_session_id)
        if not parent_session_id:
            return
        
        # Загружаем parent_state из контекста
        context_state = get_state()
        if not context_state:
            return
        
        # Если контекст - это parent_state (не sub-сессия), обновляем store из БД
        if context_state.get("session_id") == parent_session_id:
            parent_store_id = context_state.get("store_id", parent_session_id)
            if parent_store_id:
                updated_store = await self.load_store(parent_store_id)
                context_state["store"] = updated_store
                context_state["store_id"] = parent_store_id
                set_state_in_context(context_state)
                logger.debug(f"✅ Parent store обновлен в контексте для store_id={parent_store_id}")
    
    async def save_state_for_sub_agent(
        self,
        sub_session_id: str,
        sub_state: State,
        parent_state: Optional[State] = None,
        policy: Optional[SubAgentMemoryPolicy] = None
    ) -> None:
        """
        Сохраняет состояние субагента с учетом политики памяти.
        
        ВАЖНО: store всегда обновляется в родительской сессии (единый для всего flow).
        Sub-сессии сохраняют только messages.
        
        Args:
            sub_session_id: ID сессии субагента (всегда наследует parent_session_id)
            sub_state: Состояние субагента
            parent_state: Состояние родителя (обязательно для обновления store)
            policy: Политика памяти (если не указана, определяется из session_id)
        """
        if policy is None:
            policy = self._detect_memory_policy(sub_session_id)
        
        # Получаем parent_state из контекста (если установлен) или из parent_session_id
        if not parent_state:
            from app.core.variables import get_state
            context_state = get_state()
            if context_state and context_state.get("session_id") and ":sub:" not in context_state.get("session_id", ""):
                parent_state = context_state
            else:
                parent_session_id = self._extract_parent_session_id(sub_session_id)
                if parent_session_id:
                    parent_state = await self._load_state_direct(parent_session_id)
        
        # store всегда единый для всего flow - обновляем в родительской сессии если есть изменения
        if parent_state:
            # store из sub_state уже обновлен через get_state() в session_set
            # Просто сохраняем актуальное состояние родителя
            await self._save_state_direct(parent_state["session_id"], parent_state)
        
        if policy == SubAgentMemoryPolicy.SHARED:
            # Для SHARED сохраняем общее состояние (store уже обновлен в родителе)
            if parent_state:
                await self._save_state_direct(parent_state["session_id"], parent_state)
        elif policy == SubAgentMemoryPolicy.ACCUMULATED:
            # Сохраняем накопленные messages (store уже обновлен в родителе)
            await self._save_state_direct(sub_session_id, sub_state)
        # Для ISOLATED и SNAPSHOT состояние не сохраняется (только для interrupt)

    async def close(self):
        """
        Закрывает соединение.
        В новой архитектуре engine управляется database.py, поэтому ничего не делаем.
        """
        pass


# Глобальный экземпляр
_state_manager = None


async def get_state_manager() -> StateManager:
    """Получает глобальный экземпляр StateManager"""
    global _state_manager
    
    if _state_manager is None:
        _state_manager = StateManager()
        logger.info("StateManager успешно инициализирован")
    
    return _state_manager
