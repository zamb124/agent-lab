"""
Менеджер состояния для агентов.
Единообразная рекурсивная архитектура без ветвлений и фолбеков.
"""

import logging
import uuid
from typing import Any, Dict, Optional, List
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from apps.agents.services.state import State
from apps.agents.models.core_models import SubAgentMemoryPolicy
from apps.agents.container import get_agents_container

logger = logging.getLogger(__name__)


class StoreProxy(dict):
    """
    Прокси для store, который автоматически работает с БД.
    ЛЮБОЕ обращение к store - это обращение к БД.
    """
    
    def __init__(self, store_id: str, initial_data: Optional[Dict[str, Any]] = None):
        super().__init__(initial_data or {})
        self.store_id = store_id
        self._dirty = False
    
    def __getitem__(self, key: str) -> Any:
        return super().__getitem__(key)
    
    def get(self, key: str, default: Any = None) -> Any:
        return super().get(key, default)
    
    def __setitem__(self, key: str, value: Any) -> None:
        super().__setitem__(key, value)
        self._dirty = True
    
    def __delitem__(self, key: str) -> None:
        super().__delitem__(key)
        self._dirty = True
    
    def update(self, *args, **kwargs) -> None:
        super().update(*args, **kwargs)
        self._dirty = True
    
    async def _save_to_db(self) -> None:
        if not self._dirty:
            return
        
        store_repo = get_agents_container().store_repository
        await store_repo.set(self.store_id, dict(self))
        self._dirty = False
    
    async def refresh(self) -> None:
        """Мерджит локальные изменения с данными из БД и сохраняет"""
        store_repo = get_agents_container().store_repository
        db_data = await store_repo.get(self.store_id) or {}
        
        # Мерджим: сначала данные из БД, потом локальные изменения поверх
        merged = {**db_data, **dict(self)}
        
        # Обновляем себя мердженными данными
        self.clear()
        super().update(merged)  # Используем super() чтобы не помечать dirty
        
        # Сохраняем если есть изменения
        if merged != db_data:
            self._dirty = True
            await self.ensure_saved()
        else:
            self._dirty = False
    
    async def reload_from_db(self) -> None:
        """Загружает данные из БД БЕЗ сохранения локальных изменений (перезаписывает локальные данные)"""
        store_repo = get_agents_container().store_repository
        store_data = await store_repo.get(self.store_id)
        
        self.clear()
        if store_data:
            self.update(store_data)
        self._dirty = False
    
    async def ensure_saved(self) -> None:
        await self._save_to_db()


def _sanitize_value(value: Any) -> Any:
    """Санитизирует значение для JSON сериализации"""
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    return str(value)


def _sanitize_args(args: Any) -> Dict[str, Any]:
    """Санитизирует аргументы tool_call"""
    if not isinstance(args, dict):
        return {}
    return {k: _sanitize_value(v) for k, v in args.items()}


def _serialize_tool_call(tc: Any) -> Dict[str, Any]:
    """Сериализует один tool_call"""
    if isinstance(tc, dict):
        result = tc.copy()
        if "args" in result:
            result["args"] = _sanitize_args(result["args"])
        return result
    return {
        "name": getattr(tc, "name", ""),
        "args": _sanitize_args(getattr(tc, "args", {})),
        "id": str(getattr(tc, "id", "")),
    }


def _messages_to_dicts(messages: List[BaseMessage]) -> List[Dict[str, Any]]:
    """Конвертирует сообщения в словари для сериализации"""
    result = []
    for msg in messages:
        msg_dict = {
            "type": msg.__class__.__name__,
            "content": msg.content,
            "additional_kwargs": _sanitize_dict_for_message(dict(msg.additional_kwargs)) if msg.additional_kwargs else {},
            "response_metadata": _sanitize_dict_for_message(dict(msg.response_metadata)) if msg.response_metadata else {},
        }
        
        if hasattr(msg, "id") and msg.id:
            msg_dict["id"] = str(msg.id)
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            msg_dict["tool_calls"] = [_serialize_tool_call(tc) for tc in msg.tool_calls]
        if hasattr(msg, "tool_call_id") and msg.tool_call_id:
            msg_dict["tool_call_id"] = str(msg.tool_call_id)
        if hasattr(msg, "name") and msg.name:
            msg_dict["name"] = str(msg.name)
        
        result.append(msg_dict)
    return result


def _sanitize_dict_for_message(d: dict, _visited: Optional[set] = None) -> dict:
    """Санитизирует словарь, удаляя несериализуемые объекты и циклические ссылки"""
    if not d:
        return {}
    
    if _visited is None:
        _visited = set()
    
    obj_id = id(d)
    if obj_id in _visited:
        return {}
    _visited.add(obj_id)
    
    result = {}
    for k, v in d.items():
        if isinstance(v, (str, int, float, bool, type(None))):
            result[k] = v
        elif isinstance(v, list):
            sanitized_list = []
            for item in v:
                if isinstance(item, (str, int, float, bool, type(None))):
                    sanitized_list.append(item)
                elif isinstance(item, dict):
                    sanitized_list.append(_sanitize_dict_for_message(item, _visited))
                else:
                    sanitized_list.append(str(item))
            result[k] = sanitized_list
        elif isinstance(v, dict):
            result[k] = _sanitize_dict_for_message(v, _visited)
        else:
            result[k] = str(v)
    
    _visited.remove(obj_id)
    return result


MESSAGE_CLASSES = {
    "HumanMessage": HumanMessage,
    "AIMessage": AIMessage,
    "SystemMessage": SystemMessage,
}


def _create_message(msg_dict: Dict[str, Any]) -> Optional[BaseMessage]:
    """Создает сообщение из словаря"""
    msg_type = msg_dict.get("type", "HumanMessage")
    content = msg_dict.get("content", "")
    
    if isinstance(content, str) and len(content) > 100000:
        content = content[:1000] + "... [обрезано]"
    
    if msg_type == "ToolMessage":
        msg = ToolMessage(
            content=content,
            tool_call_id=msg_dict.get("tool_call_id", ""),
            name=msg_dict.get("name", "")
        )
    else:
        msg_class = MESSAGE_CLASSES.get(msg_type, HumanMessage)
        msg = msg_class(content=content)
        if msg_type == "AIMessage" and "tool_calls" in msg_dict:
            msg.tool_calls = msg_dict["tool_calls"]
    
    if "id" in msg_dict and hasattr(msg, "id"):
        msg.id = msg_dict["id"]
    
    return msg


def _dicts_to_messages(msg_dicts: List[Dict[str, Any]]) -> List[BaseMessage]:
    """Конвертирует словари обратно в сообщения"""
    if not msg_dicts:
        return []
    
    if len(msg_dicts) > 1000:
        logger.error(f"StateManager: слишком много сообщений: {len(msg_dicts)}")
        msg_dicts = msg_dicts[-100:]
    
    result = []
    for msg_dict in msg_dicts:
        msg = _create_message(msg_dict)
        if msg:
            result.append(msg)
    
    return result


class StateManager:
    """
    Единообразный менеджер состояния для агентов.
    Рекурсивная архитектура без ветвлений и фолбеков.
    """

    def __init__(self):
        self._store_repository = None
        self._agent_state_repository = None
    
    def _get_store_repository(self):
        """Получает StoreRepository из контейнера"""
        if self._store_repository is None:
            container = get_agents_container()
            self._store_repository = container.store_repository
        return self._store_repository
    
    def _get_agent_state_repository(self):
        """Получает AgentStateRepository из контейнера"""
        if self._agent_state_repository is None:
            container = get_agents_container()
            self._agent_state_repository = container.agent_state_repository
        return self._agent_state_repository

    def _extract_parent_session_id(self, session_id: str) -> str:
        """Извлекает parent_session_id из sub_session_id"""
        sub_pos = session_id.find(":sub:")
        return session_id[:sub_pos] if sub_pos > 0 else session_id
    
    def _detect_memory_policy(self, session_id: str) -> Optional[SubAgentMemoryPolicy]:
        """Определяет политику памяти из формата session_id"""
        if ":sub:" not in session_id:
            return None
        
        parts = session_id.split(":")
        policy_part = parts[3] if len(parts) >= 4 else None
        
        if policy_part == "accumulated":
            return SubAgentMemoryPolicy.ACCUMULATED
        elif policy_part == "snapshot":
            return SubAgentMemoryPolicy.SNAPSHOT
        
        return SubAgentMemoryPolicy.ISOLATED
    
    async def _generate_session_id(
        self,
        parent_session_id: Optional[str],
        agent_id: str,
        policy: SubAgentMemoryPolicy
    ) -> str:
        """Генерирует session_id согласно политике"""
        if not parent_session_id:
            return f"flow_{uuid.uuid4().hex[:12]}"
        
        if policy == SubAgentMemoryPolicy.SHARED:
            return parent_session_id
        
        if policy == SubAgentMemoryPolicy.ACCUMULATED:
            return f"{parent_session_id}:sub:{agent_id}:accumulated"
        
        if policy == SubAgentMemoryPolicy.SNAPSHOT:
            unique_id = uuid.uuid4().hex[:8]
            return f"{parent_session_id}:sub:{agent_id}:snapshot:{unique_id}"
        
        unique_id = uuid.uuid4().hex[:8]
        return f"{parent_session_id}:sub:{agent_id}:{unique_id}"
    
    async def get_sub_session_id(
        self,
        parent_session_id: str,
        sub_agent_id: str,
        policy: SubAgentMemoryPolicy
    ) -> str:
        """Генерирует sub_session_id согласно политике"""
        return await self._generate_session_id(parent_session_id, sub_agent_id, policy)
    
    async def _get_store_id(self, session_id: str, parent_state: Optional[State]) -> str:
        """Определяет store_id для сессии"""
        if parent_state:
            store_id = parent_state.get("store_id")
            if store_id:
                return store_id
            return parent_state.get("session_id")
        
        if ":sub:" in session_id:
            return self._extract_parent_session_id(session_id)
        
        return session_id
    
    async def load_store(self, store_id: str) -> Dict[str, Any]:
        """Загружает store из БД"""
        store_repo = self._get_store_repository()
        store_data = await store_repo.get(store_id)
        return store_data if store_data else {}
    
    async def _load_state_data(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Загружает данные состояния из БД"""
        agent_state_repo = self._get_agent_state_repository()
        state_data = await agent_state_repo.get(session_id)
        return state_data
    
    async def _save_state_data(self, session_id: str, state: State, store_id: str) -> None:
        """Сохраняет данные состояния в БД"""
        messages = state.get("messages", [])
        valid_messages = [msg for msg in messages if not isinstance(msg, str) and hasattr(msg, "content")]
        messages_data = _messages_to_dicts(valid_messages) if valid_messages else []
        
        # ВАЖНО: Не сохраняем remaining_steps=0, чтобы избежать проблем при загрузке
        # Если remaining_steps=0, это означает что агент завершился, и не нужно сохранять это значение
        remaining_steps = state.get("remaining_steps")
        if remaining_steps == 0:
            remaining_steps = None  # Не сохраняем 0, при загрузке будет использовано значение по умолчанию (25)
        
        state_data = {
            "messages": messages_data,
            "task_id": state.get("task_id", ""),
            "session_id": state.get("session_id", session_id),
            "user_id": state.get("user_id", ""),
            "remaining_steps": remaining_steps if remaining_steps is not None else 25,
        }
        
        if "interrupt_context" in state:
            interrupt_ctx = state["interrupt_context"]
            if isinstance(interrupt_ctx, dict):
                state_data["interrupt_context"] = _sanitize_dict_for_message(interrupt_ctx)
            else:
                state_data["interrupt_context"] = str(interrupt_ctx)
        
        agent_state_repo = self._get_agent_state_repository()
        await agent_state_repo.set(session_id, state_data, store_id)
    
    async def get_or_create_session(
        self,
        session_id: Optional[str],
        parent_session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        policy: SubAgentMemoryPolicy = SubAgentMemoryPolicy.ISOLATED,
        initial_store: Optional[Dict[str, Any]] = None
    ) -> State:
        """
        Единообразный метод получения или создания сессии.
        ВСЕГДА возвращает state с StoreProxy (хотя бы пустым).
        
        Args:
            session_id: ID сессии (если None - создается новый)
            parent_session_id: ID родительской сессии (для субагентов)
            agent_id: ID агента (для генерации sub_session_id)
            policy: Политика памяти
            initial_store: Начальные данные store (из FlowConfig)
        
        Returns:
            State с гарантированным store
        """
        if session_id:
            policy = self._detect_memory_policy(session_id) or policy
            parent_session_id = self._extract_parent_session_id(session_id) if ":sub:" in session_id else None
        else:
            session_id = await self._generate_session_id(parent_session_id, agent_id or "unknown", policy)
        
        parent_state = None
        if parent_session_id:
            parent_state = await self.get_or_create_session(parent_session_id)
        
        store_id = await self._get_store_id(session_id, parent_state)
        store_data = await self.load_store(store_id)
        
        if initial_store:
            store_data.update(initial_store)
        
        store = StoreProxy(store_id, store_data)
        
        if initial_store:
            store._dirty = True
            await store.ensure_saved()
        
        state_data = await self._load_state_data(session_id)
        
        logger.info(f"🟢 StateManager.get_or_create_session: session_id={session_id}, state_data={state_data is not None}")
        if state_data:
            logger.info(f"🟢 StateManager: state_data keys={list(state_data.keys())}, remaining_steps={state_data.get('remaining_steps', 'NOT_SET')}")
            messages = _dicts_to_messages(state_data.get("messages", []))
            
            remaining_steps_from_db = state_data.get("remaining_steps")
            # ВАЖНО: Если remaining_steps=0 в БД, это старые данные, используем значение по умолчанию
            # 0 означает что агент завершился, и не нужно использовать это значение для нового запуска
            if remaining_steps_from_db == 0:
                remaining_steps_final = 25
                logger.info("🟢 StateManager: remaining_steps из БД=0 (старое значение), используем дефолт=25")
            else:
                remaining_steps_final = remaining_steps_from_db if remaining_steps_from_db is not None else 25
                logger.info(f"🟢 StateManager: remaining_steps из БД={remaining_steps_from_db}, финальное={remaining_steps_final}")
            
            state = {
                "messages": messages,
                "store": store,
                "task_id": state_data.get("task_id", ""),
                "session_id": session_id,
                "user_id": state_data.get("user_id", ""),
                "remaining_steps": remaining_steps_final,
                "store_id": store_id,
            }
            
            if "interrupt_context" in state_data:
                interrupt_ctx = state_data["interrupt_context"]
                state["interrupt_context"] = interrupt_ctx if isinstance(interrupt_ctx, dict) else {}
        else:
            state = {
                "messages": [],
                "store": store,
                "task_id": "",
                "session_id": session_id,
                "user_id": "",
                "remaining_steps": 25,
                "store_id": store_id,
            }
        
        return state
    
    async def save_session(self, state: State) -> None:
        """
        Сохраняет сессию в БД.
        Store всегда сохраняется через StoreProxy.
        """
        session_id = state.get("session_id")
        if not session_id:
            raise ValueError("state должен содержать 'session_id'")
        
        store = state.get("store")
        if not isinstance(store, StoreProxy):
            raise ValueError("state должен содержать 'store' (StoreProxy)")
        
        store_id = state.get("store_id") or store.store_id
        await store.ensure_saved()
        
        await self._save_state_data(session_id, state, store_id)
    
    async def delete_session(self, session_id: str) -> None:
        """Удаляет сессию из БД"""
        agent_state_repo = self._get_agent_state_repository()
        await agent_state_repo.delete(session_id)


# Глобальный экземпляр
_state_manager = None


async def get_state_manager() -> StateManager:
    """Получает глобальный экземпляр StateManager"""
    global _state_manager
    
    if _state_manager is None:
        _state_manager = StateManager()
        logger.info("StateManager успешно инициализирован")
    
    return _state_manager
