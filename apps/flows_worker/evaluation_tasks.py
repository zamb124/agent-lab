"""TaskIQ contracts for Evaluation Lab execution."""

from typing import Annotated, cast

from taskiq import Context as TaskiqContext
from taskiq import TaskiqDepends

from apps.flows.src.container_state import require_current_container
from apps.flows.src.models.evaluation_lab import (
    EvaluationGatePolicyRunRequest,
    EvaluationMonitorCycleRequest,
    EvaluationMonitorCycleResult,
    EvaluationPendingRunJobsEnqueueResult,
    EvaluationRunState,
    EvaluationTaskiqExecutionContext,
)
from apps.flows.src.tasks.task_names import (
    TASK_ENQUEUE_PENDING_EVALUATION_RUNS,
    TASK_EXECUTE_EVALUATION_RUN,
    TASK_RUN_EVALUATION_GATE_POLICY,
    TASK_RUN_EVALUATION_MONITOR_CYCLE,
)
from apps.flows_worker.broker_core import broker
from core.context import Context, set_context
from core.tasks.kicker import kicker_for_task_name_with_log_labels
from core.tracing.context import set_current_trace_context
from core.types import JsonObject, require_json_object


async def _enqueue_created_evaluation_run(
    *,
    run_id: str,
    context_data: JsonObject,
    trace_context: JsonObject | None,
) -> None:
    container = require_current_container()
    job = await container.evaluation_lab_service.create_run_job(
        run_id,
        context_data=context_data,
        trace_context=trace_context,
    )
    _ = await container.evaluation_lab_service.mark_run_job_enqueued(run_id)
    try:
        kicker = kicker_for_task_name_with_log_labels(
            TASK_EXECUTE_EVALUATION_RUN,
            broker,
            background_kind="evaluation",
            extra_labels={"evaluation_run_id": run_id},
        )
        _ = await kicker.with_task_id(job.taskiq_task_id).kiq(
            run_id,
            context_data=context_data,
            trace_context=trace_context,
        )
    except Exception as enqueue_exc:
        _ = await container.evaluation_lab_service.mark_run_job_failed(
            run_id,
            str(enqueue_exc),
        )
        _ = await container.evaluation_lab_service.mark_run_enqueue_failed(
            run_id,
            str(enqueue_exc),
        )
        raise


@broker.task(task_name=TASK_EXECUTE_EVALUATION_RUN, queue_name="flows_worker")
async def execute_evaluation_run(
    run_id: str,
    taskiq_context: Annotated[TaskiqContext, TaskiqDepends()],
    context_data: JsonObject | None = None,
    trace_context: JsonObject | None = None,
) -> JsonObject:
    """Execute an already-created evaluation run by immutable run_id."""
    if context_data is None:
        raise ValueError("Context is required. Context must be created in middleware.")
    if trace_context:
        set_current_trace_context(trace_context)
    set_context(Context.from_dict(context_data))
    labels = taskiq_context.message.labels
    if "evaluation_run_id" not in labels:
        raise ValueError("TaskIQ label evaluation_run_id is required")
    raw_evaluation_run_id = cast(object, labels["evaluation_run_id"])
    if not isinstance(raw_evaluation_run_id, str) or not raw_evaluation_run_id.strip():
        raise ValueError("TaskIQ label evaluation_run_id must be a non-empty string")
    evaluation_run_id = raw_evaluation_run_id

    result = await require_current_container().evaluation_lab_service.execute_run_from_taskiq(
        run_id,
        EvaluationTaskiqExecutionContext(
            task_name=taskiq_context.message.task_name,
            task_id=taskiq_context.message.task_id,
            evaluation_run_id=evaluation_run_id,
        ),
    )
    return require_json_object(
        result.model_dump(mode="json", exclude_none=False),
        "execute_evaluation_run.result",
    )


@broker.task(task_name=TASK_ENQUEUE_PENDING_EVALUATION_RUNS, queue_name="flows_worker")
async def enqueue_pending_evaluation_runs(
    taskiq_context: Annotated[TaskiqContext, TaskiqDepends()],
    context_data: JsonObject | None = None,
    limit: int = 50,
) -> JsonObject:
    """Replay durable pending evaluation run jobs into TaskIQ."""
    _ = taskiq_context
    if context_data is None:
        raise ValueError("Context is required. Context must be created in middleware.")
    if limit < 1:
        raise ValueError("limit must be >= 1")
    set_context(Context.from_dict(context_data))
    container = require_current_container()
    jobs = await container.evaluation_lab_service.list_pending_run_jobs(limit)
    enqueued_run_ids: list[str] = []
    failed_run_ids: list[str] = []
    for job in jobs:
        _ = await container.evaluation_lab_service.mark_run_job_enqueued(job.run_id)
        try:
            kicker = kicker_for_task_name_with_log_labels(
                TASK_EXECUTE_EVALUATION_RUN,
                broker,
                background_kind="evaluation",
                extra_labels={"evaluation_run_id": job.run_id},
            )
            _ = await kicker.with_task_id(job.taskiq_task_id).kiq(
                job.run_id,
                context_data=job.context_data,
                trace_context=job.trace_context,
            )
            enqueued_run_ids.append(job.run_id)
        except Exception as enqueue_exc:
            _ = await container.evaluation_lab_service.mark_run_job_failed(
                job.run_id,
                str(enqueue_exc),
            )
            _ = await container.evaluation_lab_service.mark_run_enqueue_failed(
                job.run_id,
                str(enqueue_exc),
            )
            failed_run_ids.append(job.run_id)
    result = EvaluationPendingRunJobsEnqueueResult(
        enqueued_run_ids=enqueued_run_ids,
        failed_run_ids=failed_run_ids,
    )
    return require_json_object(
        result.model_dump(mode="json", exclude_none=False),
        "enqueue_pending_evaluation_runs.result",
    )


@broker.task(task_name=TASK_RUN_EVALUATION_GATE_POLICY, queue_name="flows_worker")
async def run_evaluation_gate_policy(
    gate_policy_id: str,
    request: JsonObject,
    taskiq_context: Annotated[TaskiqContext, TaskiqDepends()],
    context_data: JsonObject | None = None,
    trace_context: JsonObject | None = None,
) -> JsonObject:
    """Create and enqueue a CI/nightly evaluation run for a gate policy."""
    _ = taskiq_context
    if context_data is None:
        raise ValueError("Context is required. Context must be created in middleware.")
    if trace_context:
        set_current_trace_context(trace_context)
    set_context(Context.from_dict(context_data))
    container = require_current_container()
    created = await container.evaluation_lab_service.create_gate_policy_run(
        gate_policy_id,
        EvaluationGatePolicyRunRequest.model_validate(request),
    )
    if created.run.state == EvaluationRunState.QUEUED:
        await _enqueue_created_evaluation_run(
            run_id=created.run.run_id,
            context_data=context_data,
            trace_context=trace_context,
        )
    result = await container.evaluation_lab_service.get_run(created.run.run_id)
    return require_json_object(
        result.model_dump(mode="json", exclude_none=False),
        "run_evaluation_gate_policy.result",
    )


@broker.task(task_name=TASK_RUN_EVALUATION_MONITOR_CYCLE, queue_name="flows_worker")
async def run_evaluation_monitor_cycle(
    monitor_id: str,
    request: JsonObject,
    taskiq_context: Annotated[TaskiqContext, TaskiqDepends()],
    context_data: JsonObject | None = None,
    trace_context: JsonObject | None = None,
) -> JsonObject:
    """Sample a monitor and enqueue its configured gate run when requested."""
    _ = taskiq_context
    if context_data is None:
        raise ValueError("Context is required. Context must be created in middleware.")
    if trace_context:
        set_current_trace_context(trace_context)
    set_context(Context.from_dict(context_data))
    container = require_current_container()
    cycle = await container.evaluation_lab_service.run_monitor_cycle(
        monitor_id,
        EvaluationMonitorCycleRequest.model_validate(request),
    )
    if cycle.run is not None and cycle.run.state == EvaluationRunState.QUEUED:
        await _enqueue_created_evaluation_run(
            run_id=cycle.run.run_id,
            context_data=context_data,
            trace_context=trace_context,
        )
        run_with_cases = await container.evaluation_lab_service.get_run(cycle.run.run_id)
        cycle = EvaluationMonitorCycleResult(
            monitor=cycle.monitor,
            observations=cycle.observations,
            run=run_with_cases.run,
        )
    return require_json_object(
        cycle.model_dump(mode="json", exclude_none=False),
        "run_evaluation_monitor_cycle.result",
    )
