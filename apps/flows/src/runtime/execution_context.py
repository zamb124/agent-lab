"""Durable-исполнение flow: checkpoint, activity и code runner."""

from __future__ import annotations

from collections.abc import Sequence

from apps.flows.src.durable_execution import (
    SideEffectPolicy,
    WorkflowAppendResult,
    WorkflowEventPayload,
    WorkflowEventRecord,
    WorkflowEventType,
    WorkflowExecutionPosition,
    WorkflowStateEventSpec,
)
from apps.flows.src.durable_execution.manager import DurableWorkflowRuntime
from apps.flows.src.runners.remote import RemoteCodeRunner
from core.capabilities import CAPABILITY_LANGUAGE_SET
from core.state import ExecutionState
from core.types import JsonObject, require_json_value


class CodeRunnerRegistry:
    """Runner isolated code-runner-* по языку."""

    def runner(self, language: str) -> RemoteCodeRunner:
        if language not in CAPABILITY_LANGUAGE_SET:
            raise ValueError(f"Unsupported language: {language}")
        return RemoteCodeRunner(language)


class DurableActivityExecutor:
    """Schedule, start и complete activity в durable ledger."""

    def __init__(self, workflow_runtime: DurableWorkflowRuntime) -> None:
        self._workflow_runtime: DurableWorkflowRuntime = workflow_runtime

    async def schedule(
        self,
        *,
        session_id: str,
        activity_id: str,
        activity_type: str,
        input_payload: JsonObject,
        node_id: str | None,
        idempotency_key: str,
        side_effect_policy: SideEffectPolicy,
    ) -> JsonObject | None:
        return await self._workflow_runtime.record_activity_scheduled(
            session_id=session_id,
            activity_id=activity_id,
            activity_type=activity_type,
            input_payload=input_payload,
            node_id=node_id,
            idempotency_key=idempotency_key,
            side_effect_policy=side_effect_policy,
        )

    async def start(self, activity_id: str) -> bool:
        return await self._workflow_runtime.record_activity_started(activity_id=activity_id)

    async def complete(
        self,
        *,
        activity_id: str,
        result_json: JsonObject | None = None,
        error: str | None = None,
    ) -> bool:
        return await self._workflow_runtime.record_activity_completed(
            activity_id=activity_id,
            result_json=result_json,
            error=error,
        )

    async def execute_code_condition(
        self,
        *,
        activity_id: str,
        session_id: str,
        from_node: str | None,
        input_payload: JsonObject,
        code: str,
        language: str,
        entrypoint: str | None,
        state: ExecutionState,
        code_runners: CodeRunnerRegistry,
    ) -> bool:
        completed = await self.schedule(
            session_id=session_id,
            activity_id=activity_id,
            activity_type="code_condition",
            input_payload=input_payload,
            node_id=from_node,
            idempotency_key=activity_id,
            side_effect_policy=SideEffectPolicy.idempotent,
        )
        if completed is not None:
            result = require_json_value(completed.get("result"), "edge.code_condition.result")
            return bool(result)

        started = await self.start(activity_id)
        if not started:
            raise RuntimeError(f"Failed to mark code condition activity as started: {activity_id!r}")

        condition_state = state.model_copy(deep=True)
        runner = code_runners.runner(language)
        try:
            executed = await runner.execute_tool(code, {}, condition_state, entrypoint=entrypoint)
        except Exception as exc:
            completed_failed = await self.complete(activity_id=activity_id, error=str(exc))
            if not completed_failed:
                raise RuntimeError(
                    f"Failed to mark code condition activity as failed: {activity_id!r}"
                ) from exc
            raise ValueError(
                f"Edge code condition: execution error language={language!r}: {exc}"
            ) from exc
        condition_result = bool(executed)
        completed_ok = await self.complete(
            activity_id=activity_id,
            result_json={"result": condition_result},
        )
        if not completed_ok:
            raise RuntimeError(
                f"Failed to mark code condition activity as completed: {activity_id!r}"
            )
        return condition_result


class FlowExecutionContext:
    """Checkpoint state flow. Не отдаёт Redis, Authz и Files."""

    def __init__(
        self,
        workflow_runtime: DurableWorkflowRuntime,
        activities: DurableActivityExecutor,
        code_runners: CodeRunnerRegistry,
    ) -> None:
        self._workflow_runtime: DurableWorkflowRuntime = workflow_runtime
        self.activities: DurableActivityExecutor = activities
        self.code_runners: CodeRunnerRegistry = code_runners

    async def get_state(
        self,
        session_id: str,
        *,
        company_id: str | None = None,
    ) -> ExecutionState | None:
        return await self._workflow_runtime.get_state(session_id, company_id=company_id)

    async def state_history(
        self,
        session_id: str,
        *,
        execution_branch_id: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[list[WorkflowEventRecord], int]:
        return await self._workflow_runtime.get_state_history(
            session_id,
            execution_branch_id=execution_branch_id,
            limit=limit,
            offset=offset,
        )

    async def record_lifecycle(
        self,
        session_id: str,
        *,
        event_type: WorkflowEventType,
        payload: WorkflowEventPayload,
    ) -> WorkflowAppendResult:
        return await self._workflow_runtime.record_lifecycle_event(
            session_id,
            event_type=event_type,
            payload=payload,
        )

    async def record_state(
        self,
        session_id: str,
        state: ExecutionState | JsonObject,
        *,
        event_type: WorkflowEventType,
        payload: WorkflowEventPayload | None = None,
        snapshot: bool = False,
    ) -> WorkflowAppendResult:
        return await self._workflow_runtime.record_state_event(
            session_id,
            state,
            event_type=event_type,
            payload=payload,
            snapshot=snapshot,
        )

    async def active_position(self, session_id: str) -> WorkflowExecutionPosition | None:
        return await self._workflow_runtime.get_active_execution_position(session_id)

    async def checkpoint_state(
        self,
        flow_id: str,
        state: ExecutionState,
        *,
        event_type: WorkflowEventType,
        payload: WorkflowEventPayload | None,
    ) -> WorkflowAppendResult:
        if state.session_flow_id != flow_id:
            raise RuntimeError(
                f"Flow {flow_id!r} cannot checkpoint session for flow {state.session_flow_id!r}"
            )
        return await self._workflow_runtime.record_state_event(
            state.session_id,
            state,
            event_type=event_type,
            payload=payload,
        )

    async def checkpoint_state_events(
        self,
        flow_id: str,
        events: Sequence[WorkflowStateEventSpec],
    ) -> list[WorkflowAppendResult]:
        if not events:
            return []
        for event in events:
            state = (
                ExecutionState.model_validate(event.state)
                if isinstance(event.state, dict)
                else event.state
            )
            if state.session_flow_id != flow_id:
                raise RuntimeError(
                    f"Flow {flow_id!r} cannot checkpoint session for flow {state.session_flow_id!r}"
                )
        first = events[0]
        session_id = (
            first.state.session_id
            if isinstance(first.state, ExecutionState)
            else str(first.state["session_id"])
        )
        return await self._workflow_runtime.record_state_events(session_id, events)


def execution_context_for(workflow_runtime: DurableWorkflowRuntime) -> FlowExecutionContext:
    runners = CodeRunnerRegistry()
    return FlowExecutionContext(
        workflow_runtime,
        DurableActivityExecutor(workflow_runtime),
        runners,
    )
