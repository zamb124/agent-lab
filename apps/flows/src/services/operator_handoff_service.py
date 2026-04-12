"""
Единая точка создания задач оператора и завершения handoff (resume flow).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from apps.flows.src.container import get_container
from apps.flows.src.db.models import OperatorTasks
from apps.flows.src.db.operator_repository import OperatorRepository
from apps.flows.src.models.operator_schemas import OperatorTaskStatus
from apps.flows.src.services.operator_tasks_broadcast import publish_operator_tasks_refresh
from apps.flows.src.state.persistence import create_initial_state
from apps.flows.src.streaming.emitter import Emitter
from core.context import get_context
from core.logging import get_logger
from core.state import ExecutionState
from core.state.interrupt import HandoffMode

logger = get_logger(__name__)


def parse_handoff_mode(task: "OperatorTasks") -> HandoffMode:
    """Извлекает HandoffMode из interrupt_snapshot задачи."""
    snap = task.interrupt_snapshot
    if isinstance(snap, dict):
        raw = snap.get("handoff_mode")
        if isinstance(raw, str) and raw.strip():
            return HandoffMode(raw.strip())
    return HandoffMode.SINGLE_REPLY


class OperatorHandoffService:
    """Регистрация handoff в БД и действия оператора по задаче."""

    def __init__(self, repository: OperatorRepository) -> None:
        self._repo = repository

    async def register_handoff(
        self,
        state: ExecutionState,
        *,
        question: str,
        task_title: str,
        assignee_queue_slug: str,
        handoff_mode: HandoffMode = HandoffMode.SINGLE_REPLY,
        correlation_id: Optional[UUID] = None,
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
        cid = correlation_id if correlation_id is not None else uuid.uuid4()
        cid_str = str(cid)
        existing = await self._repo.get_task_by_correlation(company_id, cid_str)
        if existing is not None:
            return cid, existing.id

        snap_ctx = ctx.model_dump(mode="json")
        interrupt_snapshot: dict = {
            "question": question,
            "task_title": task_title,
            "assignee_queue": slug,
            "queue_id": queue.id,
            "handoff_mode": handoff_mode.value,
        }
        task_row = OperatorTasks(
            id=str(uuid.uuid4()),
            company_id=company_id,
            queue_id=queue.id,
            status=OperatorTaskStatus.OPEN.value,
            session_id=state.session_id,
            end_user_id=state.user_id,
            flow_id=state.session_flow_id,
            skill_id=state.skill_id,
            a2a_task_id=state.task_id,
            context_id=state.context_id,
            correlation_id=cid_str,
            interrupt_snapshot=interrupt_snapshot,
            context_data_snapshot=snap_ctx,
        )
        await self._repo.insert_task(task_row)
        logger.info(
            "Operator task created: id=%s queue=%s correlation=%s",
            task_row.id,
            queue.slug,
            cid_str,
        )
        container = get_container()
        await publish_operator_tasks_refresh(
            container.redis_client, self._repo, queue.id
        )
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
        container = get_container()
        await publish_operator_tasks_refresh(
            container.redis_client, self._repo, task.queue_id
        )

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

        log_entry: dict = {
            "role": "operator",
            "text": text.strip(),
            "ts": datetime.now(timezone.utc).isoformat(),
            "user_id": operator_user_id,
        }
        if validated_file_ids:
            log_entry["file_ids"] = validated_file_ids
        await self._repo.append_dialog_log(company_id, task_id, log_entry)

        exec_state = create_initial_state(
            task_id=task.a2a_task_id,
            context_id=ctx_id,
            user_id=task.end_user_id,
            session_id=task.session_id,
            skill_id=task.skill_id,
        )
        container = get_container()
        emitter = Emitter(container.redis_client, exec_state)
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
        await publish_operator_tasks_refresh(
            container.redis_client, self._repo, task.queue_id
        )

    async def _validate_file_ids(self, file_ids: list[str]) -> list[str]:
        """Проверяет существование файлов и возвращает валидный список."""
        container = get_container()
        file_repo = container.file_repository
        validated: list[str] = []
        for fid in file_ids:
            fid = fid.strip()
            if not fid:
                continue
            record = await file_repo.get(fid)
            if record is None:
                raise ValueError(f"Файл {fid!r} не найден")
            validated.append(fid)
        return validated

    @staticmethod
    def _format_dialog_log_for_tool_result(dialog_log: list[dict]) -> str:
        """Форматирует реплики takeover-диалога для включения в tool_result.

        Вставка dialog_log напрямую в state.messages невозможна: это ломает
        tool_call/tool_result паринг (assistant+tool_calls → tool), необходимый
        для OpenAI-совместимых API. Вместо этого весь диалог форматируется
        как текст и передаётся агенту внутри tool_result.
        """
        lines: list[str] = []
        for entry in dialog_log:
            role_raw = entry.get("role", "")
            text = str(entry.get("text", "")).strip()
            if not text and not entry.get("file_ids"):
                continue
            label = "Оператор" if role_raw == "operator" else "Пользователь"
            parts = []
            if text:
                parts.append(text)
            entry_file_ids = entry.get("file_ids", [])
            for fid in entry_file_ids:
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
        if not await self._repo.is_user_member_of_queue(task.queue_id, operator_user_id):
            raise PermissionError("Нет доступа к очереди этой задачи")
        if task.context_data_snapshot is None:
            raise ValueError("У задачи нет context_data_snapshot, resume невозможен")
        ctx_dict = dict(task.context_data_snapshot)
        channel = ctx_dict.get("channel")
        if not channel or not isinstance(channel, str):
            raise ValueError("context_data_snapshot не содержит строковый channel")

        validated_file_ids = await self._validate_file_ids(file_ids) if file_ids else []
        mode = self._task_handoff_mode(task)
        content_for_resume = resolution.strip()
        container = get_container()

        if mode == HandoffMode.TAKEOVER:
            log_entry: dict = {
                "role": "operator",
                "text": resolution.strip(),
                "ts": datetime.now(timezone.utc).isoformat(),
                "user_id": operator_user_id,
            }
            if validated_file_ids:
                log_entry["file_ids"] = validated_file_ids
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
                    skill_id=task.skill_id,
                )
                emitter = Emitter(container.redis_client, exec_state)
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

        resolution_payload: dict = {"text": resolution.strip()}
        if validated_file_ids:
            resolution_payload["file_ids"] = validated_file_ids
        await self._repo.update_task_fields(
            company_id,
            task_id,
            status=OperatorTaskStatus.COMPLETED.value,
            resolution_payload=resolution_payload,
        )
        await publish_operator_tasks_refresh(
            container.redis_client, self._repo, task.queue_id
        )

        from apps.flows.src.tasks.flow_tasks import process_flow_task

        tid = task.a2a_task_id if task.a2a_task_id else ""
        cid = task.context_id if task.context_id else task.session_id.split(":", 1)[-1]

        await process_flow_task.kiq(
            flow_id=task.flow_id,
            session_id=task.session_id,
            user_id=task.end_user_id,
            content=content_for_resume,
            skill_id=task.skill_id,
            channel=channel,
            task_id=tid,
            context_id=cid,
            metadata={},
            is_resume=True,
            files=[],
            context_data=ctx_dict,
            trace_context=None,
        )
        logger.info("Operator handoff completed, process_flow_task kicked: task_id=%s", task_id)

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

        log_entry: dict = {
            "role": "user",
            "text": text.strip(),
            "ts": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
        }
        if file_ids:
            log_entry["file_ids"] = file_ids
        await self._repo.append_dialog_log(company_id, task_id, log_entry)

        container = get_container()
        await publish_operator_tasks_refresh(
            container.redis_client, self._repo, task.queue_id
        )
