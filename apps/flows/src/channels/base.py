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
from uuid import UUID

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

from core.auth import permission_checker
from core.auth.errors import PermissionDeniedA2AError
from core.billing.exceptions import BillingBalanceBlockedError
from apps.flows.config import get_settings
from apps.flows.src.container import get_container
from core.context import Context, User, clear_context, get_context, set_context
from core.logging import bind_log_context, get_logger
from core.logging.attributes import LOG_SESSION_AGENT
from apps.flows.src.mock import check_mock_permission, resolve_mock_config
from apps.flows.src.models.flow_config import Edge, FlowConfig, BranchConfig
from apps.flows.src.models.enums import MergeMode, NodeType
from apps.flows.src.services.flow_node_merge import merge_incoming_node_dict_for_persist
from apps.flows.src.services.flow_validator import FlowValidator, ValidationSeverity
from apps.flows.src.state import collect_flow_node_files, create_initial_state
from apps.flows.src.state.cancellation import CancellationToken, FlowCancelled, set_cancellation_token
from apps.flows.src.state.flow_deadline import apply_flow_wall_clock_deadline
from apps.flows.src.state.interrupt_manager import InterruptManager
from apps.flows.src.streaming import Emitter
from core.state import ExecutionState
from core.state.trigger_runtime import TriggerRuntimeSnapshot
from core.state.interrupt import HandoffMode, OperatorTaskInterrupt, interrupt_to_response_dict
from apps.idle_worker.tasks.push_notification_tasks import send_task_update
from core.tracing import get_tracer
from core.tracing.provider import is_tracing_enabled
from apps.flows.src.utils import extract_json_from_response
from apps.flows.src.variables import VariableResolver
from apps.flows.src.channels.request_context_variables import flow_variables_from_request_context

logger = get_logger(__name__)


def effective_stream_task_id_for_session(
    params_task_id: str,
    saved_state: Optional[ExecutionState],
) -> str:
    """
    Task id для Pub/Sub `stream:{id}`: совпадает с тем, что в prepare, если
    state и context те же. Единая точка с `_prepare_task_params`, чтобы
    A2A-подписка и Emitter в воркере ссылались на один канал.
    """
    if saved_state is not None and saved_state.interrupt is not None:
        sid = saved_state.interrupt.system.task_id
        if sid:
            return sid
    return params_task_id


class PermissionDenied(Exception):
    """
    Исключение для отсутствия прав доступа.
    
    Содержит PermissionDeniedA2AError для формирования JSON-RPC ответа.
    """
    
    def __init__(self, error: PermissionDeniedA2AError):
        self.error = error
        super().__init__(error.message)


# PreparedTaskParams вынесен в types.py чтобы избежать циклических импортов
from apps.flows.src.channels.types import PreparedTaskParams


class BaseChannel(ABC):
    """
    Абстрактный базовый класс канала коммуникации.
    
    Определяет интерфейс для всех каналов: A2A, Telegram, WhatsApp и др.
    Содержит основную логику выполнения задач.
    """
    
    name: str  # Имя канала: "a2a", "telegram", "whatsapp"
    
    def __init__(
        self, 
        flow_id: str, 
        context: Optional[Context] = None,
        flow_config: Optional[Any] = None
    ):
        self.flow_id = flow_id
        self.context = context or get_context()
        self._flow_config = flow_config
    
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
        """Генерирует session_id из flow_id и context_id."""
        return f"{self.flow_id}:{context_id}"
    
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

    async def _normalize_request_variables(self, request_variables: Dict[str, Any]) -> Dict[str, Any]:
        """
        Нормализует metadata.variables от клиента перед merge в runtime_flow.variables.

        Контракт:
        - резолвим только верхнеуровневые строковые ссылки "@var:*";
        - вложенные структуры считаем данными UI-контекста и не интерпретируем как переменные.
        """
        normalized: Dict[str, Any] = dict(request_variables)
        if "target_branch_id" not in normalized and "branch_id" in normalized:
            normalized["target_branch_id"] = normalized["branch_id"]

        container = get_container()
        resolved: Dict[str, Any] = {}
        for key, value in normalized.items():
            raw_value = value["value"] if isinstance(value, dict) and "value" in value else value
            if isinstance(raw_value, str) and raw_value.startswith("@var:"):
                resolved[key] = await container.variables_service.resolve(raw_value)
            else:
                resolved[key] = raw_value
        return resolved
    
    async def check_permissions(
        self,
        user_groups: List[str],
        branch_id: str = "default",
    ) -> None:
        """
        Проверяет permissions на агента и ветку (branch).

        Args:
            user_groups: группы пользователя из JWT (grps claim)
            branch_id: ID ветки

        Raises:
            PermissionDenied: если нет доступа к агенту или ветке
        """
        config = get_settings()
        
        # Если проверка permissions отключена - пропускаем
        if not config.auth.permissions_enabled:
            return
        
        container = get_container()
        flow_config = await container.flow_repository.get(self.flow_id)
        
        if flow_config is None:
            return
        
        # Проверка permission на агента
        if not permission_checker.check_flow_permission(user_groups, flow_config.permission):
            required = permission_checker.normalize(flow_config.permission)
            raise PermissionDenied(
                PermissionDeniedA2AError.for_flow(self.flow_id, required)
            )
        
        # Проверка permission на ветку графа
        branch_config = None
        if flow_config.branches and branch_id in flow_config.branches:
            branch_config = flow_config.branches[branch_id]

        if branch_config is not None:
            if not permission_checker.check_branch_permission(
                user_groups, branch_config.permission, flow_config.permission
            ):
                effective_perm = branch_config.permission if branch_config.permission else flow_config.permission
                required = permission_checker.normalize(effective_perm)
                raise PermissionDenied(
                    PermissionDeniedA2AError.for_branch(branch_id, self.flow_id, required)
                )
    
    async def _get_state(self, session_id: str) -> Optional[ExecutionState]:
        """Получает state из StateManager."""
        container = get_container()
        return await container.state_manager.get_state(session_id)
    
    async def _save_state(self, session_id: str, state: ExecutionState) -> None:
        """Сохраняет state в StateManager."""
        container = get_container()
        await container.state_manager.save_state(session_id, state)

    async def _resolve_active_takeover_task(self, correlation_id: "UUID") -> Optional[str]:
        """Проверяет, есть ли активная (CLAIMED/USER_DIALOG) задача оператора по correlation_id.

        Возвращает operator_task_id или None (задача уже завершена / не найдена).
        """
        from apps.flows.src.models.operator_schemas import OperatorTaskStatus

        container = get_container()
        ctx = get_context()
        if ctx is None or ctx.active_company is None:
            return None
        company_id = ctx.active_company.company_id
        task = await container.operator_repository.get_task_by_correlation(
            company_id, str(correlation_id)
        )
        if task is None:
            return None
        if task.status not in (
            OperatorTaskStatus.CLAIMED.value,
            OperatorTaskStatus.USER_DIALOG.value,
        ):
            return None
        return task.id

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
        
        is_takeover_user_reply = False
        takeover_operator_task_id: str | None = None

        if state is None:
            branch_id = "default"
            if metadata:
                b = metadata.get("branch")
                if b is not None and str(b).strip():
                    branch_id = str(b).strip()
                else:
                    sk = metadata.get("skill")
                    if sk is not None and str(sk).strip():
                        branch_id = str(sk).strip()
            is_resume = False
        else:
            branch_id = state.branch_id
            # Resume если есть interrupt ИЛИ breakpoint_hit
            is_resume = bool(state.interrupt) or bool(state.breakpoint_hit)
            task_id = effective_stream_task_id_for_session(task_id, state)

            # A2A input-required follow-up: при активном takeover
            # реплика пользователя маршрутизируется в dialog_log,
            # flow НЕ возобновляется до complete_handoff оператором.
            if state.interrupt is not None:
                if (
                    isinstance(state.interrupt.body, OperatorTaskInterrupt)
                    and state.interrupt.body.handoff_mode == HandoffMode.TAKEOVER
                    and state.interrupt.correlation_id is not None
                ):
                    op_task = await self._resolve_active_takeover_task(
                        state.interrupt.correlation_id
                    )
                    if op_task is not None:
                        is_takeover_user_reply = True
                        takeover_operator_task_id = op_task
        
        # Объединяем metadata из Context канала с переданным metadata
        final_metadata = metadata or {}
        if self.context and self.context.metadata:
            final_metadata = {**self.context.metadata, **final_metadata}
        
        return PreparedTaskParams(
            task_id=task_id,
            context_id=context_id,
            session_id=session_id,
            content=content,
            branch_id=branch_id,
            is_resume=is_resume,
            files_data=files_data or [],
            message=message,
            metadata=final_metadata,
            user_id=user_id or context_id,
            is_takeover_user_reply=is_takeover_user_reply,
            takeover_operator_task_id=takeover_operator_task_id,
        )
    
    async def create_task(self, params: PreparedTaskParams) -> None:
        """
        Создаёт задачу в TaskIQ worker.
        
        Кикает process_flow_task в очередь Redis.
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
                flow_id=self.flow_id,
                branch_id=params.branch_id,
                channel=self.name,
                is_resume=params.is_resume,
            )
            trace_context_data = trace_ctx.to_dict()
        
        from apps.flows.src.tasks.flow_tasks import process_flow_task
        from core.config import get_settings
        
        broker_url = get_settings().tasks.broker_url
        logger.info("flow.create_task.broker", broker_url=broker_url)
        logger.debug(f"[create_task] Kicking task_id={params.task_id} for flow_id={self.flow_id}")
        await process_flow_task.kiq(
            flow_id=self.flow_id,
            session_id=params.session_id,
            user_id=params.user_id,
            content=params.content,
            branch_id=params.branch_id,
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
    
    async def _run_trigger_output_actions_if_applicable(
        self,
        params: PreparedTaskParams,
        state: ExecutionState,
        flow_config: Optional[FlowConfig],
    ) -> None:
        if not params.metadata:
            return
        trigger_id = params.metadata.get("trigger_id")
        if not trigger_id or not isinstance(trigger_id, str):
            return
        cfg = flow_config
        if cfg is None:
            cfg = await get_container().flow_repository.get(self.flow_id)
        if cfg is None:
            return
        trigger = cfg.triggers.get(trigger_id)
        if trigger is None:
            return
        from apps.flows.src.triggers.executor import OutputActionExecutor
        from apps.flows.src.triggers.trigger_type_contract import (
            effective_output_actions_for_trigger,
        )

        actions = effective_output_actions_for_trigger(trigger)
        if not actions:
            return
        triggers_meta = params.metadata.get("triggers")
        original_payload: Dict[str, Any] = {}
        if isinstance(triggers_meta, dict):
            raw = triggers_meta.get(trigger_id)
            if isinstance(raw, dict):
                pl = raw.get("payload")
                if isinstance(pl, dict):
                    original_payload = pl
                else:
                    msg = "metadata.triggers[trigger_id] must contain 'payload' as dict"
                    raise ValueError(msg)
        state_dict = state.model_dump(mode="json")
        executor = OutputActionExecutor()
        await executor.execute(
            output_actions=actions,
            state=state_dict,
            trigger_config=trigger.config,
            original_payload=original_payload,
        )
    
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
        self.context.flow_id = self.flow_id
        if params.metadata:
            self.context.metadata = {**self.context.metadata, **params.metadata}
        
        # Устанавливаем в ContextVar для доступа из других компонентов
        set_context(self.context)
        bind_log_context(**{LOG_SESSION_AGENT: params.session_id})

        # Загружаем state для определения task_id, resume и закреплённой версии flow
        container = get_container()
        saved_state = await container.state_manager.get_state(params.session_id)
        
        effective_task_id = effective_stream_task_id_for_session(params.task_id, saved_state)
        
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
            branch_id=params.branch_id,
            breakpoints=breakpoints,
        )
        emitter = Emitter(container.redis_client, exec_state)
        
        logger.debug(f"[process_task] Emitter created for stream:{effective_task_id}")
        
        try:
            pinned_version = saved_state.flow_config_version if saved_state else None
            try:
                runtime_flow = await container.flow_factory.get_flow(
                    self.flow_id, params.branch_id, config_version=pinned_version
                )
            except ValueError as verr:
                await emitter.emit_error(str(verr))
                raise
            if runtime_flow is None:
                await emitter.emit_error(f"Flow не найден: {self.flow_id}")
                raise ValueError(f"Flow не найден: {self.flow_id}")
            
            # Переопределяем variables из metadata если переданы
            request_variables = params.metadata.get("variables") if params.metadata else None
            if request_variables:
                resolved_override_vars = await self._normalize_request_variables(request_variables)
                # Извлекаем значения если они были в FlowVariableConfig формате
                final_override_vars = {}
                for key, value in resolved_override_vars.items():
                    if isinstance(value, dict) and "value" in value and ("public" in value or "title" in value or "description" in value):
                        final_override_vars[key] = value["value"]
                    else:
                        final_override_vars[key] = value
                override_vars = final_override_vars
                
                runtime_flow.variables = {**runtime_flow.variables, **override_vars}

            identity_vars = flow_variables_from_request_context(self.context)
            if identity_vars:
                runtime_flow.variables = {**runtime_flow.variables, **identity_vars}

            user_id = self.context.user.user_id if self.context.user else params.user_id
            user_groups = self.context.metadata.get("grps", []) or []
            
            state = saved_state
            
            if state is None:
                state = create_initial_state(
                    task_id=effective_task_id,
                    context_id=params.context_id,
                    user_id=user_id,
                    session_id=params.session_id,
                    content=params.content,
                    branch_id=params.branch_id,
                )
                cfg_nodes = (runtime_flow.config or {}).get("nodes") or {}
                state.files = collect_flow_node_files(cfg_nodes)
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
            
            state.variables = {**state.variables, **runtime_flow.variables}
            
            request_triggers = params.metadata.get("triggers") if params.metadata else None
            if request_triggers:
                merged: Dict[str, TriggerRuntimeSnapshot] = dict(state.triggers)
                for tid, snap in request_triggers.items():
                    if isinstance(snap, TriggerRuntimeSnapshot):
                        merged[tid] = snap
                    elif isinstance(snap, dict):
                        merged[tid] = TriggerRuntimeSnapshot.model_validate(snap)
                    else:
                        msg = f"metadata.triggers[{tid!r}] must be dict or TriggerRuntimeSnapshot"
                        raise TypeError(msg)
                state.triggers = merged
            
            cfg_ver = (runtime_flow.config or {}).get("version")
            if cfg_ver and not state.flow_config_version:
                state.flow_config_version = str(cfg_ver)
            
            # Обновляем breakpoints из metadata (для отладки)
            if breakpoints:
                state.breakpoints = breakpoints
            
            # Резолвим mock конфиг из всех уровней иерархии
            flow_config = await container.flow_factory.get_flow_config_snapshot(
                self.flow_id, state.flow_config_version
            )
            root_flow_mock = flow_config.mock if flow_config else None
            
            branch_mock = None
            if flow_config and flow_config.branches and params.branch_id in flow_config.branches:
                branch_cfg_snapshot = flow_config.branches[params.branch_id]
                branch_mock = branch_cfg_snapshot.mock
            
            request_mock = params.metadata.get("mock") if params.metadata else None
            
            # Проверка прав на использование mock через request metadata
            if request_mock:
                config = get_settings()
                global_mock = config.mock.model_dump() if config.mock else None
                mock_config = resolve_mock_config(global_mock, root_flow_mock, branch_mock, request_mock)
                
                if not check_mock_permission(user_groups, mock_config):
                    logger.warning(f"Mock access denied for user {user_id}")
                    request_mock = None
            
            # Резолвим итоговый mock конфиг
            config = get_settings()
            global_mock = config.mock.model_dump() if config.mock else None
            mock_config = resolve_mock_config(global_mock, root_flow_mock, branch_mock, request_mock)
            
            if mock_config.enabled:
                state.mock = mock_config.model_dump(exclude_none=False)
                logger.info(f"[mock] Mock enabled for session {params.session_id}")
            
            final_response = ""

            if params.is_resume and state.interrupt:
                state.content = params.content

            if flow_config is not None and flow_config.timeout is not None:
                _flow_t = int(flow_config.timeout)
            else:
                _flow_t = int(get_settings().default_flow_timeout_seconds)
            apply_flow_wall_clock_deadline(state, _flow_t)

            logger.info(
                "flow.process_task.state_checkpoint_before_run",
                session_id=params.session_id,
                messages_count=len(state.messages),
            )
            await self._save_state(params.session_id, state)

            cancellation_token = CancellationToken(effective_task_id, container.redis_client)
            set_cancellation_token(cancellation_token)

            try:
                state = await runtime_flow.run(state)
            except FlowCancelled:
                logger.info(f"Flow cancelled: task_id={effective_task_id}")
                await emitter.emit_cancelled()
                return {"response": "", "status": "canceled"}
            finally:
                await cancellation_token.cleanup()
                set_cancellation_token(None)

            final_response = state.response or ""

            if state.breakpoint_hit:
                node_id = state.breakpoint_hit
                logger.info(f"Breakpoint hit at node '{node_id}'")

                node_type = (
                    runtime_flow.nodes.get(node_id).config.get("type", "unknown")
                    if runtime_flow.nodes.get(node_id)
                    else "unknown"
                )
                await emitter.emit_breakpoint(node_id, node_type, state.breakpoint_state or {})

                await self._save_state(params.session_id, state)
                return {
                    "response": "",
                    "breakpoint_hit": node_id,
                    "breakpoint_state": state.breakpoint_state,
                    "status": "input-required",
                }
            if state.interrupt:
                InterruptManager.enrich_system_from_channel(
                    state,
                    context_id=params.context_id,
                    task_id=effective_task_id,
                )
                await emitter.emit_interrupt(state.interrupt)
                await self._send_push_notification(
                    params.task_id,
                    params.context_id,
                    "input-required",
                    state.interrupt.question,
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
                await self._run_trigger_output_actions_if_applicable(
                    params, state, flow_config
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
                interrupt_dict = interrupt_to_response_dict(state.interrupt)
            else:
                interrupt_dict = None
            
            status = "input-required" if state.interrupt else "completed"

            return {
                "response": final_response,
                "interrupt": interrupt_dict,
                "status": status,
            }

        except BillingBalanceBlockedError as e:
            logger.error(f"Billing balance blocked: {e}")
            await emitter.emit_error(str(e))
            await self._send_push_notification(
                params.task_id, params.context_id, "failed", str(e)
            )
            raise

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
    
    # === Опциональные методы (A2A agent-card) ===
    
    async def on_get_authenticated_extended_card(
        self, params: Any, context: Any = None
    ) -> Any:
        """Получение расширенной карточки агента."""
        raise NotImplementedError(f"Channel '{self.name}' does not support extended card")
    
    # === Branches CRUD ===

    async def list_branches(self) -> List[Dict[str, Any]]:
        """Получить список веток (branches)."""
        container = get_container()
        branches_map = await container.flow_factory.get_branches(self.flow_id)
        return [
            {
                "id": branch_id,
                "name": branch_cfg.name,
                "description": branch_cfg.description,
                "tags": branch_cfg.tags or [],
            }
            for branch_id, branch_cfg in branches_map.items()
        ]

    async def get_branch(self, branch_id: str) -> Optional[Dict[str, Any]]:
        """Получить ветку по ID."""
        container = get_container()
        config = await container.flow_repository.get(self.flow_id)
        if config is None:
            return None

        branches_map = await container.flow_factory.get_branches(self.flow_id)
        branch_cfg = branches_map.get(branch_id)
        if branch_cfg is None:
            return None

        # Формируем branch_body из BranchConfig
        branch_body = {}
        if branch_cfg.entry is not None:
            branch_body["entry"] = branch_cfg.entry
        if branch_cfg.nodes is not None:
            branch_body["nodes"] = branch_cfg.nodes
        if branch_cfg.edges is not None:
            branch_body["edges"] = [
                {
                    "from": edge.from_node,
                    "to": edge.to_node,
                    "condition": edge.condition,
                }
                for edge in branch_cfg.edges
            ]
        if branch_cfg.variables:
            branch_body["variables"] = branch_cfg.variables

        branch_body["nodes_mode"] = branch_cfg.nodes_mode
        branch_body["edges_mode"] = branch_cfg.edges_mode
        branch_body["variables_mode"] = branch_cfg.variables_mode

        return {
            "id": branch_id,
            "name": branch_cfg.name,
            "description": branch_cfg.description,
            "tags": branch_cfg.tags or [],
            "permission": branch_cfg.permission,
            "branch_body": branch_body,
        }
    
    async def create_branch(self, branch_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Создать новую ветку (branch)."""
        container = get_container()
        config = await container.flow_repository.get(self.flow_id)
        if config is None:
            raise ValueError(f"Flow '{self.flow_id}' not found")

        if config.branches and branch_id in config.branches:
            raise ValueError(f"Ветка '{branch_id}' уже существует")
        
        branch_body = data.get("branch_body", {})
        
        # Zero-Guess: валидация неизвестных полей в branch_body
        allowed_branch_body_fields = {
            "entry", "nodes", "nodes_mode", "edges", "edges_mode",
            "variables", "variables_mode", "mock"
        }
        unknown_fields = set(branch_body.keys()) - allowed_branch_body_fields
        if unknown_fields:
            raise ValueError(
                f"Unknown fields in branch_body: {sorted(unknown_fields)}. "
                f"Allowed fields: {sorted(allowed_branch_body_fields)}"
            )
        
        edges = None
        if branch_body.get("edges"):
            edges = []
            for edge in branch_body["edges"]:
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
        
        branch_kwargs: dict[str, Any] = {
            "name": data.get("name", branch_id),
            "description": data.get("description", ""),
            "tags": data.get("tags", []),
            "entry": branch_body.get("entry"),
            "nodes": branch_body.get("nodes"),
            "edges": edges,
            "variables": branch_body.get("variables", {}),
        }
        if "nodes_mode" in branch_body:
            branch_kwargs["nodes_mode"] = MergeMode(branch_body["nodes_mode"])
        if "edges_mode" in branch_body:
            branch_kwargs["edges_mode"] = MergeMode(branch_body["edges_mode"])
        if "variables_mode" in branch_body:
            branch_kwargs["variables_mode"] = MergeMode(branch_body["variables_mode"])

        new_branch_cfg = BranchConfig(**branch_kwargs)
        
        if config.branches is None:
            config.branches = {}
        
        config.branches[branch_id] = new_branch_cfg
        
        # Применяем ветку к текущему конфигу и валидируем
        effective = container.flow_factory._apply_branch(config, branch_id)
        
        validator = FlowValidator(
            flow_repository=container.flow_repository,
            tool_repository=container.tool_repository,
            node_repository=container.node_repository,
        )
        validation_result = await validator.validate(
            nodes=effective["nodes"],
            edges=[{"from": e.from_node, "to": e.to_node, "condition": e.condition} for e in effective["edges"]],
            entry=effective["entry"],
            variables=effective["variables"],
            flow_id=self.flow_id,
        )
        
        if not validation_result.valid:
            errors = [e.message for e in validation_result.errors if e.severity == ValidationSeverity.ERROR]
            raise ValueError(f"Ошибка валидации ветки: {'; '.join(errors)}")
        
        await container.flow_repository.set(config)
        
        logger.info(f"Создана ветка: {branch_id}")
        
        return {
            "status": "success",
            "message": f"Ветка '{branch_id}' создана",
            "branch_id": branch_id,
        }
    
    async def update_branch(self, branch_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Обновить существующую ветку (branch)."""
        container = get_container()
        config = await container.flow_repository.get(self.flow_id)
        if config is None:
            raise ValueError(f"Flow '{self.flow_id}' not found")

        if not config.branches or branch_id not in config.branches:
            raise ValueError(f"Ветка '{branch_id}' не найдена")
        
        branch_body = data.get("branch_body", {})
        
        # Zero-Guess: валидация неизвестных полей в branch_body
        allowed_branch_body_fields = {
            "entry", "nodes", "nodes_mode", "edges", "edges_mode",
            "variables", "variables_mode", "mock"
        }
        unknown_fields = set(branch_body.keys()) - allowed_branch_body_fields
        if unknown_fields:
            raise ValueError(
                f"Unknown fields in branch_body: {sorted(unknown_fields)}. "
                f"Allowed fields: {sorted(allowed_branch_body_fields)}"
            )
        
        edges = None
        if branch_body.get("edges"):
            edges = []
            for edge in branch_body["edges"]:
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
        
        existing_branch = config.branches.get(branch_id) if config.branches else None
        nodes_mode = MergeMode(
            branch_body["nodes_mode"]
            if "nodes_mode" in branch_body
            else (existing_branch.nodes_mode if existing_branch else "merge")
        )
        edges_mode = MergeMode(
            branch_body["edges_mode"]
            if "edges_mode" in branch_body
            else (existing_branch.edges_mode if existing_branch else "merge")
        )
        variables_mode = MergeMode(
            branch_body["variables_mode"]
            if "variables_mode" in branch_body
            else (existing_branch.variables_mode if existing_branch else "merge")
        )

        raw_branch_nodes = branch_body.get("nodes")
        if raw_branch_nodes is not None and isinstance(raw_branch_nodes, dict):
            prev_branch_nodes = (existing_branch.nodes or {}) if existing_branch else {}
            merged_branch_nodes = merge_incoming_node_dict_for_persist(
                dict(raw_branch_nodes), prev_branch_nodes
            )
        else:
            merged_branch_nodes = raw_branch_nodes

        updated_branch_cfg = BranchConfig(
            name=data.get("name", branch_id),
            description=data.get("description", ""),
            tags=data.get("tags", []),
            entry=branch_body.get("entry"),
            nodes=merged_branch_nodes,
            nodes_mode=nodes_mode,
            edges=edges,
            edges_mode=edges_mode,
            variables=branch_body.get("variables", {}),
            variables_mode=variables_mode,
        )
        
        if config.branches is None:
            config.branches = {}
        
        config.branches[branch_id] = updated_branch_cfg
        
        # Применяем ветку к текущему конфигу и валидируем
        effective = container.flow_factory._apply_branch(config, branch_id)
        
        validator = FlowValidator(
            flow_repository=container.flow_repository,
            tool_repository=container.tool_repository,
            node_repository=container.node_repository,
        )
        validation_result = await validator.validate(
            nodes=effective["nodes"],
            edges=[{"from": e.from_node, "to": e.to_node, "condition": e.condition} for e in effective["edges"]],
            entry=effective["entry"],
            variables=effective["variables"],
            flow_id=self.flow_id,
        )
        
        if not validation_result.valid:
            errors = [e.message for e in validation_result.errors if e.severity == ValidationSeverity.ERROR]
            raise ValueError(f"Ошибка валидации ветки: {'; '.join(errors)}")
        
        await container.flow_repository.set(config)
        
        logger.info(f"Обновлена ветка: {branch_id}")
        
        return {
            "status": "success",
            "message": f"Ветка '{branch_id}' обновлена",
            "branch_id": branch_id,
        }
    
    async def delete_branch(self, branch_id: str) -> Dict[str, Any]:
        """Удалить ветку (branch)."""
        container = get_container()
        config = await container.flow_repository.get(self.flow_id)
        if config is None:
            raise ValueError(f"Flow '{self.flow_id}' not found")

        if not config.branches or branch_id not in config.branches:
            raise ValueError(f"Ветка '{branch_id}' не найдена")

        del config.branches[branch_id]
        await container.flow_repository.set(config)
        logger.info(f"Удалена ветка: {branch_id}")
        return {
            "status": "success",
            "message": f"Ветка '{branch_id}' удалена",
            "branch_id": branch_id,
        }
    
    # === Tools ===
    
    async def get_branch_tools(self, branch_id: str) -> List[Dict[str, Any]]:
        """Получить список tools для ветки."""
        container = get_container()
        config = await container.flow_repository.get(self.flow_id)
        if config is None:
            return []
        
        effective = container.flow_factory._apply_branch(config, branch_id)
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
            
            # Собираем inline tools из code nodes
            if node_type == NodeType.CODE.value:
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
            
            # Собираем inline tools из llm_node nodes
            elif node_type == NodeType.LLM_NODE.value:
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
            inline_attrs: dict = {
                "description": tool_config.get("description", ""),
                "code": tool_config.get("code", ""),
                "args_schema": tool_config.get("args_schema", {}),
                "source": "inline",
            }
            ps = tool_config.get("parameters_schema")
            if ps:
                inline_attrs["parameters_schema"] = ps
            tools_info.append(
                {
                    "name": tool_id,
                    "type": "function",
                    "attributes": inline_attrs,
                }
            )
        
        # Добавляем referenced tools
        for tool_id in sorted(tools_set):
            tool_ref = await container.tool_repository.get(tool_id)
            if tool_ref:
                info = tool_ref.to_registry_format()
                ref_attrs = info.get("attributes", {})
                ref_payload: dict = {
                    "description": ref_attrs.get("description", ""),
                    "source": "reference",
                    "args_schema": ref_attrs.get("args_schema", {}),
                }
                if ref_attrs.get("parameters_schema"):
                    ref_payload["parameters_schema"] = ref_attrs["parameters_schema"]
                tools_info.append(
                    {
                        "name": tool_id,
                        "type": "function",
                        "attributes": ref_payload,
                    }
                )
            else:
                flow_config = await container.flow_repository.get(tool_id)
                if flow_config:
                    tools_info.append({
                        "name": tool_id,
                        "type": "function",
                        "attributes": {
                            "description": flow_config.description or "",
                            "flow_display_name": flow_config.name or tool_id,
                            "source": "flow",
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
                
                if node_config.get("flow_id"):
                    flow_config = await container.flow_repository.get(node_config["flow_id"])
                    if flow_config:
                        node_name = flow_config.name
                
                description = f"Нода типа '{node_type}'"
                if node_config.get("flow_id"):
                    description = f"Агент: {node_name}"
                elif node_type == NodeType.CODE.value:
                    description = "Code нода"
                elif node_type == NodeType.LLM_NODE.value:
                    description = "ReAct агент"
                elif node_type == NodeType.HITL_NODE.value:
                    description = "Оператор очереди"
                
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
    
    async def get_branch_schema(self) -> Dict[str, Any]:
        """Получить JSON Schema для создания ветки."""
        container = get_container()
        config = await container.flow_repository.get(self.flow_id)
        if config is None:
            raise ValueError(f"Flow '{self.flow_id}' not found")
        
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "title": f"Branch body — {config.name}",
            "properties": {},
            "required": [],
            "additionalProperties": True,
        }
    
    # === A2A AgentCard (спека) ===
    
    async def get_agent_card(self, base_url: str) -> Dict[str, Any]:
        """Собрать AgentCard (A2A) для этого flow_id."""
        container = get_container()
        config = self._flow_config or await container.flow_repository.get(self.flow_id)
        if config is None:
            raise ValueError(f"Flow '{self.flow_id}' not found")
        
        branches_map = await container.flow_factory.get_branches(self.flow_id)

        card_branch_entries = []
        for branch_id, branch_cfg in branches_map.items():
            card_branch_entries.append(
                AgentSkill(
                    id=branch_id,
                    name=branch_cfg.name,
                    description=branch_cfg.description,
                    tags=branch_cfg.tags or [],
                    inputModes=["text/plain"],
                    outputModes=["text/plain"],
                )
            )

        if not card_branch_entries:
            card_branch_entries.append(
                AgentSkill(
                    id="default",
                    name=config.name,
                    description=config.description,
                    tags=config.tags or [],
                    inputModes=["text/plain"],
                    outputModes=["text/plain"],
                )
            )

        svc = get_settings().server.name
        card = AgentCard(
            name=config.name,
            description=config.description,
            version="1.0.0",
            url=f"{base_url}/{svc}/api/v1/{config.flow_id}",
            capabilities=AgentCapabilities(
                streaming=True, pushNotifications=False, stateTransitionHistory=True
            ),
            skills=card_branch_entries,
            defaultInputModes=["text/plain"],
            defaultOutputModes=["text/plain"],
            supportsAuthenticatedExtendedCard=False,
        )
        
        card_dict = card.model_dump(by_alias=True, exclude_none=True)
        skills_payload = card_dict.pop("skills", None)
        if skills_payload is not None:
            card_dict["branches"] = skills_payload
        
        # Добавляем публичные variables как дополнительное поле (не входит в стандарт A2A)
        public_vars = {}
        flow_variables = config.variables or {}
        for var_name, var_config in flow_variables.items():
            # FlowVariableConfig объект
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


# =============================================================================
# BaseChannelHandler - для отправки сообщений в каналы (Telegram, Email, Webhook)
# =============================================================================

class BaseChannelHandler(ABC):
    """
    Базовый класс для отправки сообщений в каналы.
    
    Отличие от BaseChannel:
    - BaseChannel - получение и обработка сообщений ОТ агента
    - BaseChannelHandler - отправка сообщений В канал (Telegram, Email, Webhook)
    
    Каждый handler реализует методы send_message, send_photo, send_document.
    Метод execute_action - универсальный диспетчер действий.
    """
    
    from apps.flows.src.models.enums import ChannelType
    channel_type: ChannelType
    
    @abstractmethod
    async def send_message(
        self,
        recipient: str,
        text: str,
        config: Dict[str, Any],
        variables: Dict[str, Any],
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Отправляет текстовое сообщение.
        
        Args:
            recipient: Получатель (chat_id для Telegram, email для Email)
            text: Текст сообщения
            config: Конфигурация канала (bot_token, parse_mode, etc)
            variables: Переменные для резолвинга @var:
            **kwargs: Дополнительные параметры (reply_to_message_id, etc)
            
        Returns:
            Ответ от API канала
        """
        pass
    
    @abstractmethod
    async def send_photo(
        self,
        recipient: str,
        photo: Union[str, bytes],
        config: Dict[str, Any],
        variables: Dict[str, Any],
        caption: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Отправляет фото.
        
        Args:
            recipient: Получатель
            photo: URL или bytes фото
            config: Конфигурация канала
            variables: Переменные
            caption: Подпись к фото
        """
        pass
    
    @abstractmethod
    async def send_document(
        self,
        recipient: str,
        document: Union[str, bytes],
        config: Dict[str, Any],
        variables: Dict[str, Any],
        caption: Optional[str] = None,
        filename: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Отправляет документ/файл.
        
        Args:
            recipient: Получатель
            document: URL или bytes документа
            config: Конфигурация канала
            variables: Переменные
            caption: Подпись
            filename: Имя файла
        """
        pass
    
    async def execute_action(
        self,
        action: str,
        params: Dict[str, Any],
        config: Dict[str, Any],
        variables: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Универсальный диспетчер действий.
        
        Вызывает соответствующий метод (send_message, send_photo, etc).
        
        Args:
            action: Название действия (send_message, send_photo, send_document)
            params: Параметры действия (recipient, text, photo, etc)
            config: Конфигурация канала
            variables: Переменные для резолвинга
            
        Returns:
            Результат выполнения действия
        """
        method = getattr(self, action, None)
        
        if method is None:
            raise ValueError(
                f"Unknown action '{action}' for channel {self.channel_type.value}. "
                f"Available: send_message, send_photo, send_document"
            )
        
        logger.info(
            f"Channel {self.channel_type.value}: executing {action} "
            f"to {params.get('recipient', 'unknown')}"
        )
        
        return await method(config=config, variables=variables, **params)
    
    def _resolve_value(self, value: Any, variables: Dict[str, Any]) -> Any:
        """Резолвит @var: значения."""
        if not isinstance(value, str):
            return value
        from apps.flows.src.mapping import MappingResolver
        return MappingResolver.resolve_vars_in_string(value, variables)
