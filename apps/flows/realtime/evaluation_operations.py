"""Evaluation Lab: один `op_*` на verb для REST и WS RPC."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Never, TypeVar

from apps.flows.di import Di
from apps.flows.realtime.operations import (
    require_company_member,
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
from core.errors.boundary import PlatformNotFoundError
from core.models.identity_models import User
from core.pagination import ListResponse
from core.tasks import enqueue
from core.tracing.context import get_current_trace_context
from core.websocket import (
    EmptyPayload,
    raise_invalid,
    raise_not_found,
)

T = TypeVar("T")


def raise_evaluation(exc: Exception) -> Never:
    if isinstance(exc, PlatformNotFoundError):
        raise_not_found(exc)
    raise_invalid(exc)


async def _lab(awaitable: Awaitable[T]) -> T:
    try:
        return await awaitable
    except (ValueError, PlatformNotFoundError) as exc:
        raise_evaluation(exc)


def _require_id(value: str, field: str) -> str:
    if value == "":
        raise_invalid(ValueError(f"{field} required"))
    return value


async def _enqueue_evaluation_run_job(run_id: str, di: Di) -> None:
    job = await di.evaluation_lab_service.get_run_job(run_id)
    if job.state == EvaluationRunJobState.ENQUEUED:
        return
    _ = await di.evaluation_lab_service.mark_run_job_enqueued(run_id)
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
        _ = await di.evaluation_lab_service.mark_run_job_failed(run_id, str(enqueue_exc))
        _ = await di.evaluation_lab_service.mark_run_enqueue_failed(
            run_id,
            str(enqueue_exc),
        )
        raise


async def _create_run_job_and_enqueue(run_id: str, di: Di) -> None:
    context = get_context()
    if context is None:
        raise_invalid(ValueError("Context is required to enqueue evaluation run"))
    _ = await di.evaluation_lab_service.create_run_job(
        run_id,
        context_data=context.to_dict(),
        trace_context=get_current_trace_context(),
    )
    await _enqueue_evaluation_run_job(run_id, di)


async def _enqueue_run_from_cycle(
    cycle: EvaluationMonitorCycleResult,
    di: Di,
) -> EvaluationMonitorCycleResult:
    if cycle.run is not None and cycle.run.state == EvaluationRunState.QUEUED:
        await _create_run_job_and_enqueue(cycle.run.run_id, di)
        run_with_cases = await _lab(di.evaluation_lab_service.get_run(cycle.run.run_id))
        return cycle.model_copy(update={"run": run_with_cases.run})
    return cycle


async def op_flows_evaluation_evaluator_catalog(
    payload: EmptyPayload,
    *,
    user: User,
    di: Di,
) -> EvaluationBuiltinEvaluatorCatalog:
    _ = payload
    _ = user
    _ = await require_company_member(di)
    return di.evaluation_lab_service.list_builtin_evaluators()


async def op_flows_evaluation_suite_create(
    payload: EvaluationSuiteCreateRequest,
    *,
    user: User,
    di: Di,
) -> EvaluationSuite:
    _ = user
    _ = await require_company_member(di)
    return await _lab(di.evaluation_lab_service.create_suite(payload))


async def op_flows_evaluation_suites_list(
    payload: EvaluationFlowIdPayload,
    *,
    user: User,
    di: Di,
) -> ListResponse[EvaluationSuite]:
    _ = user
    _ = await require_company_member(di)
    return ListResponse(
        items=await _lab(di.evaluation_lab_service.list_suites(payload.flow_id))
    )


async def op_flows_evaluation_suite_item(
    payload: EvaluationSuiteIdPayload,
    *,
    user: User,
    di: Di,
) -> EvaluationSuite:
    _ = user
    _ = await require_company_member(di)
    return await _lab(di.evaluation_lab_service.get_suite(payload.suite_id))


async def op_flows_evaluation_suite_update(
    payload: EvaluationSuiteUpdateRequest,
    *,
    user: User,
    di: Di,
) -> EvaluationSuite:
    _ = user
    _ = await require_company_member(di)
    suite_id = _require_id(payload.suite_id, "suite_id")
    return await _lab(di.evaluation_lab_service.update_suite(suite_id, payload))


async def op_flows_evaluation_suite_archive(
    payload: EvaluationSuiteIdPayload,
    *,
    user: User,
    di: Di,
) -> EvaluationSuite:
    _ = user
    _ = await require_company_member(di)
    return await _lab(di.evaluation_lab_service.archive_suite(payload.suite_id))


async def op_flows_evaluation_case_create(
    payload: EvaluationCaseCreateRequest,
    *,
    user: User,
    di: Di,
) -> EvaluationCase:
    _ = user
    _ = await require_company_member(di)
    suite_id = _require_id(payload.suite_id, "suite_id")
    return await _lab(di.evaluation_lab_service.create_case(suite_id, payload))


async def op_flows_evaluation_cases_list(
    payload: EvaluationSuiteIdPayload,
    *,
    user: User,
    di: Di,
) -> ListResponse[EvaluationCase]:
    _ = user
    _ = await require_company_member(di)
    return ListResponse(
        items=await _lab(di.evaluation_lab_service.list_cases(payload.suite_id))
    )


async def op_flows_evaluation_case_item(
    payload: EvaluationSuiteCaseIdPayload,
    *,
    user: User,
    di: Di,
) -> EvaluationCase:
    _ = user
    _ = await require_company_member(di)
    return await _lab(
        di.evaluation_lab_service.get_case(payload.suite_id, payload.case_id)
    )


async def op_flows_evaluation_case_update(
    payload: EvaluationCaseUpdateRequest,
    *,
    user: User,
    di: Di,
) -> EvaluationCase:
    _ = user
    _ = await require_company_member(di)
    suite_id = _require_id(payload.suite_id, "suite_id")
    case_id = _require_id(payload.case_id, "case_id")
    return await _lab(
        di.evaluation_lab_service.update_case(suite_id, case_id, payload)
    )


async def op_flows_evaluation_case_delete(
    payload: EvaluationSuiteCaseIdPayload,
    *,
    user: User,
    di: Di,
) -> EvaluationDeletedResponse:
    _ = user
    _ = await require_company_member(di)
    await _lab(di.evaluation_lab_service.delete_case(payload.suite_id, payload.case_id))
    return EvaluationDeletedResponse()


async def op_flows_evaluation_case_import(
    payload: EvaluationCaseImportRequest,
    *,
    user: User,
    di: Di,
) -> EvaluationCaseImportResult:
    _ = user
    _ = await require_company_member(di)
    suite_id = _require_id(payload.suite_id, "suite_id")
    return await _lab(di.evaluation_lab_service.import_cases(suite_id, payload))


async def op_flows_evaluation_case_from_dialog(
    payload: EvaluationDialogCaseCreateRequest,
    *,
    user: User,
    di: Di,
) -> EvaluationCase:
    _ = user
    _ = await require_company_member(di)
    suite_id = _require_id(payload.suite_id, "suite_id")
    return await _lab(
        di.evaluation_lab_service.create_case_from_dialog(suite_id, payload)
    )


async def op_flows_evaluation_case_from_case_run(
    payload: EvaluationCaseRunCaseCreateRequest,
    *,
    user: User,
    di: Di,
) -> EvaluationCase:
    _ = user
    _ = await require_company_member(di)
    suite_id = _require_id(payload.suite_id, "suite_id")
    return await _lab(
        di.evaluation_lab_service.create_case_from_case_run(suite_id, payload)
    )


async def op_flows_evaluation_case_from_trace(
    payload: EvaluationTraceCaseCreateRequest,
    *,
    user: User,
    di: Di,
) -> EvaluationCase:
    _ = user
    _ = await require_company_member(di)
    suite_id = _require_id(payload.suite_id, "suite_id")
    return await _lab(
        di.evaluation_lab_service.create_case_from_trace(suite_id, payload)
    )


async def op_flows_evaluation_rubric_create(
    payload: EvaluationRubricCreateRequest,
    *,
    user: User,
    di: Di,
) -> EvaluationRubricWithVersion:
    _ = user
    _ = await require_company_member(di)
    try:
        rubric, version = await di.evaluation_lab_service.create_rubric(payload)
    except (ValueError, PlatformNotFoundError) as exc:
        raise_evaluation(exc)
    return EvaluationRubricWithVersion(rubric=rubric, version=version)


async def op_flows_evaluation_rubrics_list(
    payload: EvaluationFlowIdPayload,
    *,
    user: User,
    di: Di,
) -> ListResponse[EvaluationRubric]:
    _ = user
    _ = await require_company_member(di)
    return ListResponse(
        items=await _lab(di.evaluation_lab_service.list_rubrics(payload.flow_id))
    )


async def op_flows_evaluation_rubric_item(
    payload: EvaluationRubricIdPayload,
    *,
    user: User,
    di: Di,
) -> EvaluationRubric:
    _ = user
    _ = await require_company_member(di)
    return await _lab(di.evaluation_lab_service.get_rubric(payload.rubric_id))


async def op_flows_evaluation_rubric_update(
    payload: EvaluationRubricUpdateRequest,
    *,
    user: User,
    di: Di,
) -> EvaluationRubric:
    _ = user
    _ = await require_company_member(di)
    rubric_id = _require_id(payload.rubric_id, "rubric_id")
    return await _lab(di.evaluation_lab_service.update_rubric(rubric_id, payload))


async def op_flows_evaluation_rubric_archive(
    payload: EvaluationRubricIdPayload,
    *,
    user: User,
    di: Di,
) -> EvaluationRubric:
    _ = user
    _ = await require_company_member(di)
    return await _lab(di.evaluation_lab_service.archive_rubric(payload.rubric_id))


async def op_flows_evaluation_rubric_version_create(
    payload: EvaluationRubricVersionCreateRequest,
    *,
    user: User,
    di: Di,
) -> EvaluationRubricVersion:
    _ = user
    _ = await require_company_member(di)
    rubric_id = _require_id(payload.rubric_id, "rubric_id")
    return await _lab(
        di.evaluation_lab_service.create_rubric_version(rubric_id, payload)
    )


async def op_flows_evaluation_rubric_versions_list(
    payload: EvaluationRubricIdPayload,
    *,
    user: User,
    di: Di,
) -> ListResponse[EvaluationRubricVersion]:
    _ = user
    _ = await require_company_member(di)
    return ListResponse(
        items=await _lab(
            di.evaluation_lab_service.list_rubric_versions(payload.rubric_id)
        )
    )


async def op_flows_evaluation_run_create(
    payload: EvaluationRunCreateRequest,
    *,
    user: User,
    di: Di,
) -> EvaluationRunWithCases:
    _ = user
    _ = await require_company_member(di)
    created = await _lab(di.evaluation_lab_service.create_run(payload))
    if created.run.state == EvaluationRunState.QUEUED:
        await _create_run_job_and_enqueue(created.run.run_id, di)
    return await _lab(di.evaluation_lab_service.get_run(created.run.run_id))


async def op_flows_evaluation_compare_runs(
    payload: EvaluationCompareRunsPayload,
    *,
    user: User,
    di: Di,
) -> EvaluationRunComparison:
    _ = user
    _ = await require_company_member(di)
    return await _lab(
        di.evaluation_lab_service.compare_runs(
            payload.left_run_id,
            payload.right_run_id,
        )
    )


async def op_flows_evaluation_run_jobs_enqueue_pending(
    payload: EvaluationPendingJobsPayload,
    *,
    user: User,
    di: Di,
) -> EvaluationPendingRunJobsEnqueueResult:
    _ = user
    _ = await require_company_member(di)
    enqueued_run_ids: list[str] = []
    failed_run_ids: list[str] = []
    jobs = await _lab(di.evaluation_lab_service.list_pending_run_jobs(payload.limit))
    for job in jobs:
        try:
            await _enqueue_evaluation_run_job(job.run_id, di)
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
    di: Di,
) -> EvaluationRunWithCases:
    _ = user
    _ = await require_company_member(di)
    return await _lab(di.evaluation_lab_service.get_run(payload.run_id))


async def op_flows_evaluation_run_cancel(
    payload: EvaluationRunIdPayload,
    *,
    user: User,
    di: Di,
) -> EvaluationRunWithCases:
    _ = user
    _ = await require_company_member(di)
    return await _lab(di.evaluation_lab_service.cancel_run(payload.run_id))


async def op_flows_evaluation_run_cases(
    payload: EvaluationRunIdPayload,
    *,
    user: User,
    di: Di,
) -> ListResponse[EvaluationCaseRun]:
    _ = user
    _ = await require_company_member(di)
    return ListResponse(
        items=await _lab(di.evaluation_lab_service.list_case_runs(payload.run_id))
    )


async def op_flows_evaluation_run_events(
    payload: EvaluationRunIdPayload,
    *,
    user: User,
    di: Di,
) -> ListResponse[EvaluationRunEvent]:
    _ = user
    _ = await require_company_member(di)
    return ListResponse(
        items=await _lab(di.evaluation_lab_service.list_events(payload.run_id))
    )


async def op_flows_evaluation_run_events_page(
    payload: EvaluationEventsPagePayload,
    *,
    user: User,
    di: Di,
) -> EvaluationRunEventsPage:
    _ = user
    _ = await require_company_member(di)
    return await _lab(
        di.evaluation_lab_service.list_events_page(
            payload.run_id,
            after_sequence=payload.after_sequence,
            limit=payload.limit,
        )
    )


async def op_flows_evaluation_case_run_trace(
    payload: EvaluationCaseRunIdPayload,
    *,
    user: User,
    di: Di,
) -> EvaluationCaseRunTrace:
    _ = user
    _ = await require_company_member(di)
    return await _lab(
        di.evaluation_lab_service.get_case_run_trace(payload.case_run_id)
    )


async def op_flows_evaluation_pairwise_judgment_create(
    payload: EvaluationPairwiseJudgeRequest,
    *,
    user: User,
    di: Di,
) -> EvaluationPairwiseJudgment:
    _ = user
    _ = await require_company_member(di)
    return await _lab(di.evaluation_lab_service.create_pairwise_judgment(payload))


async def op_flows_evaluation_pairwise_judgments_list(
    payload: EvaluationCaseRunIdPayload,
    *,
    user: User,
    di: Di,
) -> ListResponse[EvaluationPairwiseJudgment]:
    _ = user
    _ = await require_company_member(di)
    return ListResponse(
        items=await _lab(
            di.evaluation_lab_service.list_pairwise_judgments_for_case_run(
                payload.case_run_id,
            )
        )
    )


async def op_flows_evaluation_annotation_create(
    payload: EvaluationAnnotationCreateRequest,
    *,
    user: User,
    di: Di,
) -> EvaluationAnnotation:
    _ = user
    _ = await require_company_member(di)
    run_id = _require_id(payload.run_id, "run_id")
    return await _lab(di.evaluation_lab_service.create_annotation(run_id, payload))


async def op_flows_evaluation_annotations_list(
    payload: EvaluationRunIdPayload,
    *,
    user: User,
    di: Di,
) -> ListResponse[EvaluationAnnotation]:
    _ = user
    _ = await require_company_member(di)
    return ListResponse(
        items=await _lab(di.evaluation_lab_service.list_annotations(payload.run_id))
    )


async def op_flows_evaluation_annotation_update(
    payload: EvaluationAnnotationUpdateRequest,
    *,
    user: User,
    di: Di,
) -> EvaluationAnnotation:
    _ = user
    _ = await require_company_member(di)
    annotation_id = _require_id(payload.annotation_id, "annotation_id")
    return await _lab(
        di.evaluation_lab_service.update_annotation(annotation_id, payload)
    )


async def op_flows_evaluation_annotation_delete(
    payload: EvaluationAnnotationIdPayload,
    *,
    user: User,
    di: Di,
) -> EvaluationDeletedResponse:
    _ = user
    _ = await require_company_member(di)
    await _lab(di.evaluation_lab_service.delete_annotation(payload.annotation_id))
    return EvaluationDeletedResponse()


async def op_flows_evaluation_runs_list(
    payload: EvaluationRunsListPayload,
    *,
    user: User,
    di: Di,
) -> ListResponse[EvaluationRun]:
    _ = user
    _ = await require_company_member(di)
    return ListResponse(
        items=await _lab(
            di.evaluation_lab_service.list_runs(payload.suite_id, payload.limit)
        )
    )


async def op_flows_evaluation_matrix_get(
    payload: EvaluationMatrixPayload,
    *,
    user: User,
    di: Di,
) -> EvaluationResultsMatrix:
    _ = user
    _ = await require_company_member(di)
    return await _lab(
        di.evaluation_lab_service.get_results_matrix(
            payload.suite_id,
            payload.branch_id,
            payload.limit,
        )
    )


async def op_flows_evaluation_baseline_set(
    payload: EvaluationBaselineSetRequest,
    *,
    user: User,
    di: Di,
) -> EvaluationBaseline:
    _ = user
    _ = await require_company_member(di)
    suite_id = _require_id(payload.suite_id, "suite_id")
    branch_id = _require_id(payload.branch_id, "branch_id")
    return await _lab(
        di.evaluation_lab_service.set_baseline(suite_id, branch_id, payload)
    )


async def op_flows_evaluation_baselines_list(
    payload: EvaluationSuiteIdPayload,
    *,
    user: User,
    di: Di,
) -> ListResponse[EvaluationBaseline]:
    _ = user
    _ = await require_company_member(di)
    return ListResponse(
        items=await _lab(di.evaluation_lab_service.list_baselines(payload.suite_id))
    )


async def op_flows_evaluation_baseline_item(
    payload: EvaluationBaselineItemPayload,
    *,
    user: User,
    di: Di,
) -> EvaluationBaseline:
    _ = user
    _ = await require_company_member(di)
    return await _lab(
        di.evaluation_lab_service.get_baseline(payload.suite_id, payload.branch_id)
    )


async def op_flows_evaluation_baseline_compare(
    payload: EvaluationBaselineComparePayload,
    *,
    user: User,
    di: Di,
) -> EvaluationBaselineComparison:
    _ = user
    _ = await require_company_member(di)
    return await _lab(
        di.evaluation_lab_service.compare_with_baseline(
            payload.suite_id,
            payload.branch_id,
            payload.run_id,
        )
    )


async def op_flows_evaluation_gate_policy_create(
    payload: EvaluationGatePolicyCreateRequest,
    *,
    user: User,
    di: Di,
) -> EvaluationGatePolicy:
    _ = user
    _ = await require_company_member(di)
    suite_id = _require_id(payload.suite_id, "suite_id")
    return await _lab(di.evaluation_lab_service.create_gate_policy(suite_id, payload))


async def op_flows_evaluation_gate_policies_list(
    payload: EvaluationSuiteIdPayload,
    *,
    user: User,
    di: Di,
) -> ListResponse[EvaluationGatePolicy]:
    _ = user
    _ = await require_company_member(di)
    return ListResponse(
        items=await _lab(
            di.evaluation_lab_service.list_gate_policies(payload.suite_id)
        )
    )


async def op_flows_evaluation_gate_policy_item(
    payload: EvaluationGatePolicyIdPayload,
    *,
    user: User,
    di: Di,
) -> EvaluationGatePolicy:
    _ = user
    _ = await require_company_member(di)
    return await _lab(di.evaluation_lab_service.get_gate_policy(payload.gate_policy_id))


async def op_flows_evaluation_gate_policy_update(
    payload: EvaluationGatePolicyUpdateRequest,
    *,
    user: User,
    di: Di,
) -> EvaluationGatePolicy:
    _ = user
    _ = await require_company_member(di)
    gate_policy_id = _require_id(payload.gate_policy_id, "gate_policy_id")
    return await _lab(
        di.evaluation_lab_service.update_gate_policy(gate_policy_id, payload)
    )


async def op_flows_evaluation_gate_policy_archive(
    payload: EvaluationGatePolicyIdPayload,
    *,
    user: User,
    di: Di,
) -> EvaluationGatePolicy:
    _ = user
    _ = await require_company_member(di)
    return await _lab(
        di.evaluation_lab_service.archive_gate_policy(payload.gate_policy_id)
    )


async def op_flows_evaluation_gate_policy_run(
    payload: EvaluationGatePolicyRunRequest,
    *,
    user: User,
    di: Di,
) -> EvaluationRunWithCases:
    _ = user
    _ = await require_company_member(di)
    gate_policy_id = _require_id(payload.gate_policy_id, "gate_policy_id")
    created = await _lab(
        di.evaluation_lab_service.create_gate_policy_run(gate_policy_id, payload)
    )
    if created.run.state == EvaluationRunState.QUEUED:
        await _create_run_job_and_enqueue(created.run.run_id, di)
    return await _lab(di.evaluation_lab_service.get_run(created.run.run_id))


async def op_flows_evaluation_gate_result(
    payload: EvaluationRunIdPayload,
    *,
    user: User,
    di: Di,
) -> EvaluationGateResult:
    _ = user
    _ = await require_company_member(di)
    return await _lab(di.evaluation_lab_service.get_gate_result(payload.run_id))


async def op_flows_evaluation_monitor_create(
    payload: EvaluationMonitorCreateRequest,
    *,
    user: User,
    di: Di,
) -> EvaluationMonitor:
    _ = user
    _ = await require_company_member(di)
    return await _lab(di.evaluation_lab_service.create_monitor(payload))


async def op_flows_evaluation_monitor_cycles_run_active(
    payload: EvaluationActiveMonitorCyclesRequest,
    *,
    user: User,
    di: Di,
) -> EvaluationActiveMonitorCyclesResult:
    _ = user
    _ = await require_company_member(di)
    cycles = await _lab(
        di.evaluation_lab_service.run_active_monitor_cycles(
            limit_per_monitor=payload.limit_per_monitor,
            enqueue_gate_runs=payload.enqueue_gate_runs,
            trials=payload.trials,
            max_concurrency=payload.max_concurrency,
        )
    )
    enqueued_cycles: list[EvaluationMonitorCycleResult] = []
    for cycle in cycles:
        enqueued_cycles.append(await _enqueue_run_from_cycle(cycle, di))
    return EvaluationActiveMonitorCyclesResult(cycles=enqueued_cycles)


async def op_flows_evaluation_monitors_list(
    payload: EvaluationSuiteIdPayload,
    *,
    user: User,
    di: Di,
) -> ListResponse[EvaluationMonitor]:
    _ = user
    _ = await require_company_member(di)
    return ListResponse(
        items=await _lab(di.evaluation_lab_service.list_monitors(payload.suite_id))
    )


async def op_flows_evaluation_monitor_item(
    payload: EvaluationMonitorIdPayload,
    *,
    user: User,
    di: Di,
) -> EvaluationMonitor:
    _ = user
    _ = await require_company_member(di)
    return await _lab(di.evaluation_lab_service.get_monitor(payload.monitor_id))


async def op_flows_evaluation_monitor_update(
    payload: EvaluationMonitorUpdateRequest,
    *,
    user: User,
    di: Di,
) -> EvaluationMonitor:
    _ = user
    _ = await require_company_member(di)
    monitor_id = _require_id(payload.monitor_id, "monitor_id")
    return await _lab(di.evaluation_lab_service.update_monitor(monitor_id, payload))


async def op_flows_evaluation_monitor_archive(
    payload: EvaluationMonitorIdPayload,
    *,
    user: User,
    di: Di,
) -> EvaluationMonitor:
    _ = user
    _ = await require_company_member(di)
    return await _lab(di.evaluation_lab_service.archive_monitor(payload.monitor_id))


async def op_flows_evaluation_monitor_sample(
    payload: EvaluationMonitorSampleRequest,
    *,
    user: User,
    di: Di,
) -> EvaluationMonitorSampleResult:
    _ = user
    _ = await require_company_member(di)
    monitor_id = _require_id(payload.monitor_id, "monitor_id")
    return await _lab(di.evaluation_lab_service.sample_monitor(monitor_id, payload))


async def op_flows_evaluation_monitor_run_cycle(
    payload: EvaluationMonitorCycleRequest,
    *,
    user: User,
    di: Di,
) -> EvaluationMonitorCycleResult:
    _ = user
    _ = await require_company_member(di)
    monitor_id = _require_id(payload.monitor_id, "monitor_id")
    cycle = await _lab(di.evaluation_lab_service.run_monitor_cycle(monitor_id, payload))
    return await _enqueue_run_from_cycle(cycle, di)


async def op_flows_evaluation_monitor_observation_case_create(
    payload: EvaluationMonitorObservationCaseCreateRequest,
    *,
    user: User,
    di: Di,
) -> EvaluationMonitorObservationCurationResult:
    _ = user
    _ = await require_company_member(di)
    monitor_id = _require_id(payload.monitor_id, "monitor_id")
    trace_id = _require_id(payload.trace_id, "trace_id")
    return await _lab(
        di.evaluation_lab_service.create_case_from_monitor_observation(
            monitor_id,
            trace_id,
            payload,
        )
    )


async def op_flows_evaluation_monitor_observations(
    payload: EvaluationMonitorObservationsPayload,
    *,
    user: User,
    di: Di,
) -> ListResponse[EvaluationMonitorObservation]:
    _ = user
    _ = await require_company_member(di)
    return ListResponse(
        items=await _lab(
            di.evaluation_lab_service.list_monitor_observations(
                payload.monitor_id,
                payload.limit,
            )
        )
    )
