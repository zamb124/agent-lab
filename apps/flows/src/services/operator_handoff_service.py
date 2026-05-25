"""
Единая точка создания задач оператора и завершения handoff (resume flow).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from uuid import UUID

from apps.flows.config import get_settings as get_flows_settings
from apps.flows.src.db.models import OperatorTasks
from apps.flows.src.db.operator_repository import OperatorRepository
from apps.flows.src.durable_execution import (
    HandoffCompletedPayload,
    WorkflowEventType,
    create_initial_state,
)
from apps.flows.src.durable_execution.manager import DurableWorkflowRuntime
from apps.flows.src.models.flow_config import FlowConfig
from apps.flows.src.models.operator_schemas import (
    OperatorDialogLogEntry,
    OperatorHandoffCommand,
    OperatorInterruptSnapshot,
    OperatorResolutionPayload,
    OperatorTaskOut,
    OperatorTaskStatus,
)
from apps.flows.src.services.operator_tasks_broadcast import publish_operator_tasks_refresh
from apps.flows.src.streaming.emitter import Emitter
from apps.flows.src.tasks.task_names import TASK_PROCESS_FLOW
from apps.flows_worker.broker import broker as flows_broker
from core.clients.redis_client import RedisClient
from core.context import get_context
from core.files.file_repository import FileRepository
from core.logging import get_logger
from core.state import ExecutionState
from core.state.interrupt import HandoffMode
from core.tasks.kicker import kiq_task_name_with_context
from core.tracing.operation_span import traced_operation
from core.types import JsonObject, parse_json_object

logger = get_logger(__name__)
HANDOFF_PREVIEW_MAX_LEN = 200
HANDOFF_COMMAND_NAMESPACE = UUID("7f74c4a1-6b92-45a4-942a-7e4f983ddc58")


def build_operator_handoff_command(
    *,
    state: ExecutionState,
    node_id: str,
    tool_call_id: str | None = None,
) -> OperatorHandoffCommand:
    execution_branch_id = state.durable_execution_branch_id
    if execution_branch_id is None:
        raise RuntimeError("HITL handoff requires durable execution_branch_id")
    node_schedule_sequence = state.durable_node_schedule_sequence
    if node_schedule_sequence is None:
        raise RuntimeError("HITL handoff requires durable NodeScheduled.sequence")
    key_parts = [
        "hitl",
        f"session:{state.session_id}",
        f"branch:{execution_branch_id}",
        f"schedule:{node_schedule_sequence}",
        f"node:{node_id}",
    ]
    if tool_call_id is not None:
        key_parts.append(f"tool_call:{tool_call_id}")
    idempotency_key = ":".join(key_parts)
    return OperatorHandoffCommand(
        correlation_id=uuid.uuid5(HANDOFF_COMMAND_NAMESPACE, idempotency_key),
        idempotency_key=idempotency_key,
        execution_branch_id=execution_branch_id,
        node_schedule_sequence=node_schedule_sequence,
        node_id=node_id,
        tool_call_id=tool_call_id,
    )


def parse_handoff_mode(task: "OperatorTasks") -> HandoffMode:
    """Извлекает HandoffMode из interrupt_snapshot задачи."""
    if task.interrupt_snapshot is None:
        raise ValueError("OperatorTasks.interrupt_snapshot обязателен для handoff mode")
    snapshot = OperatorInterruptSnapshot.model_validate(task.interrupt_snapshot)
    return snapshot.handoff_mode


def operator_task_handoff_texts(task: OperatorTasks) -> tuple[str, str]:
    if task.interrupt_snapshot is None:
        raise ValueError("OperatorTasks.interrupt_snapshot обязателен для handoff preview")
    snapshot = OperatorInterruptSnapshot.model_validate(task.interrupt_snapshot)
    question = snapshot.question
    if len(question) > HANDOFF_PREVIEW_MAX_LEN:
        preview = question[: HANDOFF_PREVIEW_MAX_LEN - 1].rstrip() + "\u2026"
    else:
        preview = question
    return snapshot.task_title, preview


def _flow_display_name(flow_config: FlowConfig | None, flow_id: str) -> str:
    if flow_config is None:
        return flow_id
    flow_name = flow_config.name.strip()
    if not flow_name:
        return flow_id
    return flow_name


def _skill_display_name(flow_config: FlowConfig | None, branch_id: str) -> str:
    if flow_config is not None and flow_config.branches:
        branch_config = flow_config.branches.get(branch_id)
        if branch_config is not None:
            branch_name = branch_config.name.strip()
            if branch_name:
                return branch_name
    return branch_id


def operator_task_to_out(
    task: OperatorTasks,
    *,
    flow_config: FlowConfig | None = None,
) -> OperatorTaskOut:
    handoff_title, handoff_preview = operator_task_handoff_texts(task)
    return OperatorTaskOut(
        operator_task_id=task.id,
        company_id=task.company_id,
        queue_id=task.queue_id,
        status=OperatorTaskStatus(task.status),
        session_id=task.session_id,
        end_user_id=task.end_user_id,
        flow_id=task.flow_id,
        branch_id=task.branch_id,
        flow_display_name=_flow_display_name(flow_config, task.flow_id),
        skill_display_name=_skill_display_name(flow_config, task.branch_id),
        handoff_title=handoff_title,
        handoff_message_preview=handoff_preview,
        handoff_mode=parse_handoff_mode(task),
        a2a_task_id=task.a2a_task_id,
        context_id=task.context_id,
        correlation_id=task.correlation_id,
        claimed_by_user_id=task.claimed_by_user_id,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


class OperatorHandoffService:
    """Регистрация handoff в БД и действия оператора по задаче."""

    def __init__(
        self,
        repository: OperatorRepository,
        *,
        file_repository: FileRepository,
        redis_client: RedisClient,
        workflow_runtime: DurableWorkflowRuntime,
    ) -> None:
        self._repo: OperatorRepository = repository
        self._file_repo: FileRepository = file_repository
        self._redis_client: RedisClient = redis_client
        self._workflow_runtime: DurableWorkflowRuntime = workflow_runtime

    async def register_handoff(
        self,
        state: ExecutionState,
        *,
        question: str,
        task_title: str,
        assignee_queue_slug: str,
        handoff_mode: HandoffMode = HandoffMode.SINGLE_REPLY,
        command: OperatorHandoffCommand,
    ) -> tuple[UUID, str]:
        """Возвращает (correlation_id, operator_task_id)."""
        ctx = get_context()
        if ctx is None or ctx.active_company is None:
            raise ValueError("OperatorHandoffService.register_handoff: нужен Context с active_company")
        company_id = ctx.active_company.company_id
        slug = assignee_queue_slug.strip()
        queue = await self._repo.get_queue_by_slug(company_id, slug)
        if queue is None:
            raise ValueError(
                f"Очередь оператора со slug {slug!r} не найдена для текущей компании"
            )
        cid = command.correlation_id
        cid_str = str(cid)
        existing = await self._repo.get_task_by_correlation(company_id, cid_str)
        if existing is not None:
            logger.info(
                "operator_handoff.register_replayed",
                operator_task_id=existing.id,
                correlation_id=cid_str,
                handoff_command_id=command.idempotency_key,
                session_id=state.session_id,
                execution_branch_id=command.execution_branch_id,
                node_schedule_sequence=command.node_schedule_sequence,
                node_id=command.node_id,
                tool_call_id=command.tool_call_id,
            )
            return cid, existing.id

        snap_ctx: JsonObject = ctx.to_dict()
        interrupt_snapshot = OperatorInterruptSnapshot(
            question=question,
            task_title=task_title,
            assignee_queue=slug,
            queue_id=queue.id,
            handoff_mode=handoff_mode,
            handoff_command_id=command.idempotency_key,
            execution_branch_id=command.execution_branch_id,
            node_schedule_sequence=command.node_schedule_sequence,
            node_id=command.node_id,
            tool_call_id=command.tool_call_id,
        )
        async with traced_operation(
            "flows.hitl.handoff.register",
            event_type="hitl.handoff.register",
            resource_type="operator_task",
            resource_id=cid_str,
            extra_attributes={
                "platform.hitl.command_id": command.idempotency_key,
                "platform.hitl.correlation_id": cid_str,
                "platform.hitl.queue_slug": queue.slug,
                "platform.workflow.session_id": state.session_id,
                "platform.workflow.execution_branch_id": command.execution_branch_id,
                "platform.workflow.node_schedule_sequence": command.node_schedule_sequence,
                "platform.node.id": command.node_id,
            },
        ):
            task_row = OperatorTasks(
                id=str(uuid.uuid4()),
                company_id=company_id,
                queue_id=queue.id,
                status=OperatorTaskStatus.OPEN.value,
                session_id=state.session_id,
                end_user_id=state.user_id,
                flow_id=state.session_flow_id,
                branch_id=state.branch_id,
                a2a_task_id=state.task_id,
                context_id=state.context_id,
                correlation_id=cid_str,
                interrupt_snapshot=parse_json_object(
                    interrupt_snapshot.model_dump_json(),
                    "OperatorInterruptSnapshot",
                ),
                context_data_snapshot=snap_ctx,
            )
            await self._repo.insert_task(task_row)
        logger.info(
            "operator_handoff.registered",
            operator_task_id=task_row.id,
            queue_slug=queue.slug,
            correlation_id=cid_str,
            handoff_command_id=command.idempotency_key,
            session_id=state.session_id,
            execution_branch_id=command.execution_branch_id,
            node_schedule_sequence=command.node_schedule_sequence,
            node_id=command.node_id,
            tool_call_id=command.tool_call_id,
        )
        await publish_operator_tasks_refresh(self._repo, queue.id)
        return cid, task_row.id

    async def claim_task(
        self,
        *,
        company_id: str,
        task_id: str,
        operator_user_id: str,
    ) -> None:
        task = await self._repo.get_task(company_id, task_id)
        if task is None:
            raise ValueError(f"Задача оператора {task_id!r} не найдена")
        if not await self._repo.is_user_member_of_queue(task.queue_id, operator_user_id):
            raise PermissionError("Нет доступа к очереди этой задачи")
        await self._repo.update_task_fields(
            company_id,
            task_id,
            status=OperatorTaskStatus.CLAIMED.value,
            claimed_by_user_id=operator_user_id,
        )
        await publish_operator_tasks_refresh(self._repo, task.queue_id)

    def _task_handoff_mode(self, task: "OperatorTasks") -> HandoffMode:
        return parse_handoff_mode(task)

    async def publish_operator_message_to_user_stream(
        self,
        *,
        company_id: str,
        task_id: str,
        operator_user_id: str,
        text: str,
        file_ids: list[str] | None = None,
    ) -> None:
        task = await self._repo.get_task(company_id, task_id)
        if task is None:
            raise ValueError(f"Задача оператора {task_id!r} не найдена")
        if not await self._repo.is_user_member_of_queue(task.queue_id, operator_user_id):
            raise PermissionError("Нет доступа к очереди этой задачи")
        mode = self._task_handoff_mode(task)
        if mode == HandoffMode.SINGLE_REPLY:
            raise PermissionError(
                "Отправка сообщений недоступна в режиме single_reply — используйте complete"
            )
        if not task.a2a_task_id:
            raise ValueError("У задачи нет a2a_task_id, публикация в стрим невозможна")
        ctx_id = task.context_id
        if not ctx_id:
            parts = task.session_id.split(":", 1)
            ctx_id = parts[1] if len(parts) > 1 else task.session_id

        validated_file_ids = await self._validate_file_ids(file_ids) if file_ids else []

        log_entry = OperatorDialogLogEntry(
            role="operator",
            text=text.strip(),
            ts=datetime.now(timezone.utc).isoformat(),
            user_id=operator_user_id,
            file_ids=validated_file_ids,
        )
        await self._repo.append_dialog_log(company_id, task_id, log_entry)

        exec_state = create_initial_state(
            task_id=task.a2a_task_id,
            context_id=ctx_id,
            user_id=task.end_user_id,
            session_id=task.session_id,
            branch_id=task.branch_id,
        )
        emitter = Emitter(self._redis_client, exec_state)
        await emitter.emit_text(
            text.strip(), append=True, last_chunk=False, artifact_name="operator_reply"
        )
        if validated_file_ids:
            await emitter.emit_file_artifact(validated_file_ids)
        await self._repo.update_task_fields(
            company_id,
            task_id,
            status=OperatorTaskStatus.USER_DIALOG.value,
        )
        await publish_operator_tasks_refresh(self._repo, task.queue_id)

    async def _validate_file_ids(self, file_ids: list[str]) -> list[str]:
        """Проверяет существование файлов и возвращает валидный список."""
        validated: list[str] = []
        for fid in file_ids:
            fid = fid.strip()
            if not fid:
                continue
            record = await self._file_repo.get(fid)
            if record is None:
                raise ValueError(f"Файл {fid!r} не найден")
            validated.append(fid)
        return validated

    @staticmethod
    def _format_dialog_log_for_tool_result(dialog_log: list[OperatorDialogLogEntry]) -> str:
        """Форматирует реплики takeover-диалога для включения в tool_result.

        Вставка dialog_log напрямую в state.messages невозможна: это ломает
        tool_call/tool_result паринг (assistant+tool_calls → tool), необходимый
        для OpenAI-совместимых API. Вместо этого весь диалог форматируется
        как текст и передаётся агенту внутри tool_result.
        """
        lines: list[str] = []
        for entry in dialog_log:
            text = entry.text.strip()
            if not text and not entry.file_ids:
                continue
            label = "Оператор" if entry.role == "operator" else "Пользователь"
            parts: list[str] = []
            if text:
                parts.append(text)
            for fid in entry.file_ids:
                parts.append(f"[Файл: /flows/api/v1/files/download/{fid}]")
            if parts:
                lines.append(f"[{label}]: {' '.join(parts)}")
        return "\n".join(lines)

    async def complete_handoff(
        self,
        *,
        company_id: str,
        task_id: str,
        operator_user_id: str,
        resolution: str,
        file_ids: list[str] | None = None,
    ) -> None:
        task = await self._repo.get_task(company_id, task_id)
        if task is None:
            raise ValueError(f"Задача оператора {task_id!r} не найдена")
        if task.status == OperatorTaskStatus.CANCELLED.value:
            raise ValueError(f"Задача оператора {task_id!r} отменена")
        if not await self._repo.is_user_member_of_queue(task.queue_id, operator_user_id):
            raise PermissionError("Нет доступа к очереди этой задачи")
        if task.context_data_snapshot is None:
            raise ValueError("У задачи нет context_data_snapshot, resume невозможен")
        if task.interrupt_snapshot is None:
            raise ValueError("У задачи нет interrupt_snapshot, resume невозможен")
        interrupt_snapshot = OperatorInterruptSnapshot.model_validate(task.interrupt_snapshot)
        ctx_dict = task.context_data_snapshot
        channel = ctx_dict.get("channel")
        if not channel or not isinstance(channel, str):
            raise ValueError("context_data_snapshot не содержит строковый channel")

        validated_file_ids = await self._validate_file_ids(file_ids) if file_ids else []
        mode = self._task_handoff_mode(task)
        content_for_resume = resolution.strip()
        resolution_payload = OperatorResolutionPayload(
            text=resolution.strip(),
            file_ids=validated_file_ids,
        )

        if task.status == OperatorTaskStatus.COMPLETED.value:
            stored_resolution = self._completed_resolution_payload(task)
            if resolution_payload != stored_resolution:
                raise ValueError(
                    "Operator handoff completion replay payload mismatch: "
                    + f"operator_task_id={task_id!r}"
                )
            content_for_resume = await self._content_for_completed_resume(
                company_id=company_id,
                task=task,
                resolution_payload=stored_resolution,
                handoff_mode=mode,
            )
            await self._record_handoff_completed_once(
                session_id=task.session_id,
                payload=HandoffCompletedPayload(
                    handoff_command_id=interrupt_snapshot.handoff_command_id,
                    correlation_id=self._task_correlation_id(task),
                    operator_task_id=task_id,
                    operator_user_id=operator_user_id,
                    handoff_mode=interrupt_snapshot.handoff_mode,
                    resolution_preview=stored_resolution.text[:HANDOFF_PREVIEW_MAX_LEN],
                    file_count=len(stored_resolution.file_ids),
                ),
            )
            await self._resume_completed_handoff_if_needed(
                task=task,
                channel=channel,
                context_data=ctx_dict,
                content_for_resume=content_for_resume,
                interrupt_snapshot=interrupt_snapshot,
            )
            logger.info(
                "operator_handoff.complete_replayed",
                operator_task_id=task_id,
                correlation_id=task.correlation_id,
                session_id=task.session_id,
                handoff_command_id=interrupt_snapshot.handoff_command_id,
            )
            return

        if mode == HandoffMode.TAKEOVER:
            log_entry = OperatorDialogLogEntry(
                role="operator",
                text=resolution.strip(),
                ts=datetime.now(timezone.utc).isoformat(),
                user_id=operator_user_id,
                file_ids=validated_file_ids,
            )
            await self._repo.append_dialog_log(company_id, task_id, log_entry)

            if task.a2a_task_id:
                ctx_id = task.context_id
                if not ctx_id:
                    parts = task.session_id.split(":", 1)
                    ctx_id = parts[1] if len(parts) > 1 else task.session_id
                exec_state = create_initial_state(
                    task_id=task.a2a_task_id,
                    context_id=ctx_id,
                    user_id=task.end_user_id,
                    session_id=task.session_id,
                    branch_id=task.branch_id,
                )
                emitter = Emitter(self._redis_client, exec_state)
                await emitter.emit_text(
                    resolution.strip(),
                    append=True,
                    last_chunk=False,
                    artifact_name="operator_reply",
                )
                if validated_file_ids:
                    await emitter.emit_file_artifact(validated_file_ids)

            log = await self._repo.get_dialog_log(company_id, task_id)
            if log:
                dialog_text = self._format_dialog_log_for_tool_result(log)
                content_for_resume = (
                    f"Диалог оператора с пользователем:\n{dialog_text}\n\n"
                    f"Итог оператора: {resolution.strip()}"
                )

        completed_now = await self._repo.complete_task_once(
            company_id,
            task_id,
            resolution_payload=resolution_payload,
        )
        if not completed_now:
            logger.info(
                "operator_handoff.complete_replayed",
                operator_task_id=task_id,
                correlation_id=task.correlation_id,
                session_id=task.session_id,
            )
            return
        await self._record_handoff_completed_once(
            session_id=task.session_id,
            payload=HandoffCompletedPayload(
                handoff_command_id=interrupt_snapshot.handoff_command_id,
                correlation_id=self._task_correlation_id(task),
                operator_task_id=task_id,
                operator_user_id=operator_user_id,
                handoff_mode=interrupt_snapshot.handoff_mode,
                resolution_preview=resolution.strip()[:HANDOFF_PREVIEW_MAX_LEN],
                file_count=len(validated_file_ids),
            )
        )
        await publish_operator_tasks_refresh(self._repo, task.queue_id)
        await self._resume_completed_handoff_if_needed(
            task=task,
            channel=channel,
            context_data=ctx_dict,
            content_for_resume=content_for_resume,
            interrupt_snapshot=interrupt_snapshot,
        )

    @staticmethod
    def _task_correlation_id(task: OperatorTasks) -> str:
        if task.correlation_id is None:
            raise ValueError("У задачи нет correlation_id, resume невозможен")
        return task.correlation_id

    @staticmethod
    def _completed_resolution_payload(task: OperatorTasks) -> OperatorResolutionPayload:
        if task.resolution_payload is None:
            raise ValueError("Completed operator task has no resolution_payload")
        return OperatorResolutionPayload.model_validate(task.resolution_payload)

    async def _content_for_completed_resume(
        self,
        *,
        company_id: str,
        task: OperatorTasks,
        resolution_payload: OperatorResolutionPayload,
        handoff_mode: HandoffMode,
    ) -> str:
        if handoff_mode != HandoffMode.TAKEOVER:
            return resolution_payload.text
        log = await self._repo.get_dialog_log(company_id, task.id)
        if not log:
            return resolution_payload.text
        dialog_text = self._format_dialog_log_for_tool_result(log)
        return (
            f"Диалог оператора с пользователем:\n{dialog_text}\n\n"
            f"Итог оператора: {resolution_payload.text}"
        )

    async def _record_handoff_completed_once(
        self,
        *,
        session_id: str,
        payload: HandoffCompletedPayload,
    ) -> None:
        if await self._handoff_completed_event_exists(session_id, payload.handoff_command_id):
            logger.info(
                "operator_handoff.completed_event_replayed",
                session_id=session_id,
                handoff_command_id=payload.handoff_command_id,
                operator_task_id=payload.operator_task_id,
                correlation_id=payload.correlation_id,
            )
            return
        async with traced_operation(
            "flows.hitl.handoff.complete",
            event_type="hitl.handoff.complete",
            resource_type="operator_task",
            resource_id=payload.operator_task_id,
            extra_attributes={
                "platform.hitl.command_id": payload.handoff_command_id,
                "platform.hitl.correlation_id": payload.correlation_id,
                "platform.hitl.operator_task_id": payload.operator_task_id,
                "platform.workflow.session_id": session_id,
            },
        ):
            _ = await self._workflow_runtime.record_lifecycle_event(
                session_id,
                event_type=WorkflowEventType.handoff_completed,
                payload=payload,
            )

    async def _handoff_completed_event_exists(
        self,
        session_id: str,
        handoff_command_id: str,
    ) -> bool:
        offset = 0
        limit = 200
        while True:
            history, total = await self._workflow_runtime.get_state_history(
                session_id,
                limit=limit,
                offset=offset,
            )
            for event in history:
                payload = event.payload
                if (
                    event.event_type is WorkflowEventType.handoff_completed
                    and isinstance(payload, HandoffCompletedPayload)
                    and payload.handoff_command_id == handoff_command_id
                ):
                    return True
            if not history or offset + len(history) >= total:
                return False
            offset += len(history)

    async def _resume_completed_handoff_if_needed(
        self,
        *,
        task: OperatorTasks,
        channel: str,
        context_data: JsonObject,
        content_for_resume: str,
        interrupt_snapshot: OperatorInterruptSnapshot,
    ) -> None:
        task_correlation_id = self._task_correlation_id(task)
        saved_state = await self._workflow_runtime.get_state(task.session_id)
        if saved_state is not None and saved_state.interrupt is None:
            logger.info(
                "operator_handoff.resume_replayed",
                operator_task_id=task.id,
                correlation_id=task_correlation_id,
                handoff_command_id=interrupt_snapshot.handoff_command_id,
                session_id=task.session_id,
            )
            return
        if saved_state is not None and saved_state.interrupt is not None:
            interrupt_correlation_id = saved_state.interrupt.correlation_id
            if (
                interrupt_correlation_id is not None
                and str(interrupt_correlation_id) != task_correlation_id
            ):
                raise ValueError(
                    "Operator handoff resume correlation mismatch: "
                    + f"operator_task_id={task.id!r}"
                )

        tid = task.a2a_task_id if task.a2a_task_id else ""
        cid = task.context_id if task.context_id else task.session_id.split(":", 1)[-1]

        resume_task = await kiq_task_name_with_context(
            TASK_PROCESS_FLOW,
            flows_broker,
            flow_id=task.flow_id,
            session_id=task.session_id,
            user_id=task.end_user_id,
            content=content_for_resume,
            branch_id=task.branch_id,
            channel=channel,
            task_id=tid,
            context_id=cid,
            metadata={},
            is_resume=True,
            files=[],
            context_data=context_data,
            trace_context=None,
            background_kind="operator_handoff",
        )
        resume_result = await asyncio.wait_for(
            resume_task.wait_result(),
            timeout=get_flows_settings().default_flow_timeout_seconds + 5,
        )
        if resume_result.is_err:
            raise RuntimeError(f"Operator handoff resume failed: {resume_result.error}")
        logger.info(
            "operator_handoff.resume_completed",
            operator_task_id=task.id,
            correlation_id=task_correlation_id,
            handoff_command_id=interrupt_snapshot.handoff_command_id,
            session_id=task.session_id,
            flow_id=task.flow_id,
            branch_id=task.branch_id,
        )
        logger.info(
            "operator_handoff.completed",
            operator_task_id=task.id,
            correlation_id=task_correlation_id,
            handoff_command_id=interrupt_snapshot.handoff_command_id,
            session_id=task.session_id,
            flow_id=task.flow_id,
            branch_id=task.branch_id,
        )

    async def receive_user_reply(
        self,
        *,
        company_id: str,
        task_id: str,
        text: str,
        user_id: str,
        file_ids: list[str] | None = None,
    ) -> None:
        """Реплика пользователя оператору при takeover: сохраняем и публикуем."""
        task = await self._repo.get_task(company_id, task_id)
        if task is None:
            raise ValueError(f"Задача оператора {task_id!r} не найдена")
        mode = self._task_handoff_mode(task)
        if mode != HandoffMode.TAKEOVER:
            raise PermissionError("Ответ пользователя доступен только в режиме takeover")
        if task.status not in (
            OperatorTaskStatus.CLAIMED.value,
            OperatorTaskStatus.USER_DIALOG.value,
        ):
            raise ValueError(
                f"Задача в статусе {task.status!r}, ответ пользователя недоступен"
            )

        log_entry = OperatorDialogLogEntry(
            role="user",
            text=text.strip(),
            ts=datetime.now(timezone.utc).isoformat(),
            user_id=user_id,
            file_ids=file_ids or [],
        )
        await self._repo.append_dialog_log(company_id, task_id, log_entry)

        await publish_operator_tasks_refresh(self._repo, task.queue_id)
