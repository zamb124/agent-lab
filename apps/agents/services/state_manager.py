"""
Менеджер состояния для агентов.
Единообразная рекурсивная архитектура без ветвлений и фолбеков.
"""

import json
import logging
import uuid
from typing import Any, Dict, Optional, List
from sqlalchemy import text
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from apps.agents.services.state import State
from core.db.database import get_session_factory
from apps.agents.models.core_models import SubAgentMemoryPolicy

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
        
        store_data_json = json.dumps(dict(self), default=str, ensure_ascii=False)
        session_factory = await get_session_factory()
        
        async with session_factory() as session:
            async with session.begin():
                await session.execute(
                    text("""
                        INSERT INTO stores (store_id, store_data, updated_at)
                        VALUES (:store_id, CAST(:store_data AS JSONB), CURRENT_TIMESTAMP)
                        ON CONFLICT (store_id)
                        DO UPDATE SET store_data = CAST(:store_data AS JSONB), updated_at = CURRENT_TIMESTAMP
                    """),
                    {"store_id": self.store_id, "store_data": store_data_json}
                )
        
        self._dirty = False
    
    async def refresh(self) -> None:
        await self.ensure_saved()
        
        session_factory = await get_session_factory()
        async with session_factory() as session:
            result = await session.execute(
                text("SELECT store_data FROM stores WHERE store_id = :store_id"),
                {"store_id": self.store_id}
            )
            row = result.first()
        
        self.clear()
        if row and row[0]:
            self.update(row[0])
        self._dirty = False
    
    async def ensure_saved(self) -> None:
        await self._save_to_db()


def _messages_to_dicts(messages: List[BaseMessage]) -> List[Dict[str, Any]]:
    """Конвертирует сообщения в словари для сериализации"""
    result = []
    for msg in messages:
        additional_kwargs = {}
        if msg.additional_kwargs:
            additional_kwargs = _sanitize_dict_for_message(dict(msg.additional_kwargs))
        
        response_metadata = {}
        if msg.response_metadata:
            response_metadata = _sanitize_dict_for_message(dict(msg.response_metadata))
        
        msg_dict = {
            "type": msg.__class__.__name__,
            "content": msg.content,
            "additional_kwargs": additional_kwargs,
            "response_metadata": response_metadata,
        }
        if hasattr(msg, "id") and msg.id:
            msg_dict["id"] = str(msg.id)
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            tool_calls_list = []
            for tc in msg.tool_calls:
                if isinstance(tc, dict):
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


def _dicts_to_messages(msg_dicts: List[Dict[str, Any]]) -> List[BaseMessage]:
    """Конвертирует словари обратно в сообщения"""
    import logging
    logger = logging.getLogger(__name__)
    
    if not msg_dicts:
        logger.info("🟢 StateManager._dicts_to_messages: пустой список сообщений")
        return []
    
    logger.info(f"🟢 StateManager._dicts_to_messages: конвертируем {len(msg_dicts)} сообщений")
    
    # Защита от слишком большого количества сообщений (может быть признаком проблемы)
    if len(msg_dicts) > 1000:
        logger.error(f"🔴 StateManager: ПРЕДУПРЕЖДЕНИЕ! Слишком много сообщений: {len(msg_dicts)}. Возможна проблема с сохранением состояния.")
        msg_dicts = msg_dicts[-100:]  # Берем только последние 100
    
    result = []
    for i, msg_dict in enumerate(msg_dicts):
        if i % 50 == 0:  # Логируем каждое 50-е сообщение, чтобы не засорять логи
            logger.info(f"🟢 StateManager: обрабатываем сообщение {i+1}/{len(msg_dicts)}")
        
        msg_type = msg_dict.get("type", "HumanMessage")
        content = msg_dict.get("content", "")
        
        # Защита от слишком большого content (может быть циклическая ссылка)
        if isinstance(content, str) and len(content) > 100000:
            logger.warning(f"🟢 StateManager: сообщение {i+1} имеет очень большой content ({len(content)} символов), обрезаем")
            content = content[:1000] + "... [обрезано]"
        
        try:
            if msg_type == "HumanMessage":
                msg = HumanMessage(content=content)
            elif msg_type == "AIMessage":
                msg = AIMessage(content=content)
                if "tool_calls" in msg_dict:
                    msg.tool_calls = msg_dict["tool_calls"]
            elif msg_type == "SystemMessage":
                msg = SystemMessage(content=content)
            elif msg_type == "ToolMessage":
                tool_call_id = msg_dict.get("tool_call_id", "")
                name = msg_dict.get("name", "")
                msg = ToolMessage(content=content, tool_call_id=tool_call_id, name=name)
            else:
                msg = HumanMessage(content=content)
            
            if "id" in msg_dict and hasattr(msg, "id"):
                msg.id = msg_dict["id"]
            
            result.append(msg)
        except Exception as e:
            logger.error(f"🔴 StateManager: ОШИБКА при создании сообщения {i+1} (type={msg_type}): {e}", exc_info=True)
            # Пропускаем проблемное сообщение вместо падения
            continue
    
    logger.info(f"🟢 StateManager._dicts_to_messages: успешно конвертировано {len(result)} из {len(msg_dicts)} сообщений")
    return result


class StateManager:
    """
    Единообразный менеджер состояния для агентов.
    Рекурсивная архитектура без ветвлений и фолбеков.
    """

    def __init__(self):
        pass

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
        session_factory = await get_session_factory()
        async with session_factory() as session:
            result = await session.execute(
                text("SELECT store_data FROM stores WHERE store_id = :store_id"),
                {"store_id": store_id}
            )
            row = result.first()
        
        return row[0] if row and row[0] else {}
    
    async def _load_state_data(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Загружает данные состояния из БД"""
        session_factory = await get_session_factory()
        async with session_factory() as session:
            result = await session.execute(
                text("""
                    SELECT a.state_data, a.store_id
                    FROM agent_states a
                    WHERE a.session_id = :session_id
                """),
                {"session_id": session_id}
            )
            row = result.first()
        
        if not row:
            return None
        
        state_data_raw, store_id = row[0], row[1]
        
        if isinstance(state_data_raw, str):
            state_data = json.loads(state_data_raw)
        elif isinstance(state_data_raw, dict):
            state_data = state_data_raw
        else:
            state_data = dict(state_data_raw) if hasattr(state_data_raw, '__dict__') else {}
        
        state_data["_store_id"] = store_id or session_id
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
        
        state_data_json = json.dumps(state_data, default=str, ensure_ascii=False)
        
        session_factory = await get_session_factory()
        async with session_factory() as session:
            async with session.begin():
                await session.execute(
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
        session_factory = await get_session_factory()
        async with session_factory() as session:
            async with session.begin():
                await session.execute(
                    text("DELETE FROM agent_states WHERE session_id = :session_id"),
                    {"session_id": session_id}
                )


# Глобальный экземпляр
_state_manager = None


async def get_state_manager() -> StateManager:
    """Получает глобальный экземпляр StateManager"""
    global _state_manager
    
    if _state_manager is None:
        _state_manager = StateManager()
        logger.info("StateManager успешно инициализирован")
    
    return _state_manager
