"""
Фабрика для создания Flow экземпляров и работы с историей выполнения.
"""

import logging
from typing import List, Optional, Any
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage

from app.core.storage import Storage
from app.flows.flow import Flow
from app.models.history_models import (
    MessageItem,
    MessageRole,
    ToolCallInfo,
    CheckpointInfo,
    MessageHistoryResponse,
    SessionListItem,
    SessionListResponse,
)

logger = logging.getLogger(__name__)


class FlowFactory:
    """Фабрика для Flow и управления историей выполнения"""

    def __init__(self):
        self.storage = Storage()

    async def get_flow(self, flow_id: str) -> Flow:
        """
        Получает Flow по ID из БД и создает экземпляр.

        Args:
            flow_id: Идентификатор flow

        Returns:
            Экземпляр Flow
        """
        config = await self.storage.get_flow_config(flow_id)
        if not config:
            raise ValueError(f"Flow {flow_id} не найден в БД")

        flow = Flow(config)
        await flow.initialize()

        logger.debug(f"Flow {flow_id} создан")
        return flow

    async def get_flow_history(
        self, 
        session_id: str, 
        limit: Optional[int] = 100,
        include_checkpoints: bool = False
    ) -> MessageHistoryResponse:
        """
        Получает полную историю выполнения flow для сессии из LangGraph checkpointer.
        
        Args:
            session_id: ID сессии (thread_id для LangGraph)
            limit: Максимальное количество checkpoint'ов для загрузки
            include_checkpoints: Включать ли детальную информацию о checkpoint'ах
            
        Returns:
            MessageHistoryResponse с полной историей сообщений
        """
        logger.info(f"📜 Получение истории flow для сессии {session_id}")
        
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from app.core.config import get_settings
        
        settings = get_settings()
        config = {"configurable": {"thread_id": session_id}}
        
        all_messages = []
        all_checkpoints = []
        checkpoint_count = 0
        
        checkpointer_cm = AsyncPostgresSaver.from_conn_string(settings.database.checkpointer_url)
        async with checkpointer_cm as checkpointer:
            latest_checkpoint = None
            
            async for checkpoint_tuple in checkpointer.alist(config, limit=limit):
                checkpoint_count += 1
                
                if not checkpoint_tuple or not checkpoint_tuple.checkpoint:
                    continue
                
                if checkpoint_count == 1:
                    latest_checkpoint = checkpoint_tuple
                
                checkpoint_data = checkpoint_tuple.checkpoint
                checkpoint_metadata = checkpoint_tuple.metadata or {}
                checkpoint_config = checkpoint_tuple.config or {}
                
                checkpoint_id = checkpoint_config.get("configurable", {}).get("checkpoint_id", f"checkpoint_{checkpoint_count}")
                checkpoint_ns = checkpoint_config.get("configurable", {}).get("checkpoint_ns", "")
                
                step = checkpoint_metadata.get("step", checkpoint_count)
                timestamp_str = checkpoint_metadata.get("ts")
                timestamp = None
                if timestamp_str:
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                
                if include_checkpoints:
                    channel_values = checkpoint_data.get("channel_values", {})
                    messages_in_checkpoint = channel_values.get("messages", [])
                    checkpoint_messages = []
                    
                    for msg in messages_in_checkpoint:
                        message_item = self._parse_message(msg, timestamp)
                        if message_item:
                            checkpoint_messages.append(message_item)
                    
                    if checkpoint_messages:
                        checkpoint_info = CheckpointInfo(
                            checkpoint_id=checkpoint_id,
                            thread_id=session_id,
                            checkpoint_ns=checkpoint_ns,
                            step=step,
                            timestamp=timestamp,
                            messages=checkpoint_messages,
                            metadata=checkpoint_metadata
                        )
                        all_checkpoints.append(checkpoint_info)
            
            if latest_checkpoint:
                channel_values = latest_checkpoint.checkpoint.get("channel_values", {})
                messages_in_checkpoint = channel_values.get("messages", [])
                
                for msg in messages_in_checkpoint:
                    message_item = self._parse_message(msg, None)
                    if message_item:
                        all_messages.append(message_item)
        
            created_at = all_messages[0].timestamp if all_messages else None
            last_activity = all_messages[-1].timestamp if all_messages else None
        
        session_config = await self.storage.get_session_config(session_id)
        flow_id = session_config.flow_id if session_config else None
        
        flow_name = None
        if flow_id:
            try:
                flow_config = await self.storage.get_flow_config(flow_id)
                if flow_config and hasattr(flow_config, 'name'):
                    flow_name = flow_config.name
            except Exception as e:
                logger.warning(f"⚠️ Не удалось получить имя flow {flow_id}: {e}")
        
        logger.info(
            f"✅ Загружено {len(all_messages)} сообщений из {checkpoint_count} checkpoint'ов для {session_id}"
        )
        
        return MessageHistoryResponse(
            session_id=session_id,
            thread_id=session_id,
            flow_id=flow_id,
            flow_name=flow_name,
            messages=all_messages,
            checkpoints=all_checkpoints if include_checkpoints else [],
            total_messages=len(all_messages),
            total_checkpoints=checkpoint_count,
            created_at=created_at,
            last_activity=last_activity
        )

    async def get_flow_sessions(
        self,
        platform: Optional[str] = None,
        flow_id: Optional[str] = None,
        user_id: Optional[str] = None,
        status: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0
    ) -> SessionListResponse:
        """
        Получает список сессий выполнения flow с фильтрацией.
        
        Args:
            platform: Фильтр по платформе
            flow_id: Фильтр по flow
            user_id: Фильтр по пользователю
            status: Фильтр по статусу
            date_from: Фильтр от даты
            date_to: Фильтр до даты
            limit: Максимальное количество результатов
            offset: Смещение для пагинации
            
        Returns:
            SessionListResponse со списком сессий
        """
        logger.info(f"📋 Получение списка сессий flow (limit={limit}, offset={offset})")
        
        from app.models import SessionConfig
        
        session_keys = await self.storage.list_by_prefix("session:", limit=1000)
        
        sessions = []
        for key in session_keys:
            session_json = await self.storage.get(key)
            if not session_json:
                continue
            
            session = SessionConfig.model_validate_json(session_json)
            
            if platform and session.platform != platform:
                continue
            if flow_id and session.flow_id != flow_id:
                continue
            if user_id and session.user_id != user_id:
                continue
            if status and session.status.value != status:
                continue
            if date_from and session.created_at and session.created_at < date_from:
                continue
            if date_to and session.created_at and session.created_at > date_to:
                continue
            
            message_count = await self._get_session_message_count(session.session_id)
            
            flow_name = None
            if session.flow_id:
                try:
                    flow_config = await self.storage.get_flow_config(session.flow_id)
                    if flow_config and hasattr(flow_config, 'name'):
                        flow_name = flow_config.name
                except Exception:
                    pass
            
            session_item = SessionListItem(
                session_id=session.session_id,
                flow_id=session.flow_id,
                flow_name=flow_name,
                platform=session.platform,
                user_id=session.user_id,
                status=session.status.value,
                message_count=message_count,
                created_at=session.created_at,
                last_activity=session.last_activity,
                metadata=session.metadata
            )
            sessions.append(session_item)
        
        sessions.sort(key=lambda s: s.last_activity or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        
        total = len(sessions)
        paginated_sessions = sessions[offset:offset + limit]
        
        filters = {
            "platform": platform,
            "flow_id": flow_id,
            "user_id": user_id,
            "status": status,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None
        }
        
        logger.info(f"✅ Найдено {total} сессий, возвращаем {len(paginated_sessions)}")
        
        return SessionListResponse(
            sessions=paginated_sessions,
            total=total,
            limit=limit,
            offset=offset,
            filters=filters
        )

    def _parse_message(self, msg: Any, default_timestamp: Optional[datetime] = None) -> Optional[MessageItem]:
        """
        Парсит сообщение из LangGraph в MessageItem.
        
        Args:
            msg: Сообщение из LangGraph (HumanMessage, AIMessage, ToolMessage, etc)
            default_timestamp: Время по умолчанию если не указано в сообщении
            
        Returns:
            MessageItem или None если сообщение не удалось распарсить
        """
        if isinstance(msg, HumanMessage):
            return MessageItem(
                role=MessageRole.USER,
                content=msg.content or "",
                timestamp=default_timestamp or datetime.now(timezone.utc),
                metadata=msg.additional_kwargs or {}
            )
        
        elif isinstance(msg, AIMessage):
            tool_calls = []
            
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_call = ToolCallInfo(
                        tool_name=tc.get('name', 'unknown'),
                        tool_id=tc.get('id', 'unknown'),
                        arguments=tc.get('args', {})
                    )
                    tool_calls.append(tool_call)
            
            return MessageItem(
                role=MessageRole.ASSISTANT,
                content=msg.content or "",
                timestamp=default_timestamp or datetime.now(timezone.utc),
                tool_calls=tool_calls,
                metadata=msg.additional_kwargs or {}
            )
        
        elif isinstance(msg, ToolMessage):
            return MessageItem(
                role=MessageRole.TOOL,
                content=msg.content or "",
                timestamp=default_timestamp or datetime.now(timezone.utc),
                metadata={
                    "tool_call_id": msg.tool_call_id if hasattr(msg, 'tool_call_id') else None,
                    **(msg.additional_kwargs or {})
                }
            )
        
        elif isinstance(msg, SystemMessage):
            return MessageItem(
                role=MessageRole.SYSTEM,
                content=msg.content or "",
                timestamp=default_timestamp or datetime.now(timezone.utc),
                metadata=msg.additional_kwargs or {}
            )
        
        else:
            logger.warning(f"⚠️ Неизвестный тип сообщения: {type(msg)}")
            return MessageItem(
                role=MessageRole.SYSTEM,
                content=str(msg),
                timestamp=default_timestamp or datetime.now(timezone.utc),
                metadata={"original_type": str(type(msg))}
            )

    def _deduplicate_messages(self, messages: List[MessageItem]) -> List[MessageItem]:
        """
        Удаляет дубликаты сообщений на основе содержимого и времени.
        
        Args:
            messages: Список сообщений
            
        Returns:
            Список уникальных сообщений
        """
        seen = set()
        unique_messages = []
        
        for msg in messages:
            msg_key = (
                msg.role.value,
                msg.content[:100],
                msg.timestamp.isoformat() if msg.timestamp else "no_time"
            )
            
            if msg_key not in seen:
                seen.add(msg_key)
                unique_messages.append(msg)
        
        return unique_messages

    async def _get_session_message_count(self, session_id: str) -> int:
        """
        Получает количество сообщений в сессии.
        
        Args:
            session_id: ID сессии
            
        Returns:
            Количество сообщений
        """
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from app.core.config import get_settings
        
        settings = get_settings()
        config = {"configurable": {"thread_id": session_id}}
        
        message_count = 0
        checkpointer_cm = AsyncPostgresSaver.from_conn_string(settings.database.checkpointer_url)
        async with checkpointer_cm as checkpointer:
            async for checkpoint_tuple in checkpointer.alist(config, limit=10):
                if checkpoint_tuple and checkpoint_tuple.checkpoint:
                    channel_values = checkpoint_tuple.checkpoint.get("channel_values", {})
                    messages = channel_values.get("messages", [])
                    message_count = max(message_count, len(messages))
        
            return message_count
