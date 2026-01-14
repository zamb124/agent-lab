"""
BaseChannel - абстрактный базовый класс для каналов коммуникации.

Каждый канал (A2A, Telegram, WhatsApp) реализует этот интерфейс.
Содержит основную логику выполнения задач и стриминга событий.
"""

from __future__ import annotations

import json
import uuid
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict, List, Optional, Union

from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    Message,
    MessageSendParams,
    Task,
    TaskArtifactUpdateEvent,
    TaskIdParams,
    TaskPushNotificationConfig,
    TaskQueryParams,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from a2a.utils.message import get_message_text, new_agent_text_message

from apps.agents.src.agent.exceptions import AgentInterrupt
from core.state import InterruptData
from core.auth import permission_checker
from core.auth.errors import PermissionDeniedA2AError
from apps.agents.config import get_settings
from apps.agents.src.container import get_container
from core.context import Context, User, clear_context, get_context, set_context
from core.logging import get_logger
from apps.agents.src.mock import check_mock_permission, resolve_mock_config
from apps.agents.src.models.agent_config import Edge, SkillConfig
from apps.agents.src.models.enums import NodeType
from apps.agents.src.services.agent_validator import AgentValidator, ValidationSeverity
from apps.agents.src.state import create_initial_state
from apps.agents.src.streaming import Emitter
from core.state import ExecutionState
from apps.agents.src.tasks.push_notification_tasks import send_task_update
from core.tracing import get_tracer
from core.tracing.context import TraceContext, get_current_trace_context
from core.tracing.provider import is_tracing_enabled
from apps.agents.src.utils import extract_json_from_response
from apps.agents.src.variables import VariableResolver

logger = get_logger(__name__)


class PermissionDenied(Exception):
    """
    Исключение для отсутствия прав доступа.
    
    Содержит PermissionDeniedA2AError для формирования JSON-RPC ответа.
    """
    
    def __init__(self, error: PermissionDeniedA2AError):
        self.error = error
        super().__init__(error.message)


# PreparedTaskParams вынесен в types.py чтобы избежать циклических импортов
from apps.agents.src.channels.types import PreparedTaskParams


class BaseChannel(ABC):
    """
    Абстрактный базовый класс канала коммуникации.
    
    Определяет интерфейс для всех каналов: A2A, Telegram, WhatsApp и др.
    Содержит основную логику выполнения задач.
    """
    
    name: str  # Имя канала: "a2a", "telegram", "whatsapp"
    
    def __init__(
        self, 
        agent_id: str, 
        context: Optional[Context] = None,
        agent_config: Optional[Any] = None
    ):
        self.agent_id = agent_id
        self.context = context or get_context()
        self._agent_config = agent_config
    
    # === Универсальный метод отправки сообщения ===
    
    @abstractmethod
    async def send_to_user(
        self,
        content: str,
        buttons: Optional[List[str]] = None,
        attachments: Optional[List[Any]] = None,
    ) -> None:
        """
        Отправляет сообщение пользователю через канал.
        
        Args:
            content: Текст сообщения
            buttons: Кнопки быстрого ответа (опционально)
            attachments: Вложения (опционально)
        """
        pass
    
    # === Общие утилитарные методы ===
    
    def _generate_session_id(self, context_id: str) -> str:
        """Генерирует session_id из agent_id и context_id."""
        return f"{self.agent_id}:{context_id}"
    
    def _generate_ids(self, message: Optional[Message] = None) -> tuple[str, str]:
        """
        Генерирует task_id и context_id.
        
        Returns:
            Tuple (task_id, context_id)
        """
        if message:
            task_id = message.task_id or str(uuid.uuid4())
            context_id = message.context_id or str(uuid.uuid4())
        else:
            task_id = str(uuid.uuid4())
            context_id = str(uuid.uuid4())
        return task_id, context_id
    
    def _get_user_groups_from_context(self, context: Any) -> List[str]:
        """
        Извлекает группы пользователя из контекста.
        
        Args:
            context: контекст запроса (dict с user_groups или Context)
            
        Returns:
            Список групп пользователя
        """
        if context is None:
            # Пробуем взять из Context канала
            if self.context and self.context.metadata:
                return self.context.metadata.get("grps", []) or []
            return []
        
        if isinstance(context, dict):
            return context.get("user_groups", []) or []
        
        if isinstance(context, Context):
            return context.metadata.get("grps", []) or []
        
        return getattr(context, "user_groups", []) or []
    
    async def check_permissions(
        self,
        user_groups: List[str],
        skill_id: str = "default",
    ) -> None:
        """
        Проверяет permissions на агента и skill.
        
        Args:
            user_groups: группы пользователя из JWT (grps claim)
            skill_id: ID skill
            
        Raises:
            PermissionDenied: если нет доступа к агенту или skill
        """
        config = get_settings()
        
        # Если проверка permissions отключена - пропускаем
        if not config.auth.permissions_enabled:
            return
        
        container = get_container()
        agent_config = await container.agent_repository.get(self.agent_id)
        
        if agent_config is None:
            return
        
        # Проверка permission на агента
        if not permission_checker.check_flow_permission(user_groups, agent_config.permission):
            required = permission_checker.normalize(agent_config.permission)
            raise PermissionDenied(
                PermissionDeniedA2AError.for_flow(self.agent_id, required)
            )
        
        # Проверка permission на skill
        skill_config = None
        if agent_config.skills and skill_id in agent_config.skills:
            skill_config = agent_config.skills[skill_id]
        
        if skill_config is not None:
            if not permission_checker.check_skill_permission(
                user_groups, skill_config.permission, agent_config.permission
            ):
                effective_perm = skill_config.permission if skill_config.permission else agent_config.permission
                required = permission_checker.normalize(effective_perm)
                raise PermissionDenied(
                    PermissionDeniedA2AError.for_skill(skill_id, self.agent_id, required)
                )
    
    async def _get_state(self, session_id: str) -> Optional[ExecutionState]:
        """Получает state из StateManager."""
        container = get_container()
        state_dict = await container.state_manager.get_state(session_id)
        if state_dict is None:
            return None
        return ExecutionState.model_validate(state_dict)
    
    async def _save_state(self, session_id: str, state: ExecutionState) -> None:
        """Сохраняет state в StateManager."""
        container = get_container()
        await container.state_manager.save_state(session_id, state)
    
    async def _prepare_task_params(
        self,
        content: str,
        context_id: Optional[str] = None,
        task_id: Optional[str] = None,
        message: Optional[Message] = None,
        metadata: Optional[Dict] = None,
        files_data: Optional[List[Dict]] = None,
        user_id: Optional[str] = None,
    ) -> PreparedTaskParams:
        """
        Подготовка общих параметров для process_task.
        
        Общая логика для всех каналов.
        Берет данные пользователя из Context, если он установлен.
        """
        if task_id is None or context_id is None:
            task_id, context_id = self._generate_ids(message)
        
        # Получаем данные пользователя из Context канала
        # ВАЖНО: session_id агента НЕ берется из Context.session_id (это авторизационная сессия)
        # Сессия агента генерируется на основе context_id из сообщения
        if self.context and self.context.user:
            if user_id is None:
                user_id = self.context.user.user_id
        
        # Сессия агента всегда генерируется на основе context_id
        session_id = self._generate_session_id(context_id)
        
        state = await self._get_state(session_id)
        
        if state is None:
            skill_id = "default"
            if metadata and "skill" in metadata:
                skill_id = metadata["skill"]
            is_resume = False
        else:
            skill_id = state.skill_id
            # Resume если есть interrupt ИЛИ breakpoint_hit
            is_resume = bool(state.interrupt) or bool(state.breakpoint_hit)
            
            if state.interrupt:
                saved_task_id = state.interrupt.context.get("task_id") if state.interrupt.context else None
                if saved_task_id:
                    task_id = saved_task_id
        
        # Объединяем metadata из Context канала с переданным metadata
        final_metadata = metadata or {}
        if self.context and self.context.metadata:
            final_metadata = {**self.context.metadata, **final_metadata}
        
        return PreparedTaskParams(
            task_id=task_id,
            context_id=context_id,
            session_id=session_id,
            content=content,
            skill_id=skill_id,
            is_resume=is_resume,
            files_data=files_data or [],
            message=message,
            metadata=final_metadata,
            user_id=user_id or context_id,
        )
    
    async def create_task(self, params: PreparedTaskParams) -> None:
        """
        Создаёт задачу в TaskIQ worker.
        
        Кикает process_agent_task в очередь Redis.
        События публикуются в Redis Pub/Sub и доступны через EventSubscriber.
        """
        if self.context is None:
            raise ValueError("Context is not set. Context must be created in middleware.")
        
        context_data = self.context.to_dict()
        
        # Создаем trace context для propagation в worker
        trace_context_data = None
        if is_tracing_enabled():
            tracer = get_tracer()
            trace_ctx = tracer.create_trace_context(
                user_id=self.context.user.user_id if self.context.user else None,
                user_name=self.context.user.name if self.context.user else None,
                user_groups=self.context.metadata.get("grps", []) if self.context.metadata else [],
                session_auth=self.context.session_id,
                session_agent=params.session_id,
                task_id=params.task_id,
                context_id=params.context_id,
                agent_id=self.agent_id,
                skill_id=params.skill_id,
                channel=self.name,
                is_resume=params.is_resume,
            )
            trace_context_data = trace_ctx.to_dict()
        
        from apps.agents.src.tasks.agent_tasks import process_agent_task
        from core.config import get_settings
        
        broker_url = get_settings().tasks.broker_url
        logger.info(f"[create_task] 🔧 TaskIQ broker URL: {broker_url}")
        logger.debug(f"[create_task] Kicking task_id={params.task_id} for agent={self.agent_id}")
        await process_agent_task.kiq(
            agent_id=self.agent_id,
            session_id=params.session_id,
            user_id=params.user_id,
            content=params.content,
            skill_id=params.skill_id,
            channel=self.name,
            task_id=params.task_id,
            context_id=params.context_id,
            metadata=params.metadata or {},
            is_resume=params.is_resume,
            files=params.files_data,
            context_data=context_data,
            trace_context=trace_context_data,
        )
        logger.debug(f"[create_task] Task kicked to TaskIQ: task_id={params.task_id}")
    
    # === Основной метод выполнения задачи ===
    
    async def process_task(self, params: PreparedTaskParams) -> Dict[str, Any]:
        """
        Обрабатывает запрос через агента.
        
        STREAM-FIRST: Все события публикуются в Redis Pub/Sub через Emitter.
        API подписывается на канал и стримит события клиенту.
        
        Returns:
            Результат выполнения
        """
        container = get_container()
        
        # Context должен быть установлен в middleware и передан через context_data
        # Обновляем только специфичные для задачи поля
        self.context.session_id = params.session_id
        self.context.channel = self.name
        self.context.agent_id = self.agent_id
        if params.metadata:
            self.context.metadata = {**self.context.metadata, **params.metadata}
        
        # Устанавливаем в ContextVar для доступа из других компонентов
        set_context(self.context)
        
        # Загружаем state для определения task_id и resume
        container = get_container()
        state_dict = await container.state_manager.get_state(params.session_id)
        
        saved_task_id = None
        if state_dict:
            interrupt_data = state_dict.get("interrupt")
            if interrupt_data and isinstance(interrupt_data, dict):
                context = interrupt_data.get("context")
                if context and isinstance(context, dict):
                    saved_task_id = context.get("task_id")
        effective_task_id = saved_task_id or params.task_id
        
        logger.debug(f"[process_task] Starting task_id={effective_task_id} (from params: {params.task_id})")
        
        # Получаем breakpoints из metadata
        breakpoints = {}
        if params.metadata and "breakpoints" in params.metadata:
            breakpoints = params.metadata["breakpoints"]
        
        exec_state = ExecutionState(
            task_id=effective_task_id,
            context_id=params.context_id,
            user_id=params.user_id,
            user_groups=self._get_user_groups_from_context(self.context),
            session_id=params.session_id,
            skill_id=params.skill_id,
            breakpoints=breakpoints,
        )
        emitter = Emitter(container.redis_client, exec_state)
        
        logger.debug(f"[process_task] Emitter created for stream:{effective_task_id}")
        
        try:
            agent = await container.agent_factory.get_flow(self.agent_id, params.skill_id)
            if agent is None:
                await emitter.emit_error(f"Agent не найден: {self.agent_id}")
                raise ValueError(f"Agent не найден: {self.agent_id}")
            
            # Переопределяем variables из metadata если переданы
            request_variables = params.metadata.get("variables") if params.metadata else None
            if request_variables:
                # Извлекаем значения из переданных variables
                override_vars = {}
                for key, value in request_variables.items():
                    if isinstance(value, dict) and "value" in value:
                        override_vars[key] = value["value"]
                    else:
                        override_vars[key] = value
                
                # Резолвим @var:key ссылки в переопределенных переменных
                # VariablesService.resolve() рекурсивно резолвит словарь
                resolved_override_vars = await container.variables_service.resolve(override_vars)
                # Извлекаем значения если они были в AgentVariableConfig формате
                final_override_vars = {}
                for key, value in resolved_override_vars.items():
                    if isinstance(value, dict) and "value" in value and ("public" in value or "title" in value or "description" in value):
                        final_override_vars[key] = value["value"]
                    else:
                        final_override_vars[key] = value
                override_vars = final_override_vars
                
                agent.variables = {**agent.variables, **override_vars}
            
            user_id = self.context.user.user_id if self.context.user else params.user_id
            user_groups = self.context.metadata.get("grps", []) or []
            
            # Загружаем state из state_dict
            state = ExecutionState.model_validate(state_dict) if state_dict else None
            
            if state is None:
                state = create_initial_state(
                    task_id=effective_task_id,
                    context_id=params.context_id,
                    user_id=user_id,
                    session_id=params.session_id,
                    content=params.content,
                    skill_id=params.skill_id,
                )
                logger.info(f"[state] Created new state for session {params.session_id}")
            else:
                messages_count = len(state.messages)
                logger.info(
                    f"[state] Loaded state for session {params.session_id}: "
                    f"messages={messages_count}, current_nodes={state.current_nodes}, "
                    f"interrupt={bool(state.interrupt)}, breakpoint_hit={state.breakpoint_hit}"
                )
                # При breakpoint resume НЕ перезаписываем content - используем оригинальный
                if not state.breakpoint_hit:
                    state.content = params.content
                state.task_id = effective_task_id
                state.context_id = params.context_id
                state.session_id = params.session_id
            
            state.user_id = user_id
            state.user_groups = user_groups
            
            if params.files_data:
                state.files = list(state.files) + params.files_data
            
            state.variables = {**state.variables, **agent.variables}
            
            # Обновляем breakpoints из metadata (для отладки)
            if breakpoints:
                state.breakpoints = breakpoints
            
            # Резолвим mock конфиг из всех уровней иерархии
            agent_config = await container.agent_repository.get(self.agent_id)
            agent_mock = agent_config.mock if agent_config else None
            
            skill_mock = None
            if agent_config and agent_config.skills and params.skill_id in agent_config.skills:
                skill_config = agent_config.skills[params.skill_id]
                skill_mock = skill_config.mock
            
            request_mock = params.metadata.get("mock") if params.metadata else None
            
            # Проверка прав на использование mock через request metadata
            if request_mock:
                config = get_settings()
                global_mock = config.mock.model_dump() if config.mock else None
                mock_config = resolve_mock_config(global_mock, agent_mock, skill_mock, request_mock)
                
                if not check_mock_permission(user_groups, mock_config):
                    logger.warning(f"Mock access denied for user {user_id}")
                    request_mock = None
            
            # Резолвим итоговый mock конфиг
            config = get_settings()
            global_mock = config.mock.model_dump() if config.mock else None
            mock_config = resolve_mock_config(global_mock, agent_mock, skill_mock, request_mock)
            
            if mock_config.enabled:
                state.mock = mock_config.model_dump(exclude_none=False)
                logger.info(f"[mock] Mock enabled for session {params.session_id}")
            
            entry_node = agent.nodes.get(agent.entry)
            node_type = entry_node.config.get("type", "") if entry_node else ""
            
            final_response = ""
            
            ReactNode = get_container().react_node_class
            if node_type == NodeType.REACT_NODE.value and isinstance(entry_node, ReactNode):
                if entry_node.tool_refs and entry_node._loaded_tools is None:
                    entry_node._loaded_tools = await entry_node._load_tools()
                
                runner = await entry_node.get_runner()
                
                trace_ctx = None
                if is_tracing_enabled():
                    trace_ctx_data = get_current_trace_context()
                    if trace_ctx_data:
                        trace_ctx = TraceContext.from_dict(trace_ctx_data)
                
                tracer = get_tracer()
                
                try:
                    async with tracer.flow_span(self.agent_id, agent.entry, trace_ctx):
                        async with tracer.node_span(agent.entry, "react_node", trace_ctx):
                            async for event in runner.run({"content": params.content}, state):
                                await emitter.emit(event)
                    
                    final_response = state.response or ""
                    
                    state.current_nodes = []
                    state.interrupt = None
                    
                    json_data = extract_json_from_response(final_response)
                    has_artifact = json_data is not None
                    if has_artifact:
                        await emitter.emit_artifact(json.dumps(json_data, ensure_ascii=False))
                    
                    await emitter.emit_complete(final_response, has_artifact=has_artifact)
                    
                    await self._save_state(params.session_id, state)
                    
                    await self._send_push_notification(
                        params.task_id, params.context_id, "completed", final_response
                    )
                    
                except AgentInterrupt as e:
                    state.interrupt = InterruptData(
                        question=e.question,
                        context={"task_id": state.task_id}
                    )
                    state.current_nodes = [agent.entry]
                    await emitter.emit_interrupt(e.question)
                    final_response = e.question
                    
                    await self._save_state(params.session_id, state)
                    
                    await self._send_push_notification(
                        params.task_id, params.context_id, "input-required", e.question
                    )
            else:
                if params.is_resume and state.interrupt:
                    # Resume после interrupt (ask_user)
                    state = await agent.resume(state, answer=params.content)
                elif params.is_resume and state.breakpoint_hit:
                    # Continue после breakpoint - просто execute с текущим state
                    # breakpoint_hit остаётся, agent._check_breakpoint увидит и пропустит проверку
                    state = await agent.execute(state)
                else:
                    state = await agent.execute(state)
                
                final_response = state.response or ""
                
                if state.breakpoint_hit:
                    # Breakpoint сработал - выполнение остановлено
                    node_id = state.breakpoint_hit
                    logger.info(f"Breakpoint hit at node '{node_id}'")
                    
                    # Эмитим событие breakpoint для stream (A2A)
                    node_type = agent.nodes.get(node_id).config.get("type", "unknown") if agent.nodes.get(node_id) else "unknown"
                    await emitter.emit_breakpoint(node_id, node_type, state.breakpoint_state or {})
                    
                    # Сохраняем state с breakpoint данными
                    await self._save_state(params.session_id, state)
                    return {
                        "response": "",
                        "breakpoint_hit": node_id,
                        "breakpoint_state": state.breakpoint_state,
                        "status": "input-required",
                    }
                elif state.interrupt:
                    question = state.interrupt.question
                    await emitter.emit_interrupt(question)
                    await self._send_push_notification(
                        params.task_id, params.context_id, "input-required", question
                    )
                else:
                    json_data = extract_json_from_response(final_response)
                    has_artifact = json_data is not None
                    if has_artifact:
                        await emitter.emit_artifact(json.dumps(json_data, ensure_ascii=False))
                    await emitter.emit_complete(final_response, has_artifact=has_artifact)
                    await self._send_push_notification(
                        params.task_id, params.context_id, "completed", final_response
                    )
            
            messages_count = len(state.messages)

            logger.info(
                f"[state] Saving state for session {params.session_id}: "
                f"messages={messages_count}, current_nodes={state.current_nodes}, "
                f"interrupt={bool(state.interrupt)}"
            )
            await self._save_state(params.session_id, state)
            
            # Сериализация interrupt
            if state.interrupt:
                interrupt_dict = state.interrupt.model_dump()
            else:
                interrupt_dict = None
            
            status = "input-required" if state.interrupt else "completed"
            
            return {
                "response": final_response,
                "interrupt": interrupt_dict,
                "status": status,
            }
            
        except Exception as e:
            logger.error(f"Error in process_task: {e}")
            await emitter.emit_error(str(e))
            await self._send_push_notification(
                params.task_id, params.context_id, "failed", str(e)
            )
            raise
        finally:
            clear_context()
    
    async def _send_push_notification(
        self, task_id: str, context_id: str, state: str, message: str
    ) -> None:
        """Отправляет push notification через TaskIQ."""
        await send_task_update.kiq(task_id, context_id, state, message, True)
    
    # === Общая реализация on_get_task ===
    
    async def _get_task_from_state(self, context_id: str) -> Optional[Task]:
        """
        Получает Task из state.
        
        Общая логика для всех каналов.
        Использует context_id для генерации session_id (для multi-turn сценариев).
        """
        session_id = self._generate_session_id(context_id)
        state = await self._get_state(session_id)
        
        if state is None:
            return None
        
        if state.interrupt:
            task_state = TaskState.input_required
            response = state.interrupt.question
        elif getattr(state, "_cancelled", False):
            task_state = TaskState.canceled
            response = "Task cancelled"
        elif state.response:
            task_state = TaskState.completed
            response = state.response
        else:
            task_state = TaskState.working
            response = ""
        
        messages: List[Message] = list(state.messages)
        
        task_id = state.task_id
        
        return Task(
            id=task_id,
            contextId=context_id,
            status=TaskStatus(state=task_state, message=new_agent_text_message(response)),
            history=messages if messages else None,
        )
    
    async def _cancel_task_in_state(self, task_id: str) -> Optional[Task]:
        """Отменяет Task в state."""
        session_id = self._generate_session_id(task_id)
        state = await self._get_state(session_id)
        
        if state is None:
            return None
        
        setattr(state, "_cancelled", True)
        await self._save_state(session_id, state)
        
        return Task(
            id=task_id,
            contextId=task_id,
            status=TaskStatus(
                state=TaskState.canceled,
                message=new_agent_text_message("Task cancelled"),
            ),
        )
    
    # === Обязательные методы (abstract) ===
    
    @abstractmethod
    async def on_message_send(
        self, params: MessageSendParams, context: Any = None
    ) -> Union[Task, Message]:
        """
        Отправка сообщения (синхронно).
        
        Возвращает Task или Message в зависимости от типа запроса.
        """
        pass
    
    @abstractmethod
    async def on_message_stream(
        self, params: MessageSendParams, context: Any = None
    ) -> AsyncGenerator[Union[Message, Task, TaskStatusUpdateEvent, TaskArtifactUpdateEvent], None]:
        """
        Отправка сообщения (streaming).
        
        Yield'ит события по мере генерации.
        """
        pass
    
    @abstractmethod
    async def on_get_task(
        self, params: TaskQueryParams, context: Any = None
    ) -> Optional[Task]:
        """Получение задачи по ID."""
        pass
    
    @abstractmethod
    async def on_cancel_task(
        self, params: TaskIdParams, context: Any = None
    ) -> Optional[Task]:
        """Отмена задачи."""
        pass
    
    @abstractmethod
    async def on_resubscribe_to_task(
        self, params: TaskIdParams, context: Any = None
    ) -> AsyncGenerator[Union[Message, Task, TaskStatusUpdateEvent, TaskArtifactUpdateEvent], None]:
        """Переподписка на события задачи."""
        pass
    
    # === Опциональные методы (push notifications) ===
    
    async def on_set_task_push_notification_config(
        self, params: TaskPushNotificationConfig, context: Any = None
    ) -> TaskPushNotificationConfig:
        """Установка конфигурации push notification."""
        raise NotImplementedError(f"Channel '{self.name}' does not support push notifications")
    
    async def on_get_task_push_notification_config(
        self, params: Any, context: Any = None
    ) -> Optional[TaskPushNotificationConfig]:
        """Получение конфигурации push notification."""
        raise NotImplementedError(f"Channel '{self.name}' does not support push notifications")
    
    async def on_list_task_push_notification_config(
        self, params: Any, context: Any = None
    ) -> List[TaskPushNotificationConfig]:
        """Список конфигураций push notification."""
        raise NotImplementedError(f"Channel '{self.name}' does not support push notifications")
    
    async def on_delete_task_push_notification_config(
        self, params: Any, context: Any = None
    ) -> None:
        """Удаление конфигурации push notification."""
        raise NotImplementedError(f"Channel '{self.name}' does not support push notifications")
    
    # === Опциональные методы (agent card) ===
    
    async def on_get_authenticated_extended_card(
        self, params: Any, context: Any = None
    ) -> Any:
        """Получение расширенной карточки агента."""
        raise NotImplementedError(f"Channel '{self.name}' does not support extended card")
    
    # === Skills CRUD ===
    
    async def list_skills(self) -> List[Dict[str, Any]]:
        """Получить список skills."""
        container = get_container()
        skills = await container.agent_factory.get_skills(self.agent_id)
        return [
            {
                "id": skill_id,
                "name": skill.name,
                "description": skill.description,
                "tags": skill.tags or [],
            }
            for skill_id, skill in skills.items()
        ]
    
    async def get_skill(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """Получить skill по ID."""
        container = get_container()
        config = await container.agent_repository.get(self.agent_id)
        if config is None:
            return None
        
        skills = await container.agent_factory.get_skills(self.agent_id)
        skill = skills.get(skill_id)
        if skill is None:
            return None
        
        # Формируем skill_body из SkillConfig
        skill_body = {}
        if skill.entry is not None:
            skill_body["entry"] = skill.entry
        if skill.nodes is not None:
            skill_body["nodes"] = skill.nodes
        if skill.edges is not None:
            skill_body["edges"] = [
                {
                    "from": edge.from_node,
                    "to": edge.to_node,
                    "condition": edge.condition,
                }
                for edge in skill.edges
            ]
        if skill.variables:
            skill_body["variables"] = skill.variables
        
        skill_body["nodes_mode"] = skill.nodes_mode
        skill_body["edges_mode"] = skill.edges_mode
        skill_body["variables_mode"] = skill.variables_mode
        
        return {
            "id": skill_id,
            "name": skill.name,
            "description": skill.description,
            "tags": skill.tags or [],
            "permission": skill.permission,
            "skill_body": skill_body,
        }
    
    async def create_skill(self, skill_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Создать новый skill."""
        container = get_container()
        config = await container.agent_repository.get(self.agent_id)
        if config is None:
            raise ValueError(f"Agent '{self.agent_id}' not found")
        
        skills = await container.agent_factory.get_skills(self.agent_id)
        if skill_id in skills:
            raise ValueError(f"Skill '{skill_id}' already exists")
        
        skill_body = data.get("skill_body", {})
        
        # Zero-Guess: валидация неизвестных полей в skill_body
        allowed_skill_body_fields = {
            "entry", "nodes", "nodes_mode", "edges", "edges_mode",
            "variables", "variables_mode", "mock"
        }
        unknown_fields = set(skill_body.keys()) - allowed_skill_body_fields
        if unknown_fields:
            raise ValueError(
                f"Unknown fields in skill_body: {sorted(unknown_fields)}. "
                f"Allowed fields: {sorted(allowed_skill_body_fields)}"
            )
        
        edges = None
        if skill_body.get("edges"):
            edges = []
            for edge in skill_body["edges"]:
                if isinstance(edge, dict):
                    edges.append(
                        Edge(
                            from_node=edge.get("from") or edge.get("from_node"),
                            to_node=edge.get("to") or edge.get("to_node"),
                            condition=edge.get("condition"),
                        )
                    )
                else:
                    edges.append(edge)
        
        skill_config = SkillConfig(
            name=data.get("name", skill_id),
            description=data.get("description", ""),
            tags=data.get("tags", []),
            entry=skill_body.get("entry"),
            nodes=skill_body.get("nodes"),
            edges=edges,
            variables=skill_body.get("variables", {}),
        )
        
        if config.skills is None:
            config.skills = {}
        
        config.skills[skill_id] = skill_config
        
        # Применяем skill к текущему конфигу и валидируем
        effective = container.agent_factory._apply_skill(config, skill_id)
        
        validator = AgentValidator(
            agent_repository=container.agent_repository,
            tool_repository=container.tool_repository,
            node_repository=container.node_repository,
        )
        validation_result = await validator.validate(
            nodes=effective["nodes"],
            edges=[{"from": e.from_node, "to": e.to_node, "condition": e.condition} for e in effective["edges"]],
            entry=effective["entry"],
            variables=effective["variables"],
            agent_id=self.agent_id,
        )
        
        if not validation_result.valid:
            errors = [e.message for e in validation_result.errors if e.severity == ValidationSeverity.ERROR]
            raise ValueError(f"Skill validation failed: {'; '.join(errors)}")
        
        await container.agent_repository.set(config)
        
        logger.info(f"Created skill: {skill_id}")
        
        return {
            "status": "success",
            "message": f"Skill '{skill_id}' created successfully",
            "skill_id": skill_id,
        }
    
    async def update_skill(self, skill_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Обновить существующий skill."""
        container = get_container()
        config = await container.agent_repository.get(self.agent_id)
        if config is None:
            raise ValueError(f"Agent '{self.agent_id}' not found")
        
        skills = await container.agent_factory.get_skills(self.agent_id)
        if skill_id not in skills:
            raise ValueError(f"Skill '{skill_id}' not found")
        
        skill_body = data.get("skill_body", {})
        
        # Zero-Guess: валидация неизвестных полей в skill_body
        allowed_skill_body_fields = {
            "entry", "nodes", "nodes_mode", "edges", "edges_mode",
            "variables", "variables_mode", "mock"
        }
        unknown_fields = set(skill_body.keys()) - allowed_skill_body_fields
        if unknown_fields:
            raise ValueError(
                f"Unknown fields in skill_body: {sorted(unknown_fields)}. "
                f"Allowed fields: {sorted(allowed_skill_body_fields)}"
            )
        
        edges = None
        if skill_body.get("edges"):
            edges = []
            for edge in skill_body["edges"]:
                if isinstance(edge, dict):
                    edges.append(
                        Edge(
                            from_node=edge.get("from") or edge.get("from_node"),
                            to_node=edge.get("to") or edge.get("to_node"),
                            condition=edge.get("condition"),
                        )
                    )
                else:
                    edges.append(edge)
        
        skill_config = SkillConfig(
            name=data.get("name", skill_id),
            description=data.get("description", ""),
            tags=data.get("tags", []),
            entry=skill_body.get("entry"),
            nodes=skill_body.get("nodes"),
            edges=edges,
            variables=skill_body.get("variables", {}),
        )
        
        if config.skills is None:
            config.skills = {}
        
        config.skills[skill_id] = skill_config
        
        # Применяем skill к текущему конфигу и валидируем
        effective = container.agent_factory._apply_skill(config, skill_id)
        
        validator = AgentValidator(
            agent_repository=container.agent_repository,
            tool_repository=container.tool_repository,
            node_repository=container.node_repository,
        )
        validation_result = await validator.validate(
            nodes=effective["nodes"],
            edges=[{"from": e.from_node, "to": e.to_node, "condition": e.condition} for e in effective["edges"]],
            entry=effective["entry"],
            variables=effective["variables"],
            agent_id=self.agent_id,
        )
        
        if not validation_result.valid:
            errors = [e.message for e in validation_result.errors if e.severity == ValidationSeverity.ERROR]
            raise ValueError(f"Skill validation failed: {'; '.join(errors)}")
        
        await container.agent_repository.set(config)
        
        logger.info(f"Updated skill: {skill_id}")
        
        return {
            "status": "success",
            "message": f"Skill '{skill_id}' updated successfully",
            "skill_id": skill_id,
        }
    
    async def delete_skill(self, skill_id: str) -> Dict[str, Any]:
        """Удалить skill."""
        container = get_container()
        config = await container.agent_repository.get(self.agent_id)
        if config is None:
            raise ValueError(f"Agent '{self.agent_id}' not found")
        
        skills = await container.agent_factory.get_skills(self.agent_id)
        if skill_id not in skills:
            raise ValueError(f"Skill '{skill_id}' not found")
        
        if config.skills and skill_id in config.skills:
            del config.skills[skill_id]
            await container.agent_repository.set(config)
            logger.info(f"Deleted skill: {skill_id}")
            return {
                "status": "success",
                "message": f"Skill '{skill_id}' deleted successfully",
                "skill_id": skill_id,
            }
        
        raise ValueError(f"Skill '{skill_id}' not found")
    
    # === Tools ===
    
    async def get_skill_tools(self, skill_id: str) -> List[Dict[str, Any]]:
        """Получить список tools для skill."""
        container = get_container()
        config = await container.agent_repository.get(self.agent_id)
        if config is None:
            return []
        
        effective = container.agent_factory._apply_skill(config, skill_id)
        # Graph flow если есть реальные переходы между нодами (не только to: null)
        real_edges = [
            e for e in effective["edges"]
            if (e.to_node if hasattr(e, "to_node") else e.get("to")) is not None
        ]
        is_graph_flow = len(real_edges) > 0
        
        tools_set = set()
        inline_tools = {}
        
        for node_id, node_config in effective["nodes"].items():
            node_type = node_config.get("type")
            
            # Собираем inline tools из tool nodes
            if node_type == NodeType.TOOL.value:
                if node_config.get("code"):
                    tool_id = node_config.get("tool_id") or node_id
                    inline_tools[tool_id] = {
                        "tool_id": tool_id,
                        "name": node_config.get("name", tool_id),
                        "description": node_config.get("description", ""),
                        "code": node_config.get("code", ""),
                        "args_schema": node_config.get("args_schema", {})
                    }
                elif node_config.get("tool_id"):
                    tools_set.add(node_config["tool_id"])
            
            # Собираем inline tools из react_node nodes
            elif node_type == NodeType.REACT_NODE.value:
                tools_list = node_config.get("tools", [])
                for tool_ref in tools_list:
                    if isinstance(tool_ref, dict) and tool_ref.get("code"):
                        tool_id = tool_ref.get("tool_id", f"inline_{node_id}")
                        inline_tools[tool_id] = tool_ref
                    else:
                        tool_id = (
                            tool_ref.tool_id
                            if hasattr(tool_ref, "tool_id")
                            else (tool_ref.get("tool_id") if isinstance(tool_ref, dict) else str(tool_ref))
                        )
                        tools_set.add(tool_id)
                
                if node_config.get("node_id"):
                    node_db_config = await container.node_repository.get(node_config["node_id"])
                    if node_db_config and node_db_config.tools:
                        for tool_ref in node_db_config.tools:
                            if isinstance(tool_ref, dict) and tool_ref.get("code"):
                                tool_id = tool_ref.get("tool_id", f"inline_{node_id}")
                                inline_tools[tool_id] = tool_ref
                            else:
                                tool_id = (
                                    tool_ref.tool_id
                                    if hasattr(tool_ref, "tool_id")
                                    else (tool_ref.get("tool_id") if isinstance(tool_ref, dict) else str(tool_ref))
                                )
                                tools_set.add(tool_id)
        
        tools_info = []
        
        # Добавляем inline tools
        for tool_id, tool_config in inline_tools.items():
            tools_info.append({
                "name": tool_id,
                "type": "function",
                "attributes": {
                    "description": tool_config.get("description", ""),
                    "code": tool_config.get("code", ""),
                    "args_schema": tool_config.get("args_schema", {}),
                    "source": "inline",
                },
            })
        
        # Добавляем referenced tools
        for tool_id in sorted(tools_set):
            tool_ref = await container.tool_repository.get(tool_id)
            if tool_ref:
                info = tool_ref.to_registry_format()
                tools_info.append({
                    "name": tool_id,
                    "type": "function",
                    "attributes": {
                        "description": info.get("description", ""),
                        "source": "reference",
                        "args_schema": info.get("attributes", {}).get("args_schema", {}),
                    },
                })
            else:
                agent_config = await container.agent_repository.get(tool_id)
                if agent_config:
                    tools_info.append({
                        "name": tool_id,
                        "type": "function",
                        "attributes": {
                            "description": agent_config.description or "",
                            "agent_name": agent_config.name or tool_id,
                            "source": "agent",
                        },
                    })
                else:
                    tools_info.append({
                        "name": tool_id,
                        "type": "function",
                        "attributes": {
                            "description": "",
                            "source": "reference",
                        },
                    })
        
        if is_graph_flow:
            for node_id, node_config in effective["nodes"].items():
                node_type = node_config.get("type", "unknown")
                node_name = node_id
                
                if node_config.get("agent_id"):
                    agent_config = await container.agent_repository.get(node_config["agent_id"])
                    if agent_config:
                        node_name = agent_config.name
                
                description = f"Нода типа '{node_type}'"
                if node_config.get("agent_id"):
                    description = f"Агент: {node_name}"
                elif node_type == NodeType.FUNCTION.value:
                    description = "Function нода"
                elif node_type == NodeType.REACT_NODE.value:
                    description = "ReAct агент"
                
                tools_info.append({
                    "name": node_id,
                    "type": "node",
                    "attributes": {
                        "description": description,
                        "node_type": node_type,
                        "node_name": node_name,
                    },
                })
            
            for edge in effective["edges"]:
                from_node = edge.from_node if hasattr(edge, "from_node") else edge.get("from")
                to_node = edge.to_node if hasattr(edge, "to_node") else edge.get("to")
                condition = edge.condition if hasattr(edge, "condition") else edge.get("condition")
                
                edge_name = f"{from_node} -> {to_node or 'end'}"
                description = f"Переход от '{from_node}' к '{to_node or 'конец'}'"
                if condition:
                    description += f" (условие: {condition})"
                
                tools_info.append({
                    "name": edge_name,
                    "type": "edge",
                    "attributes": {
                        "description": description,
                        "from_node": from_node,
                        "to_node": to_node,
                        "condition": condition,
                    },
                })
        
        return tools_info
    
    # === Schema ===
    
    async def get_skill_schema(self) -> Dict[str, Any]:
        """Получить JSON Schema для создания skill."""
        container = get_container()
        config = await container.agent_repository.get(self.agent_id)
        if config is None:
            raise ValueError(f"Agent '{self.agent_id}' not found")
        
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "title": f"Skill Body - {config.name}",
            "properties": {},
            "required": [],
            "additionalProperties": True,
        }
    
    # === Карточка агента ===
    
    async def get_agent_card(self, base_url: str) -> Dict[str, Any]:
        """Получить Agent Card."""
        container = get_container()
        config = self._agent_config or await container.agent_repository.get(self.agent_id)
        if config is None:
            raise ValueError(f"Agent '{self.agent_id}' not found")
        
        skills = await container.agent_factory.get_skills(self.agent_id)
        
        agent_skills = []
        for skill_id, skill in skills.items():
            agent_skills.append(
                AgentSkill(
                    id=skill_id,
                    name=skill.name,
                    description=skill.description,
                    tags=skill.tags or [],
                    inputModes=["text/plain"],
                    outputModes=["text/plain"],
                )
            )
        
        if not agent_skills:
            agent_skills.append(
                AgentSkill(
                    id="default",
                    name=config.name,
                    description=config.description,
                    tags=config.tags or [],
                    inputModes=["text/plain"],
                    outputModes=["text/plain"],
                )
            )
        
        card = AgentCard(
            name=config.name,
            description=config.description,
            version="1.0.0",
            url=f"{base_url}/agents/api/v1/{config.agent_id}",
            capabilities=AgentCapabilities(
                streaming=True, pushNotifications=False, stateTransitionHistory=True
            ),
            skills=agent_skills,
            defaultInputModes=["text/plain"],
            defaultOutputModes=["text/plain"],
            supportsAuthenticatedExtendedCard=False,
        )
        
        card_dict = card.model_dump(by_alias=True, exclude_none=True)
        
        # Добавляем публичные variables как дополнительное поле (не входит в стандарт A2A)
        public_vars = {}
        flow_variables = config.variables or {}
        for var_name, var_config in flow_variables.items():
            # AgentVariableConfig объект
            if var_config.public:
                var_value = var_config.value
                var_info = {}

                # Добавляем метаданные если есть
                if var_config.title:
                    var_info["title"] = var_config.title
                if var_config.description:
                    var_info["description"] = var_config.description

                # Обрабатываем значение
                if isinstance(var_value, str) and var_value.startswith("@var:"):
                    var_info["type"] = "reference"
                    var_info["key"] = var_value[5:]
                else:
                    var_info["value"] = var_value

                public_vars[var_name] = var_info

        if public_vars:
            card_dict["variables"] = public_vars

        return card_dict
