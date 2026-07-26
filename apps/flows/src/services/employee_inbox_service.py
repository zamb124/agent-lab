"""Единый inbox «платформа → flow-сотрудник».

Одна точка входа для входящей работы сотруднику-агенту: sync-меншены/DM и
назначение задач worktracker. Источник событий — consumer group `flows` шины
`platform:events` (`PlatformEventConsumerService`); поверхности (sync,
worktracker) публикуют обычные доменные события и не знают про flows-домен.

Сервис резолвит flow по employee-user, собирает ``context_id`` от источника и
запускает flow через стандартный ``process_flow_task`` от имени сотрудника
(SESSION JWT), сохраняя инициатора-отправителя для эскалаций.

Write-back в WorkItem (видимость «агент взял задачу»): при запуске от
``work_item_assigned`` задаче добавляется ``FlowSessionLink`` + системный
комментарий; ошибка запуска тоже фиксируется комментарием.
"""

from __future__ import annotations

from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.services.execution_identity import resolve_execution_context
from apps.flows.src.tasks.task_names import TASK_PROCESS_FLOW
from core.context import clear_context, get_context, set_context
from core.context.job_context import build_job_context
from core.identity.flow_employee import is_flow_employee, require_flow_employee_flow_id
from core.logging import get_logger
from core.tasks import enqueue
from core.types import JsonObject
from core.worktracker.models import (
    FlowSessionLink,
    UserActor,
    WorkItemCommentRole,
)

logger = get_logger(__name__)


class EmployeeInboxService:
    """Запуск flow-сотрудника на входящую работу (sync / worktracker)."""

    def __init__(self, container: FlowRuntimeContainer) -> None:
        self._container: FlowRuntimeContainer = container

    async def dispatch_sync_message(
        self,
        *,
        company_id: str,
        employee_user_id: str,
        sender_user_id: str,
        channel_id: str,
        message_id: str,
        text: str,
    ) -> bool:
        """Входящее сообщение sync (mention или DM) сотруднику-агенту."""
        return await self._dispatch(
            company_id=company_id,
            employee_user_id=employee_user_id,
            sender_user_id=sender_user_id,
            source="sync_message",
            context_id=f"sync:{channel_id}",
            text=text,
            metadata={
                "employee_inbox_source": "sync_message",
                "channel_id": channel_id,
                "message_id": message_id,
            },
        )

    async def dispatch_work_item_assigned(
        self,
        *,
        company_id: str,
        employee_user_id: str,
        sender_user_id: str,
        work_item_id: str,
        text: str,
        branch_id: str = "default",
    ) -> bool:
        """Назначение задачи worktracker сотруднику-агенту + write-back в задачу."""
        context_id = f"work_item:{work_item_id}"
        try:
            dispatched = await self._dispatch(
                company_id=company_id,
                employee_user_id=employee_user_id,
                sender_user_id=sender_user_id,
                source="work_item_assigned",
                context_id=context_id,
                text=text,
                branch_id=branch_id,
                metadata={
                    "employee_inbox_source": "work_item_assigned",
                    "work_item_id": work_item_id,
                },
            )
        except Exception as exc:
            await self._write_back_failure(
                company_id=company_id,
                work_item_id=work_item_id,
                sender_user_id=sender_user_id,
                error_text=str(exc),
            )
            raise
        if dispatched:
            employee_user = await self._container.user_repository.get(employee_user_id)
            if employee_user is None:
                raise ValueError(f"employee inbox: user {employee_user_id} not found")
            flow_id = require_flow_employee_flow_id(employee_user)
            try:
                await self._write_back_started(
                    company_id=company_id,
                    work_item_id=work_item_id,
                    flow_id=flow_id,
                    context_id=context_id,
                    sender_user_id=sender_user_id,
                )
            except Exception as write_back_exc:
                # Run уже поставлен в очередь — write-back не должен его ронять.
                logger.error(
                    "employee_inbox.write_back_started_failed",
                    work_item_id=work_item_id,
                    error=str(write_back_exc),
                    exc_info=True,
                )
        return dispatched

    async def _dispatch(
        self,
        *,
        company_id: str,
        employee_user_id: str,
        sender_user_id: str,
        source: str,
        context_id: str,
        text: str,
        metadata: JsonObject,
        branch_id: str = "default",
    ) -> bool:
        """Общий путь запуска; False — адресат не flow-сотрудник (ignored)."""
        container = self._container
        employee_user = await container.user_repository.get(employee_user_id)
        if employee_user is None:
            raise ValueError(f"employee inbox: user {employee_user_id} not found")
        if not is_flow_employee(employee_user):
            logger.info(
                "employee_inbox.ignored_not_flow_employee",
                employee_user_id=employee_user_id,
                source=source,
            )
            return False
        flow_id = require_flow_employee_flow_id(employee_user)

        company = await container.company_repository.get(company_id)
        if company is None:
            raise ValueError(f"employee inbox: company {company_id} not found")

        sender = await container.user_repository.get(sender_user_id)
        if sender is None:
            raise ValueError(f"employee inbox: sender {sender_user_id} not found")

        initiator_context = build_job_context(
            company=company,
            user=sender,
            host="",
            trace_id="",
            session_id="",
            channel="employee_inbox",
        )
        previous_context = get_context()
        set_context(initiator_context)
        try:
            flow_config = await container.flow_repository.get(flow_id)
            if flow_config is None:
                raise ValueError(f"employee inbox: flow {flow_id} not found")

            execution = await resolve_execution_context(
                container,
                flow_config=flow_config,
                initiator_context=initiator_context,
            )

            session_id = f"{flow_id}:{context_id}"
            logger.info(
                "employee_inbox.run",
                flow_id=flow_id,
                employee_user_id=employee_user_id,
                source=source,
                context_id=context_id,
            )
            _ = await enqueue(
                TASK_PROCESS_FLOW,
                flow_id=flow_id,
                session_id=session_id,
                user_id=execution.context.user.user_id,
                initiator_user_id=execution.initiator_user_id,
                content=text,
                branch_id=branch_id,
                channel="a2a",
                task_id=context_id,
                context_id=context_id,
                metadata=metadata,
                is_resume=False,
                files=[],
                context_data=execution.context.to_dict(),
                trace_context=None,
                background_kind="employee_inbox",
            )
        finally:
            if previous_context is None:
                clear_context()
            else:
                set_context(previous_context)
        return True

    async def _write_back_started(
        self,
        *,
        company_id: str,
        work_item_id: str,
        flow_id: str,
        context_id: str,
        sender_user_id: str,
    ) -> None:
        """FlowSessionLink + системный комментарий «агент взял задачу»."""
        work_item_service = self._container.work_item_service
        item = await work_item_service.get(company_id, work_item_id)
        session_id = f"{flow_id}:{context_id}"
        has_session_link = any(
            isinstance(link, FlowSessionLink) and link.session_id == session_id
            for link in item.links
        )
        if not has_session_link:
            links = [
                *item.links,
                FlowSessionLink(
                    session_id=session_id,
                    a2a_task_id=context_id,
                    context_id=context_id,
                    flow_id=flow_id,
                ),
            ]
            _ = await work_item_service.update(
                company_id=company_id,
                work_item_id=work_item_id,
                links=links,
            )
        _ = await work_item_service.add_comment(
            company_id=company_id,
            work_item_id=work_item_id,
            author=UserActor(user_id=sender_user_id),
            role=WorkItemCommentRole.SYSTEM,
            text="Агент взял задачу в работу.",
        )

    async def _write_back_failure(
        self,
        *,
        company_id: str,
        work_item_id: str,
        sender_user_id: str,
        error_text: str,
    ) -> None:
        """Системный комментарий об ошибке запуска агента (best-effort)."""
        try:
            _ = await self._container.work_item_service.add_comment(
                company_id=company_id,
                work_item_id=work_item_id,
                author=UserActor(user_id=sender_user_id),
                role=WorkItemCommentRole.SYSTEM,
                text=f"Не удалось запустить агента: {error_text}",
            )
        except Exception as comment_exc:
            logger.error(
                "employee_inbox.write_back_failure_comment_failed",
                work_item_id=work_item_id,
                error=str(comment_exc),
                exc_info=True,
            )


__all__ = ["EmployeeInboxService"]
