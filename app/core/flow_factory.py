"""
Фабрика для создания Flow экземпляров и работы с историей выполнения.
"""

import asyncio
import logging
from typing import List, Optional, Any, Dict
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage

from app.core.storage import Storage
from app.flows.flow import Flow
from app.identity.models import User, Company
from app.models.history_models import (
    MessageItem,
    MessageRole,
    ToolCallInfo,
    CheckpointInfo,
    MessageHistoryResponse,
    SessionListItem,
    SessionListResponse,
)
from app.models import FlowConfig, ToolReference
from app.core.context import get_context
from app.core.migrator import Migrator
from app.services.variables_service import VariablesService
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from app.core.config import get_settings
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
                raw_source_node = checkpoint_metadata.get("source")
                
                # Фильтруем служебные названия LangGraph
                source_node = None
                if raw_source_node and raw_source_node not in ["__start__", "__end__", "loop"]:
                    source_node = raw_source_node
                
                timestamp_str = checkpoint_metadata.get("ts")
                timestamp = None
                if timestamp_str:
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                
                if include_checkpoints:
                    channel_values = checkpoint_data.get("channel_values", {})
                    messages_in_checkpoint = channel_values.get("messages", [])
                    checkpoint_messages = []
                    
                    for msg in messages_in_checkpoint:
                        message_item = self._parse_message(msg, timestamp, source_node)
                        if message_item:
                            checkpoint_messages.append(message_item)
                    
                    if checkpoint_messages:
                        checkpoint_info = CheckpointInfo(
                            checkpoint_id=checkpoint_id,
                            thread_id=session_id,
                            checkpoint_ns=checkpoint_ns,
                            step=step,
                            source_node=source_node,
                            timestamp=timestamp,
                            messages=checkpoint_messages,
                            metadata=checkpoint_metadata
                        )
                        all_checkpoints.append(checkpoint_info)
            
            if latest_checkpoint:
                latest_metadata = latest_checkpoint.metadata or {}
                raw_latest_source = latest_metadata.get("source")
                
                # Фильтруем служебные названия LangGraph
                latest_source_node = None
                if raw_latest_source and raw_latest_source not in ["__start__", "__end__", "loop"]:
                    latest_source_node = raw_latest_source
                
                channel_values = latest_checkpoint.checkpoint.get("channel_values", {})
                messages_in_checkpoint = channel_values.get("messages", [])
                
                for msg in messages_in_checkpoint:
                    message_item = self._parse_message(msg, None, latest_source_node)
                    if message_item:
                        all_messages.append(message_item)
            
            # Дедупликация сообщений по содержимому
            all_messages = self._deduplicate_messages(all_messages)
        
            created_at = all_messages[0].timestamp if all_messages else None
            last_activity = all_messages[-1].timestamp if all_messages else None
        
        session_config = await self.storage.get_session_config(session_id)
        flow_id = session_config.flow_id if session_config else None
        
        flow_name = None
        if flow_id:
            flow_config = await self.storage.get_flow_config(flow_id)
            if flow_config and hasattr(flow_config, 'name'):
                flow_name = flow_config.name
        
        logger.info(
            f"✅ Загружено {len(all_messages)} сообщений из {checkpoint_count} checkpoint'ов для {session_id}"
        )
        
        # Обновляем статистику для старых сессий (Database-First: актуализация данных)
        if session_config and session_config.message_count == 0 and len(all_messages) > 0:
            session_config.message_count = len(all_messages)
            
            # Ищем первое сообщение пользователя
            if not session_config.first_message:
                for msg in all_messages:
                    if msg.role.value == "user" and msg.content:
                        preview = msg.content[:100] if len(msg.content) > 100 else msg.content
                        session_config.first_message = preview
                        break
            
            await self.storage.set_session_config(session_config)
            logger.info(f"📊 Обновлена статистика старой сессии: {len(all_messages)} сообщений")
        
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
        
        filtered_sessions = []
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
            
            filtered_sessions.append(session)
        
        logger.info(f"🔍 Отфильтровано {len(filtered_sessions)} сессий, начинаем параллельную обработку")
        
        user_cache: Dict[str, Optional[str]] = {}
        flow_cache: Dict[str, Optional[str]] = {}
        
        async def process_session(session: Any) -> SessionListItem:
            # Database-First: все данные берем из SessionConfig (БД), не обращаемся к checkpointer
            
            flow_name = None
            if session.flow_id:
                if session.flow_id not in flow_cache:
                    flow_config = await self.storage.get_flow_config(session.flow_id)
                    flow_cache[session.flow_id] = flow_config.name if flow_config and hasattr(flow_config, 'name') else None
                flow_name = flow_cache[session.flow_id]
            
            user_name = None
            if session.user_id:
                if session.user_id not in user_cache:
                    try:
                        user_key = f"user:{session.user_id}"
                        user_json = await self.storage.get(user_key, force_global=True)
                        if user_json:
                            user = User.model_validate_json(user_json)
                            user_cache[session.user_id] = user.name
                        else:
                            user_cache[session.user_id] = None
                    except Exception as e:
                        logger.error(f"❌ Ошибка загрузки пользователя {session.user_id}: {e}")
                        user_cache[session.user_id] = None
                user_name = user_cache[session.user_id]
            
            return SessionListItem(
                session_id=session.session_id,
                flow_id=session.flow_id,
                flow_name=flow_name,
                platform=session.platform,
                user_id=session.user_id,
                user_name=user_name,
                status=session.status.value,
                message_count=session.message_count,
                first_message=session.first_message,
                created_at=session.created_at,
                last_activity=session.last_activity,
                metadata=session.metadata
            )
        
        sessions = await asyncio.gather(*[process_session(session) for session in filtered_sessions])
        
        sessions_list = list(sessions)
        sessions_list.sort(key=lambda s: s.last_activity or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        
        total = len(sessions_list)
        paginated_sessions = sessions_list[offset:offset + limit]
        
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

    def _parse_message(self, msg: Any, default_timestamp: Optional[datetime] = None, source_node: Optional[str] = None) -> Optional[MessageItem]:
        """
        Парсит сообщение из LangGraph в MessageItem.
        
        Args:
            msg: Сообщение из LangGraph (HumanMessage, AIMessage, ToolMessage, etc)
            default_timestamp: Время по умолчанию если не указано в сообщении
            source_node: Название node/агента, создавшего сообщение (применяется только к AI/Tool сообщениям)
            
        Returns:
            MessageItem или None если сообщение не удалось распарсить
        """
        if isinstance(msg, HumanMessage):
            return MessageItem(
                role=MessageRole.USER,
                content=msg.content or "",
                timestamp=default_timestamp or datetime.now(timezone.utc),
                source_node=None,
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
                source_node=source_node,
                metadata=msg.additional_kwargs or {}
            )
        
        elif isinstance(msg, ToolMessage):
            return MessageItem(
                role=MessageRole.TOOL,
                content=msg.content or "",
                timestamp=default_timestamp or datetime.now(timezone.utc),
                source_node=source_node,
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
                source_node=source_node,
                metadata=msg.additional_kwargs or {}
            )
        
        else:
            logger.warning(f"⚠️ Неизвестный тип сообщения: {type(msg)}")
            return MessageItem(
                role=MessageRole.SYSTEM,
                content=str(msg),
                timestamp=default_timestamp or datetime.now(timezone.utc),
                source_node=source_node,
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

    async def _get_session_info(self, session_id: str) -> tuple[int, Optional[str]]:
        """
        Получает информацию о сессии: количество сообщений и первое сообщение пользователя.
        Оптимизирован для получения обеих данных за один проход.
        
        Args:
            session_id: ID сессии
            
        Returns:
            Tuple (количество сообщений, первое сообщение пользователя)
        """
        settings = get_settings()
        config = {"configurable": {"thread_id": session_id}}
        
        message_count = 0
        first_message = None
        oldest_checkpoint = None
        
        checkpointer_cm = AsyncPostgresSaver.from_conn_string(settings.database.checkpointer_url)
        async with checkpointer_cm as checkpointer:
            async for checkpoint_tuple in checkpointer.alist(config, limit=20):
                if not checkpoint_tuple or not checkpoint_tuple.checkpoint:
                    continue
                
                channel_values = checkpoint_tuple.checkpoint.get("channel_values", {})
                messages = channel_values.get("messages", [])
                message_count = max(message_count, len(messages))
                
                oldest_checkpoint = checkpoint_tuple
            
            if oldest_checkpoint:
                channel_values = oldest_checkpoint.checkpoint.get("channel_values", {})
                messages = channel_values.get("messages", [])
                
                for msg in messages:
                    if isinstance(msg, HumanMessage):
                        content = msg.content or ""
                        first_message = content[:60] if len(content) > 60 else content
                        break
        
        return message_count, first_message
    
    async def install_flow(self, flow_id: str) -> Dict[str, Any]:
        """
        Устанавливает flow из Store для текущей компании.
        
        Использует существующую логику Migrator.migrate_for_company
        для миграции flow с зависимостями из системной компании.
        
        Args:
            flow_id: ID flow для установки (например, "app.flows.weather_flow.weather_flow_config")
            
        Returns:
            Информация об установке
        """
        context = get_context()
        company_id = context.active_company.company_id
        user_id = context.user.user_id
        
        logger.info(f"Установка flow {flow_id} для компании {company_id}")
        
        company_data = await self.storage.get(f"company:{company_id}", force_global=True)
        if not company_data:
            raise ValueError(f"Компания {company_id} не найдена")
        
        company = Company.model_validate_json(company_data)
        
        migrator = Migrator()
        await migrator.migrate_for_company(
            company=company,
            flows=[flow_id],
            with_dependencies=True
        )
        
        flow_config = await self.storage.get_flow_config(flow_id)
        if flow_config and flow_config.install_hook:
            await self._execute_hook(flow_config.install_hook, flow_config, company_id)
        
        additional_url = None
        if flow_config and flow_config.after_install_hook:
            additional_url = await self._execute_after_install_hook(flow_config.after_install_hook)
        
        logger.info(f"Flow {flow_id} успешно установлен в компанию {company_id}")
        
        return {
            "flow_id": flow_id,
            "company_id": company_id,
            "installed_at": datetime.now(timezone.utc).isoformat(),
            "installed_by": user_id,
            "additional_url": additional_url
        }
    
    async def uninstall_flow(self, flow_id: str) -> None:
        """
        Удаляет flow из текущей компании.
        
        Выполняет uninstall hook если есть, удаляет агентов и сам flow.
        
        Args:
            flow_id: ID flow для удаления
        """
        context = get_context()
        company_id = context.active_company.company_id
        
        logger.info(f"Удаление flow {flow_id} из компании {company_id}")
        
        flow_config = await self.storage.get_flow_config(flow_id)
        if not flow_config:
            raise ValueError(f"Flow {flow_id} не установлен в компании {company_id}")
        
        if flow_config.uninstall_hook:
            await self._execute_hook(flow_config.uninstall_hook, flow_config, company_id)
        
        await self._delete_flow_agents(flow_config.entry_point_agent)
        
        await self.storage.delete(f"flow:{flow_id}")
        
        logger.info(f"Flow {flow_id} успешно удален из компании {company_id}")
    
    async def _execute_hook(
        self,
        hook_ref: ToolReference,
        flow_config: FlowConfig,
        company_id: str
    ) -> None:
        """Выполняет hook из ToolReference через exec()"""
        
        if not hook_ref or not hook_ref.inline_code:
            return
        
        namespace = {
            "FlowConfig": FlowConfig,
            "logger": logger,
            "Storage": Storage,
            "VariablesService": VariablesService,
            "datetime": datetime,
        }
        
        exec(hook_ref.inline_code, namespace)
        
        hook_func = namespace.get("install") or namespace.get("uninstall")
        if hook_func and callable(hook_func):
            await hook_func(flow_config, company_id)
            logger.info(f"Выполнен hook {hook_ref.tool_id}")
    
    async def _execute_after_install_hook(self, hook_ref: ToolReference) -> str | None:
        """
        Выполняет after_install_hook из ToolReference через exec().
        
        Args:
            hook_ref: Ссылка на hook
            
        Returns:
            URL для открытия в новом окне или None
        """
        if not hook_ref or not hook_ref.inline_code:
            return None
        
        namespace = {
            "logger": logger,
            "FlowConfig": FlowConfig,
        }
        
        exec(hook_ref.inline_code, namespace)
        
        after_install_func = namespace.get("after_install")
        if after_install_func and callable(after_install_func):
            result = await after_install_func()
            if isinstance(result, str) and result.strip():
                logger.info(f"after_install_hook вернул URL: {result.strip()}")
                return result.strip()
        
        return None
    
    async def _delete_flow_agents(self, agent_id: str) -> None:
        """Удаляет агента и его субагентов рекурсивно"""
        agent_config = await self.storage.get_agent_config(agent_id)
        if not agent_config:
            return
        
        for tool_ref in agent_config.tools:
            if tool_ref.tool_id.startswith("agent:"):
                sub_agent_id = tool_ref.tool_id.replace("agent:", "")
                await self._delete_flow_agents(sub_agent_id)
        
        await self.storage.delete(f"agent:{agent_id}")
        logger.info(f"Агент {agent_id} удален")
