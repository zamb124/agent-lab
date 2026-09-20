"""Evaluation Lab: один `op_*` на verb для REST и WS RPC."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Never, TypeVar

from apps.flows.realtime.operations import (
    FlowsEmptyPayload,
    require_company_member,
)
from apps.flows.src.container import FlowContainer
from apps.flows.src.evaluation.lab_service import (
    EvaluationLabNotFoundError,
)
from apps.flows.src.models.evaluation_lab import (
    EvaluationActiveMonitorCyclesRequest,
    EvaluationActiveMonitorCyclesResult,
    EvaluationAnnotation,
    EvaluationAnnotationCreateRequest,
    EvaluationAnnotationIdPayload,
    EvaluationAnnotationUpdateRequest,
    EvaluationBaseline,
    EvaluationBaselineComparePayload,
    EvaluationBaselineComparison,
    EvaluationBaselineItemPayload,
    EvaluationBaselineSetRequest,
    EvaluationBuiltinEvaluatorCatalog,
    EvaluationCase,
    EvaluationCaseCreateRequest,
    EvaluationCaseImportRequest,
    EvaluationCaseImportResult,
    EvaluationCaseRun,
    EvaluationCaseRunCaseCreateRequest,
    EvaluationCaseRunIdPayload,
    EvaluationCaseRunTrace,
    EvaluationCaseUpdateRequest,
    EvaluationCompareRunsPayload,
    EvaluationDeletedResponse,
    EvaluationDialogCaseCreateRequest,
    EvaluationEventsPagePayload,
    EvaluationFlowIdPayload,
    EvaluationGatePolicy,
    EvaluationGatePolicyCreateRequest,
    EvaluationGatePolicyIdPayload,
    EvaluationGatePolicyRunRequest,
    EvaluationGatePolicyUpdateRequest,
    EvaluationGateResult,
    EvaluationMatrixPayload,
    EvaluationMonitor,
    EvaluationMonitorCreateRequest,
    EvaluationMonitorCycleRequest,
    EvaluationMonitorCycleResult,
    EvaluationMonitorIdPayload,
    EvaluationMonitorObservation,
    EvaluationMonitorObservationCaseCreateRequest,
    EvaluationMonitorObservationCurationResult,
    EvaluationMonitorObservationsPayload,
    EvaluationMonitorSampleRequest,
    EvaluationMonitorSampleResult,
    EvaluationMonitorUpdateRequest,
    EvaluationPairwiseJudgeRequest,
    EvaluationPairwiseJudgment,
    EvaluationPendingJobsPayload,
    EvaluationPendingRunJobsEnqueueResult,
    EvaluationResultsMatrix,
    EvaluationRubric,
    EvaluationRubricCreateRequest,
    EvaluationRubricIdPayload,
    EvaluationRubricUpdateRequest,
    EvaluationRubricVersion,
    EvaluationRubricVersionCreateRequest,
    EvaluationRubricWithVersion,
    EvaluationRun,
    EvaluationRunComparison,
    EvaluationRunCreateRequest,
    EvaluationRunEvent,
    EvaluationRunEventsPage,
    EvaluationRunIdPayload,
    EvaluationRunJobState,
    EvaluationRunsListPayload,
    EvaluationRunState,
    EvaluationRunWithCases,
    EvaluationSuite,
    EvaluationSuiteCaseIdPayload,
    EvaluationSuiteCreateRequest,
    EvaluationSuiteIdPayload,
    EvaluationSuiteUpdateRequest,
    EvaluationTraceCaseCreateRequest,
)
from apps.flows.src.tasks.task_names import TASK_EXECUTE_EVALUATION_RUN
from core.context import get_context
from core.models.identity_models import User
from core.pagination import ListResponse
from core.tasks import enqueue
from core.tracing.context import get_current_trace_context
from core.websocket import (
    raise_invalid,
    raise_not_found,
)

T = TypeVar("T")


def raise_evaluation(exc: Exception) -> Never:
    if isinstance(exc, EvaluationLabNotFoundError):
        raise_not_found(exc)
    raise_invalid(exc)


async def _lab(awaitable: Awaitable[T]) -> T:
    try:
        return await awaitable
    except ValueError as exc:
        raise_evaluation(exc)


def _require_id(value: str, field: str) -> str:
    if value == "":
        raise_invalid(ValueError(f"{field} required"))
    return value


async def _enqueue_evaluation_run_job(run_id: str, container: FlowContainer) -> None:
    job = await container.evaluation_lab_service.get_run_job(run_id)
    if job.state == EvaluationRunJobState.ENQUEUED:
        return
    _ = await container.evaluation_lab_service.mark_run_job_enqueued(run_id)
    try:
        _ = await enqueue(
            TASK_EXECUTE_EVALUATION_RUN,
            run_id,
            context_data=job.context_data,
            trace_context=job.trace_context,
            background_kind="evaluation",
            extra_labels={"evaluation_run_id": run_id},
            taskiq_task_id=job.taskiq_task_id,
        )
    except Exception as enqueue_exc:
        _ = await container.evaluation_lab_service.mark_run_job_failed(run_id, str(enqueue_exc))
        _ = await container.evaluation_lab_service.mark_run_enqueue_failed(
            run_id,
            str(enqueue_exc),
        )
        raise


async def _create_run_job_and_enqueue(run_id: str, container: FlowContainer) -> None:
    context = get_context()
    if context is None:
        raise_invalid(ValueError("Context is required to enqueue evaluation run"))
    _ = await container.evaluation_lab_service.create_run_job(
        run_id,
        context_data=context.to_dict(),
        trace_context=get_current_trace_context(),
    )
    await _enqueue_evaluation_run_job(run_id, container)


async def _enqueue_run_from_cycle(
    cycle: EvaluationMonitorCycleResult,
    container: FlowContainer,
) -> EvaluationMonitorCycleResult:
    if cycle.run is not None and cycle.run.state == EvaluationRunState.QUEUED:
        await _create_run_job_and_enqueue(cycle.run.run_id, container)
        run_with_cases = await _lab(container.evaluation_lab_service.get_run(cycle.run.run_id))
        return cycle.model_copy(update={"run": run_with_cases.run})
    return cycle


async def op_flows_evaluation_evaluator_catalog(
    payload: FlowsEmptyPayload,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationBuiltinEvaluatorCatalog:
    _ = payload
    _ = user
    _ = await require_company_member(container)
    return container.evaluation_lab_service.list_builtin_evaluators()


async def op_flows_evaluation_suite_create(
    payload: EvaluationSuiteCreateRequest,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationSuite:
    _ = user
    _ = await require_company_member(container)
    return await _lab(container.evaluation_lab_service.create_suite(payload))


async def op_flows_evaluation_suites_list(
    payload: EvaluationFlowIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> ListResponse[EvaluationSuite]:
    _ = user
    _ = await require_company_member(container)
    return ListResponse(
        items=await _lab(container.evaluation_lab_service.list_suites(payload.flow_id))
    )


async def op_flows_evaluation_suite_item(
    payload: EvaluationSuiteIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationSuite:
    _ = user
    _ = await require_company_member(container)
    return await _lab(container.evaluation_lab_service.get_suite(payload.suite_id))


async def op_flows_evaluation_suite_update(
    payload: EvaluationSuiteUpdateRequest,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationSuite:
    _ = user
    _ = await require_company_member(container)
    suite_id = _require_id(payload.suite_id, "suite_id")
    return await _lab(container.evaluation_lab_service.update_suite(suite_id, payload))


async def op_flows_evaluation_suite_archive(
    payload: EvaluationSuiteIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationSuite:
    _ = user
    _ = await require_company_member(container)
    return await _lab(container.evaluation_lab_service.archive_suite(payload.suite_id))


async def op_flows_evaluation_case_create(
    payload: EvaluationCaseCreateRequest,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationCase:
    _ = user
    _ = await require_company_member(container)
    suite_id = _require_id(payload.suite_id, "suite_id")
    return await _lab(container.evaluation_lab_service.create_case(suite_id, payload))


async def op_flows_evaluation_cases_list(
    payload: EvaluationSuiteIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> ListResponse[EvaluationCase]:
    _ = user
    _ = await require_company_member(container)
    return ListResponse(
        items=await _lab(container.evaluation_lab_service.list_cases(payload.suite_id))
    )


async def op_flows_evaluation_case_item(
    payload: EvaluationSuiteCaseIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationCase:
    _ = user
    _ = await require_company_member(container)
    return await _lab(
        container.evaluation_lab_service.get_case(payload.suite_id, payload.case_id)
    )


async def op_flows_evaluation_case_update(
    payload: EvaluationCaseUpdateRequest,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationCase:
    _ = user
    _ = await require_company_member(container)
    suite_id = _require_id(payload.suite_id, "suite_id")
    case_id = _require_id(payload.case_id, "case_id")
    return await _lab(
        container.evaluation_lab_service.update_case(suite_id, case_id, payload)
    )


async def op_flows_evaluation_case_delete(
    payload: EvaluationSuiteCaseIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationDeletedResponse:
    _ = user
    _ = await require_company_member(container)
    await _lab(container.evaluation_lab_service.delete_case(payload.suite_id, payload.case_id))
    return EvaluationDeletedResponse()


async def op_flows_evaluation_case_import(
    payload: EvaluationCaseImportRequest,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationCaseImportResult:
    _ = user
    _ = await require_company_member(container)
    suite_id = _require_id(payload.suite_id, "suite_id")
    return await _lab(container.evaluation_lab_service.import_cases(suite_id, payload))


async def op_flows_evaluation_case_from_dialog(
    payload: EvaluationDialogCaseCreateRequest,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationCase:
    _ = user
    _ = await require_company_member(container)
    suite_id = _require_id(payload.suite_id, "suite_id")
    return await _lab(
        container.evaluation_lab_service.create_case_from_dialog(suite_id, payload)
    )


async def op_flows_evaluation_case_from_case_run(
    payload: EvaluationCaseRunCaseCreateRequest,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationCase:
    _ = user
    _ = await require_company_member(container)
    suite_id = _require_id(payload.suite_id, "suite_id")
    return await _lab(
        container.evaluation_lab_service.create_case_from_case_run(suite_id, payload)
    )


async def op_flows_evaluation_case_from_trace(
    payload: EvaluationTraceCaseCreateRequest,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationCase:
    _ = user
    _ = await require_company_member(container)
    suite_id = _require_id(payload.suite_id, "suite_id")
    return await _lab(
        container.evaluation_lab_service.create_case_from_trace(suite_id, payload)
    )


async def op_flows_evaluation_rubric_create(
    payload: EvaluationRubricCreateRequest,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationRubricWithVersion:
    _ = user
    _ = await require_company_member(container)
    try:
        rubric, version = await container.evaluation_lab_service.create_rubric(payload)
    except ValueError as exc:
        raise_evaluation(exc)
    return EvaluationRubricWithVersion(rubric=rubric, version=version)


async def op_flows_evaluation_rubrics_list(
    payload: EvaluationFlowIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> ListResponse[EvaluationRubric]:
    _ = user
    _ = await require_company_member(container)
    return ListResponse(
        items=await _lab(container.evaluation_lab_service.list_rubrics(payload.flow_id))
    )


async def op_flows_evaluation_rubric_item(
    payload: EvaluationRubricIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationRubric:
    _ = user
    _ = await require_company_member(container)
    return await _lab(container.evaluation_lab_service.get_rubric(payload.rubric_id))


async def op_flows_evaluation_rubric_update(
    payload: EvaluationRubricUpdateRequest,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationRubric:
    _ = user
    _ = await require_company_member(container)
    rubric_id = _require_id(payload.rubric_id, "rubric_id")
    return await _lab(container.evaluation_lab_service.update_rubric(rubric_id, payload))


async def op_flows_evaluation_rubric_archive(
    payload: EvaluationRubricIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationRubric:
    _ = user
    _ = await require_company_member(container)
    return await _lab(container.evaluation_lab_service.archive_rubric(payload.rubric_id))


async def op_flows_evaluation_rubric_version_create(
    payload: EvaluationRubricVersionCreateRequest,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationRubricVersion:
    _ = user
    _ = await require_company_member(container)
    rubric_id = _require_id(payload.rubric_id, "rubric_id")
    return await _lab(
        container.evaluation_lab_service.create_rubric_version(rubric_id, payload)
    )


async def op_flows_evaluation_rubric_versions_list(
    payload: EvaluationRubricIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> ListResponse[EvaluationRubricVersion]:
    _ = user
    _ = await require_company_member(container)
    return ListResponse(
        items=await _lab(
            container.evaluation_lab_service.list_rubric_versions(payload.rubric_id)
        )
    )


async def op_flows_evaluation_run_create(
    payload: EvaluationRunCreateRequest,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationRunWithCases:
    _ = user
    _ = await require_company_member(container)
    created = await _lab(container.evaluation_lab_service.create_run(payload))
    if created.run.state == EvaluationRunState.QUEUED:
        await _create_run_job_and_enqueue(created.run.run_id, container)
    return await _lab(container.evaluation_lab_service.get_run(created.run.run_id))


async def op_flows_evaluation_compare_runs(
    payload: EvaluationCompareRunsPayload,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationRunComparison:
    _ = user
    _ = await require_company_member(container)
    return await _lab(
        container.evaluation_lab_service.compare_runs(
            payload.left_run_id,
            payload.right_run_id,
        )
    )


async def op_flows_evaluation_run_jobs_enqueue_pending(
    payload: EvaluationPendingJobsPayload,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationPendingRunJobsEnqueueResult:
    _ = user
    _ = await require_company_member(container)
    enqueued_run_ids: list[str] = []
    failed_run_ids: list[str] = []
    jobs = await _lab(container.evaluation_lab_service.list_pending_run_jobs(payload.limit))
    for job in jobs:
        try:
            await _enqueue_evaluation_run_job(job.run_id, container)
        except Exception:
            failed_run_ids.append(job.run_id)
            continue
        enqueued_run_ids.append(job.run_id)
    return EvaluationPendingRunJobsEnqueueResult(
        enqueued_run_ids=enqueued_run_ids,
        failed_run_ids=failed_run_ids,
    )


async def op_flows_evaluation_run_get(
    payload: EvaluationRunIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationRunWithCases:
    _ = user
    _ = await require_company_member(container)
    return await _lab(container.evaluation_lab_service.get_run(payload.run_id))


async def op_flows_evaluation_run_cancel(
    payload: EvaluationRunIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationRunWithCases:
    _ = user
    _ = await require_company_member(container)
    return await _lab(container.evaluation_lab_service.cancel_run(payload.run_id))


async def op_flows_evaluation_run_cases(
    payload: EvaluationRunIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> ListResponse[EvaluationCaseRun]:
    _ = user
    _ = await require_company_member(container)
    return ListResponse(
        items=await _lab(container.evaluation_lab_service.list_case_runs(payload.run_id))
    )


async def op_flows_evaluation_run_events(
    payload: EvaluationRunIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> ListResponse[EvaluationRunEvent]:
    _ = user
    _ = await require_company_member(container)
    return ListResponse(
        items=await _lab(container.evaluation_lab_service.list_events(payload.run_id))
    )


async def op_flows_evaluation_run_events_page(
    payload: EvaluationEventsPagePayload,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationRunEventsPage:
    _ = user
    _ = await require_company_member(container)
    return await _lab(
        container.evaluation_lab_service.list_events_page(
            payload.run_id,
            after_sequence=payload.after_sequence,
            limit=payload.limit,
        )
    )


async def op_flows_evaluation_case_run_trace(
    payload: EvaluationCaseRunIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationCaseRunTrace:
    _ = user
    _ = await require_company_member(container)
    return await _lab(
        container.evaluation_lab_service.get_case_run_trace(payload.case_run_id)
    )


async def op_flows_evaluation_pairwise_judgment_create(
    payload: EvaluationPairwiseJudgeRequest,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationPairwiseJudgment:
    _ = user
    _ = await require_company_member(container)
    return await _lab(container.evaluation_lab_service.create_pairwise_judgment(payload))


async def op_flows_evaluation_pairwise_judgments_list(
    payload: EvaluationCaseRunIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> ListResponse[EvaluationPairwiseJudgment]:
    _ = user
    _ = await require_company_member(container)
    return ListResponse(
        items=await _lab(
            container.evaluation_lab_service.list_pairwise_judgments_for_case_run(
                payload.case_run_id,
            )
        )
    )


async def op_flows_evaluation_annotation_create(
    payload: EvaluationAnnotationCreateRequest,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationAnnotation:
    _ = user
    _ = await require_company_member(container)
    run_id = _require_id(payload.run_id, "run_id")
    return await _lab(container.evaluation_lab_service.create_annotation(run_id, payload))


async def op_flows_evaluation_annotations_list(
    payload: EvaluationRunIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> ListResponse[EvaluationAnnotation]:
    _ = user
    _ = await require_company_member(container)
    return ListResponse(
        items=await _lab(container.evaluation_lab_service.list_annotations(payload.run_id))
    )


async def op_flows_evaluation_annotation_update(
    payload: EvaluationAnnotationUpdateRequest,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationAnnotation:
    _ = user
    _ = await require_company_member(container)
    annotation_id = _require_id(payload.annotation_id, "annotation_id")
    return await _lab(
        container.evaluation_lab_service.update_annotation(annotation_id, payload)
    )


async def op_flows_evaluation_annotation_delete(
    payload: EvaluationAnnotationIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationDeletedResponse:
    _ = user
    _ = await require_company_member(container)
    await _lab(container.evaluation_lab_service.delete_annotation(payload.annotation_id))
    return EvaluationDeletedResponse()


async def op_flows_evaluation_runs_list(
    payload: EvaluationRunsListPayload,
    *,
    user: User,
    container: FlowContainer,
) -> ListResponse[EvaluationRun]:
    _ = user
    _ = await require_company_member(container)
    return ListResponse(
        items=await _lab(
            container.evaluation_lab_service.list_runs(payload.suite_id, payload.limit)
        )
    )


async def op_flows_evaluation_matrix_get(
    payload: EvaluationMatrixPayload,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationResultsMatrix:
    _ = user
    _ = await require_company_member(container)
    return await _lab(
        container.evaluation_lab_service.get_results_matrix(
            payload.suite_id,
            payload.branch_id,
            payload.limit,
        )
    )


async def op_flows_evaluation_baseline_set(
    payload: EvaluationBaselineSetRequest,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationBaseline:
    _ = user
    _ = await require_company_member(container)
    suite_id = _require_id(payload.suite_id, "suite_id")
    branch_id = _require_id(payload.branch_id, "branch_id")
    return await _lab(
        container.evaluation_lab_service.set_baseline(suite_id, branch_id, payload)
    )


async def op_flows_evaluation_baselines_list(
    payload: EvaluationSuiteIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> ListResponse[EvaluationBaseline]:
    _ = user
    _ = await require_company_member(container)
    return ListResponse(
        items=await _lab(container.evaluation_lab_service.list_baselines(payload.suite_id))
    )


async def op_flows_evaluation_baseline_item(
    payload: EvaluationBaselineItemPayload,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationBaseline:
    _ = user
    _ = await require_company_member(container)
    return await _lab(
        container.evaluation_lab_service.get_baseline(payload.suite_id, payload.branch_id)
    )


async def op_flows_evaluation_baseline_compare(
    payload: EvaluationBaselineComparePayload,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationBaselineComparison:
    _ = user
    _ = await require_company_member(container)
    return await _lab(
        container.evaluation_lab_service.compare_with_baseline(
            payload.suite_id,
            payload.branch_id,
            payload.run_id,
        )
    )


async def op_flows_evaluation_gate_policy_create(
    payload: EvaluationGatePolicyCreateRequest,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationGatePolicy:
    _ = user
    _ = await require_company_member(container)
    suite_id = _require_id(payload.suite_id, "suite_id")
    return await _lab(container.evaluation_lab_service.create_gate_policy(suite_id, payload))


async def op_flows_evaluation_gate_policies_list(
    payload: EvaluationSuiteIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> ListResponse[EvaluationGatePolicy]:
    _ = user
    _ = await require_company_member(container)
    return ListResponse(
        items=await _lab(
            container.evaluation_lab_service.list_gate_policies(payload.suite_id)
        )
    )


async def op_flows_evaluation_gate_policy_item(
    payload: EvaluationGatePolicyIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationGatePolicy:
    _ = user
    _ = await require_company_member(container)
    return await _lab(container.evaluation_lab_service.get_gate_policy(payload.gate_policy_id))


async def op_flows_evaluation_gate_policy_update(
    payload: EvaluationGatePolicyUpdateRequest,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationGatePolicy:
    _ = user
    _ = await require_company_member(container)
    gate_policy_id = _require_id(payload.gate_policy_id, "gate_policy_id")
    return await _lab(
        container.evaluation_lab_service.update_gate_policy(gate_policy_id, payload)
    )


async def op_flows_evaluation_gate_policy_archive(
    payload: EvaluationGatePolicyIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationGatePolicy:
    _ = user
    _ = await require_company_member(container)
    return await _lab(
        container.evaluation_lab_service.archive_gate_policy(payload.gate_policy_id)
    )


async def op_flows_evaluation_gate_policy_run(
    payload: EvaluationGatePolicyRunRequest,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationRunWithCases:
    _ = user
    _ = await require_company_member(container)
    gate_policy_id = _require_id(payload.gate_policy_id, "gate_policy_id")
    created = await _lab(
        container.evaluation_lab_service.create_gate_policy_run(gate_policy_id, payload)
    )
    if created.run.state == EvaluationRunState.QUEUED:
        await _create_run_job_and_enqueue(created.run.run_id, container)
    return await _lab(container.evaluation_lab_service.get_run(created.run.run_id))


async def op_flows_evaluation_gate_result(
    payload: EvaluationRunIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationGateResult:
    _ = user
    _ = await require_company_member(container)
    return await _lab(container.evaluation_lab_service.get_gate_result(payload.run_id))


async def op_flows_evaluation_monitor_create(
    payload: EvaluationMonitorCreateRequest,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationMonitor:
    _ = user
    _ = await require_company_member(container)
    return await _lab(container.evaluation_lab_service.create_monitor(payload))


async def op_flows_evaluation_monitor_cycles_run_active(
    payload: EvaluationActiveMonitorCyclesRequest,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationActiveMonitorCyclesResult:
    _ = user
    _ = await require_company_member(container)
    cycles = await _lab(
        container.evaluation_lab_service.run_active_monitor_cycles(
            limit_per_monitor=payload.limit_per_monitor,
            enqueue_gate_runs=payload.enqueue_gate_runs,
            trials=payload.trials,
            max_concurrency=payload.max_concurrency,
        )
    )
    enqueued_cycles: list[EvaluationMonitorCycleResult] = []
    for cycle in cycles:
        enqueued_cycles.append(await _enqueue_run_from_cycle(cycle, container))
    return EvaluationActiveMonitorCyclesResult(cycles=enqueued_cycles)


async def op_flows_evaluation_monitors_list(
    payload: EvaluationSuiteIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> ListResponse[EvaluationMonitor]:
    _ = user
    _ = await require_company_member(container)
    return ListResponse(
        items=await _lab(container.evaluation_lab_service.list_monitors(payload.suite_id))
    )


async def op_flows_evaluation_monitor_item(
    payload: EvaluationMonitorIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationMonitor:
    _ = user
    _ = await require_company_member(container)
    return await _lab(container.evaluation_lab_service.get_monitor(payload.monitor_id))


async def op_flows_evaluation_monitor_update(
    payload: EvaluationMonitorUpdateRequest,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationMonitor:
    _ = user
    _ = await require_company_member(container)
    monitor_id = _require_id(payload.monitor_id, "monitor_id")
    return await _lab(container.evaluation_lab_service.update_monitor(monitor_id, payload))


async def op_flows_evaluation_monitor_archive(
    payload: EvaluationMonitorIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationMonitor:
    _ = user
    _ = await require_company_member(container)
    return await _lab(container.evaluation_lab_service.archive_monitor(payload.monitor_id))


async def op_flows_evaluation_monitor_sample(
    payload: EvaluationMonitorSampleRequest,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationMonitorSampleResult:
    _ = user
    _ = await require_company_member(container)
    monitor_id = _require_id(payload.monitor_id, "monitor_id")
    return await _lab(container.evaluation_lab_service.sample_monitor(monitor_id, payload))


async def op_flows_evaluation_monitor_run_cycle(
    payload: EvaluationMonitorCycleRequest,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationMonitorCycleResult:
    _ = user
    _ = await require_company_member(container)
    monitor_id = _require_id(payload.monitor_id, "monitor_id")
    cycle = await _lab(container.evaluation_lab_service.run_monitor_cycle(monitor_id, payload))
    return await _enqueue_run_from_cycle(cycle, container)


async def op_flows_evaluation_monitor_observation_case_create(
    payload: EvaluationMonitorObservationCaseCreateRequest,
    *,
    user: User,
    container: FlowContainer,
) -> EvaluationMonitorObservationCurationResult:
    _ = user
    _ = await require_company_member(container)
    monitor_id = _require_id(payload.monitor_id, "monitor_id")
    trace_id = _require_id(payload.trace_id, "trace_id")
    return await _lab(
        container.evaluation_lab_service.create_case_from_monitor_observation(
            monitor_id,
            trace_id,
            payload,
        )
    )


async def op_flows_evaluation_monitor_observations(
    payload: EvaluationMonitorObservationsPayload,
    *,
    user: User,
    container: FlowContainer,
) -> ListResponse[EvaluationMonitorObservation]:
    _ = user
    _ = await require_company_member(container)
    return ListResponse(
        items=await _lab(
            container.evaluation_lab_service.list_monitor_observations(
                payload.monitor_id,
                payload.limit,
            )
        )
    )
