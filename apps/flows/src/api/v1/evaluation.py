"""API для first-class Evaluation Lab."""

from typing import Annotated, NoReturn

from fastapi import APIRouter, HTTPException, Query

from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.evaluation.lab_service import (
    EvaluationLabNotFoundError,
    EvaluationLabValidationError,
)
from apps.flows.src.models.evaluation_lab import (
    EvaluationActiveMonitorCyclesRequest,
    EvaluationActiveMonitorCyclesResult,
    EvaluationAnnotation,
    EvaluationAnnotationCreateRequest,
    EvaluationAnnotationUpdateRequest,
    EvaluationBaseline,
    EvaluationBaselineComparison,
    EvaluationBaselineSetRequest,
    EvaluationBuiltinEvaluatorCatalog,
    EvaluationCase,
    EvaluationCaseCreateRequest,
    EvaluationCaseImportRequest,
    EvaluationCaseImportResult,
    EvaluationCaseRun,
    EvaluationCaseRunCaseCreateRequest,
    EvaluationCaseRunTrace,
    EvaluationCaseUpdateRequest,
    EvaluationDialogCaseCreateRequest,
    EvaluationGatePolicy,
    EvaluationGatePolicyCreateRequest,
    EvaluationGatePolicyRunRequest,
    EvaluationGatePolicyUpdateRequest,
    EvaluationGateResult,
    EvaluationMonitor,
    EvaluationMonitorCreateRequest,
    EvaluationMonitorCycleRequest,
    EvaluationMonitorCycleResult,
    EvaluationMonitorObservation,
    EvaluationMonitorObservationCaseCreateRequest,
    EvaluationMonitorObservationCurationResult,
    EvaluationMonitorSampleRequest,
    EvaluationMonitorSampleResult,
    EvaluationMonitorUpdateRequest,
    EvaluationPairwiseJudgeRequest,
    EvaluationPairwiseJudgment,
    EvaluationPendingRunJobsEnqueueResult,
    EvaluationResultsMatrix,
    EvaluationRubric,
    EvaluationRubricCreateRequest,
    EvaluationRubricUpdateRequest,
    EvaluationRubricVersion,
    EvaluationRubricVersionCreateRequest,
    EvaluationRubricWithVersion,
    EvaluationRun,
    EvaluationRunComparison,
    EvaluationRunCreateRequest,
    EvaluationRunEvent,
    EvaluationRunEventsPage,
    EvaluationRunJobState,
    EvaluationRunState,
    EvaluationRunWithCases,
    EvaluationSuite,
    EvaluationSuiteCreateRequest,
    EvaluationSuiteUpdateRequest,
    EvaluationTraceCaseCreateRequest,
)
from apps.flows.src.tasks.task_names import TASK_EXECUTE_EVALUATION_RUN
from apps.flows_worker.broker_core import broker as flows_broker
from core.context import get_context
from core.pagination import ListResponse
from core.tasks.kicker import kicker_for_task_name_with_log_labels
from core.tracing.context import get_current_trace_context
from core.types import JsonObject

router = APIRouter(tags=["evaluation"])


def _raise_evaluation_error(exc: ValueError) -> NoReturn:
    if isinstance(exc, EvaluationLabNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, EvaluationLabValidationError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


async def _enqueue_evaluation_run_job(run_id: str, container: ContainerDep) -> None:
    job = await container.evaluation_lab_service.get_run_job(run_id)
    if job.state == EvaluationRunJobState.ENQUEUED:
        return
    _ = await container.evaluation_lab_service.mark_run_job_enqueued(run_id)
    try:
        kicker = kicker_for_task_name_with_log_labels(
            TASK_EXECUTE_EVALUATION_RUN,
            flows_broker,
            background_kind="evaluation",
            extra_labels={"evaluation_run_id": run_id},
        )
        _ = await kicker.with_task_id(job.taskiq_task_id).kiq(
            run_id,
            context_data=job.context_data,
            trace_context=job.trace_context,
        )
    except Exception as enqueue_exc:
        _ = await container.evaluation_lab_service.mark_run_job_failed(run_id, str(enqueue_exc))
        _ = await container.evaluation_lab_service.mark_run_enqueue_failed(
            run_id,
            str(enqueue_exc),
        )
        raise


async def _create_run_job_and_enqueue(run_id: str, container: ContainerDep) -> None:
    context = get_context()
    if context is None:
        raise EvaluationLabValidationError("Context is required to enqueue evaluation run")
    _ = await container.evaluation_lab_service.create_run_job(
        run_id,
        context_data=context.to_dict(),
        trace_context=get_current_trace_context(),
    )
    await _enqueue_evaluation_run_job(run_id, container)


async def _enqueue_run_from_cycle(
    cycle: EvaluationMonitorCycleResult,
    container: ContainerDep,
) -> EvaluationMonitorCycleResult:
    if cycle.run is not None and cycle.run.state == EvaluationRunState.QUEUED:
        await _create_run_job_and_enqueue(cycle.run.run_id, container)
        run_with_cases = await container.evaluation_lab_service.get_run(cycle.run.run_id)
        return cycle.model_copy(update={"run": run_with_cases.run})
    return cycle


@router.get("/evaluator-catalog", response_model=EvaluationBuiltinEvaluatorCatalog)
async def get_evaluation_evaluator_catalog(
    container: ContainerDep,
) -> EvaluationBuiltinEvaluatorCatalog:
    return container.evaluation_lab_service.list_builtin_evaluators()


@router.post("/suites", response_model=EvaluationSuite)
async def create_evaluation_suite(
    request: EvaluationSuiteCreateRequest,
    container: ContainerDep,
) -> EvaluationSuite:
    try:
        return await container.evaluation_lab_service.create_suite(request)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.get("/suites", response_model=ListResponse[EvaluationSuite])
async def list_evaluation_suites(
    container: ContainerDep,
    flow_id: Annotated[str, Query(description="ID агента")],
) -> ListResponse[EvaluationSuite]:
    return ListResponse(items=await container.evaluation_lab_service.list_suites(flow_id))


@router.get("/suites/{suite_id}", response_model=EvaluationSuite)
async def get_evaluation_suite(
    suite_id: str,
    container: ContainerDep,
) -> EvaluationSuite:
    try:
        return await container.evaluation_lab_service.get_suite(suite_id)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.put("/suites/{suite_id}", response_model=EvaluationSuite)
async def update_evaluation_suite(
    suite_id: str,
    request: EvaluationSuiteUpdateRequest,
    container: ContainerDep,
) -> EvaluationSuite:
    try:
        return await container.evaluation_lab_service.update_suite(suite_id, request)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.post("/suites/{suite_id}/archive", response_model=EvaluationSuite)
async def archive_evaluation_suite(
    suite_id: str,
    container: ContainerDep,
) -> EvaluationSuite:
    try:
        return await container.evaluation_lab_service.archive_suite(suite_id)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.post("/suites/{suite_id}/cases", response_model=EvaluationCase)
async def create_evaluation_case(
    suite_id: str,
    request: EvaluationCaseCreateRequest,
    container: ContainerDep,
) -> EvaluationCase:
    try:
        return await container.evaluation_lab_service.create_case(suite_id, request)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.get("/suites/{suite_id}/cases", response_model=ListResponse[EvaluationCase])
async def list_evaluation_cases(
    suite_id: str,
    container: ContainerDep,
) -> ListResponse[EvaluationCase]:
    try:
        return ListResponse(items=await container.evaluation_lab_service.list_cases(suite_id))
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.get("/suites/{suite_id}/cases/{case_id}", response_model=EvaluationCase)
async def get_evaluation_case(
    suite_id: str,
    case_id: str,
    container: ContainerDep,
) -> EvaluationCase:
    try:
        return await container.evaluation_lab_service.get_case(suite_id, case_id)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.put("/suites/{suite_id}/cases/{case_id}", response_model=EvaluationCase)
async def update_evaluation_case(
    suite_id: str,
    case_id: str,
    request: EvaluationCaseUpdateRequest,
    container: ContainerDep,
) -> EvaluationCase:
    try:
        return await container.evaluation_lab_service.update_case(suite_id, case_id, request)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.delete("/suites/{suite_id}/cases/{case_id}")
async def delete_evaluation_case(
    suite_id: str,
    case_id: str,
    container: ContainerDep,
) -> JsonObject:
    try:
        await container.evaluation_lab_service.delete_case(suite_id, case_id)
    except ValueError as exc:
        _raise_evaluation_error(exc)
    return {"deleted": True}


@router.post("/suites/{suite_id}/cases/import", response_model=EvaluationCaseImportResult)
async def import_evaluation_cases(
    suite_id: str,
    request: EvaluationCaseImportRequest,
    container: ContainerDep,
) -> EvaluationCaseImportResult:
    try:
        return await container.evaluation_lab_service.import_cases(suite_id, request)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.post("/suites/{suite_id}/cases/from-dialog", response_model=EvaluationCase)
async def create_evaluation_case_from_dialog(
    suite_id: str,
    request: EvaluationDialogCaseCreateRequest,
    container: ContainerDep,
) -> EvaluationCase:
    try:
        return await container.evaluation_lab_service.create_case_from_dialog(suite_id, request)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.post("/suites/{suite_id}/cases/from-case-run", response_model=EvaluationCase)
async def create_evaluation_case_from_case_run(
    suite_id: str,
    request: EvaluationCaseRunCaseCreateRequest,
    container: ContainerDep,
) -> EvaluationCase:
    try:
        return await container.evaluation_lab_service.create_case_from_case_run(suite_id, request)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.post("/suites/{suite_id}/cases/from-trace", response_model=EvaluationCase)
async def create_evaluation_case_from_trace(
    suite_id: str,
    request: EvaluationTraceCaseCreateRequest,
    container: ContainerDep,
) -> EvaluationCase:
    try:
        return await container.evaluation_lab_service.create_case_from_trace(suite_id, request)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.post("/rubrics", response_model=EvaluationRubricWithVersion)
async def create_evaluation_rubric(
    request: EvaluationRubricCreateRequest,
    container: ContainerDep,
) -> EvaluationRubricWithVersion:
    try:
        rubric, version = await container.evaluation_lab_service.create_rubric(request)
        return EvaluationRubricWithVersion(rubric=rubric, version=version)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.get("/rubrics", response_model=ListResponse[EvaluationRubric])
async def list_evaluation_rubrics(
    container: ContainerDep,
    flow_id: Annotated[str, Query(description="ID агента")],
) -> ListResponse[EvaluationRubric]:
    return ListResponse(items=await container.evaluation_lab_service.list_rubrics(flow_id))


@router.get("/rubrics/{rubric_id}", response_model=EvaluationRubric)
async def get_evaluation_rubric(
    rubric_id: str,
    container: ContainerDep,
) -> EvaluationRubric:
    try:
        return await container.evaluation_lab_service.get_rubric(rubric_id)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.put("/rubrics/{rubric_id}", response_model=EvaluationRubric)
async def update_evaluation_rubric(
    rubric_id: str,
    request: EvaluationRubricUpdateRequest,
    container: ContainerDep,
) -> EvaluationRubric:
    try:
        return await container.evaluation_lab_service.update_rubric(rubric_id, request)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.post("/rubrics/{rubric_id}/archive", response_model=EvaluationRubric)
async def archive_evaluation_rubric(
    rubric_id: str,
    container: ContainerDep,
) -> EvaluationRubric:
    try:
        return await container.evaluation_lab_service.archive_rubric(rubric_id)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.post("/rubrics/{rubric_id}/versions", response_model=EvaluationRubricVersion)
async def create_evaluation_rubric_version(
    rubric_id: str,
    request: EvaluationRubricVersionCreateRequest,
    container: ContainerDep,
) -> EvaluationRubricVersion:
    try:
        return await container.evaluation_lab_service.create_rubric_version(rubric_id, request)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.get("/rubrics/{rubric_id}/versions", response_model=ListResponse[EvaluationRubricVersion])
async def list_evaluation_rubric_versions(
    rubric_id: str,
    container: ContainerDep,
) -> ListResponse[EvaluationRubricVersion]:
    try:
        return ListResponse(
            items=await container.evaluation_lab_service.list_rubric_versions(rubric_id)
        )
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.post("/runs", response_model=EvaluationRunWithCases)
async def create_evaluation_run(
    request: EvaluationRunCreateRequest,
    container: ContainerDep,
) -> EvaluationRunWithCases:
    try:
        created = await container.evaluation_lab_service.create_run(request)
        if created.run.state == EvaluationRunState.QUEUED:
            await _create_run_job_and_enqueue(created.run.run_id, container)
        return await container.evaluation_lab_service.get_run(created.run.run_id)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.get("/runs/compare", response_model=EvaluationRunComparison)
async def compare_evaluation_runs(
    container: ContainerDep,
    left_run_id: Annotated[str, Query(description="ID базового запуска")],
    right_run_id: Annotated[str, Query(description="ID сравниваемого запуска")],
) -> EvaluationRunComparison:
    try:
        return await container.evaluation_lab_service.compare_runs(left_run_id, right_run_id)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.post("/run-jobs/enqueue-pending", response_model=EvaluationPendingRunJobsEnqueueResult)
async def enqueue_pending_evaluation_run_jobs(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> EvaluationPendingRunJobsEnqueueResult:
    enqueued_run_ids: list[str] = []
    failed_run_ids: list[str] = []
    try:
        jobs = await container.evaluation_lab_service.list_pending_run_jobs(limit)
        for job in jobs:
            try:
                await _enqueue_evaluation_run_job(job.run_id, container)
                enqueued_run_ids.append(job.run_id)
            except Exception:
                failed_run_ids.append(job.run_id)
        return EvaluationPendingRunJobsEnqueueResult(
            enqueued_run_ids=enqueued_run_ids,
            failed_run_ids=failed_run_ids,
        )
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.get("/runs/{run_id}", response_model=EvaluationRunWithCases)
async def get_evaluation_run(
    run_id: str,
    container: ContainerDep,
) -> EvaluationRunWithCases:
    try:
        return await container.evaluation_lab_service.get_run(run_id)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.post("/runs/{run_id}/cancel", response_model=EvaluationRunWithCases)
async def cancel_evaluation_run(
    run_id: str,
    container: ContainerDep,
) -> EvaluationRunWithCases:
    try:
        return await container.evaluation_lab_service.cancel_run(run_id)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.get("/runs/{run_id}/cases", response_model=ListResponse[EvaluationCaseRun])
async def list_evaluation_case_runs(
    run_id: str,
    container: ContainerDep,
) -> ListResponse[EvaluationCaseRun]:
    try:
        return ListResponse(items=await container.evaluation_lab_service.list_case_runs(run_id))
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.get("/runs/{run_id}/events", response_model=ListResponse[EvaluationRunEvent])
async def list_evaluation_run_events(
    run_id: str,
    container: ContainerDep,
) -> ListResponse[EvaluationRunEvent]:
    try:
        return ListResponse(items=await container.evaluation_lab_service.list_events(run_id))
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.get("/runs/{run_id}/events-page", response_model=EvaluationRunEventsPage)
async def list_evaluation_run_events_page(
    run_id: str,
    container: ContainerDep,
    after_sequence: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> EvaluationRunEventsPage:
    try:
        return await container.evaluation_lab_service.list_events_page(
            run_id,
            after_sequence=after_sequence,
            limit=limit,
        )
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.get("/case-runs/{case_run_id}/trace", response_model=EvaluationCaseRunTrace)
async def get_evaluation_case_run_trace(
    case_run_id: str,
    container: ContainerDep,
) -> EvaluationCaseRunTrace:
    try:
        return await container.evaluation_lab_service.get_case_run_trace(case_run_id)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.post("/pairwise-judgments", response_model=EvaluationPairwiseJudgment)
async def create_evaluation_pairwise_judgment(
    request: EvaluationPairwiseJudgeRequest,
    container: ContainerDep,
) -> EvaluationPairwiseJudgment:
    try:
        return await container.evaluation_lab_service.create_pairwise_judgment(request)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.get(
    "/case-runs/{case_run_id}/pairwise-judgments",
    response_model=ListResponse[EvaluationPairwiseJudgment],
)
async def list_evaluation_pairwise_judgments_for_case_run(
    case_run_id: str,
    container: ContainerDep,
) -> ListResponse[EvaluationPairwiseJudgment]:
    try:
        return ListResponse(
            items=await container.evaluation_lab_service.list_pairwise_judgments_for_case_run(
                case_run_id,
            )
        )
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.post("/runs/{run_id}/annotations", response_model=EvaluationAnnotation)
async def create_evaluation_annotation(
    run_id: str,
    request: EvaluationAnnotationCreateRequest,
    container: ContainerDep,
) -> EvaluationAnnotation:
    try:
        return await container.evaluation_lab_service.create_annotation(run_id, request)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.get("/runs/{run_id}/annotations", response_model=ListResponse[EvaluationAnnotation])
async def list_evaluation_annotations(
    run_id: str,
    container: ContainerDep,
) -> ListResponse[EvaluationAnnotation]:
    try:
        return ListResponse(items=await container.evaluation_lab_service.list_annotations(run_id))
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.put("/annotations/{annotation_id}", response_model=EvaluationAnnotation)
async def update_evaluation_annotation(
    annotation_id: str,
    request: EvaluationAnnotationUpdateRequest,
    container: ContainerDep,
) -> EvaluationAnnotation:
    try:
        return await container.evaluation_lab_service.update_annotation(annotation_id, request)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.delete("/annotations/{annotation_id}")
async def delete_evaluation_annotation(
    annotation_id: str,
    container: ContainerDep,
) -> JsonObject:
    try:
        await container.evaluation_lab_service.delete_annotation(annotation_id)
    except ValueError as exc:
        _raise_evaluation_error(exc)
    return {"deleted": True}


@router.get("/suites/{suite_id}/runs", response_model=ListResponse[EvaluationRun])
async def list_evaluation_runs(
    suite_id: str,
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ListResponse[EvaluationRun]:
    try:
        return ListResponse(items=await container.evaluation_lab_service.list_runs(suite_id, limit))
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.get("/suites/{suite_id}/matrix", response_model=EvaluationResultsMatrix)
async def get_evaluation_results_matrix(
    suite_id: str,
    container: ContainerDep,
    branch_id: Annotated[str, Query(description="ID ветки")],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> EvaluationResultsMatrix:
    try:
        return await container.evaluation_lab_service.get_results_matrix(
            suite_id,
            branch_id,
            limit,
        )
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.put("/suites/{suite_id}/baselines/{branch_id}", response_model=EvaluationBaseline)
async def set_evaluation_baseline(
    suite_id: str,
    branch_id: str,
    request: EvaluationBaselineSetRequest,
    container: ContainerDep,
) -> EvaluationBaseline:
    try:
        return await container.evaluation_lab_service.set_baseline(suite_id, branch_id, request)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.get("/suites/{suite_id}/baselines", response_model=ListResponse[EvaluationBaseline])
async def list_evaluation_baselines(
    suite_id: str,
    container: ContainerDep,
) -> ListResponse[EvaluationBaseline]:
    try:
        return ListResponse(items=await container.evaluation_lab_service.list_baselines(suite_id))
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.get("/suites/{suite_id}/baselines/{branch_id}", response_model=EvaluationBaseline)
async def get_evaluation_baseline(
    suite_id: str,
    branch_id: str,
    container: ContainerDep,
) -> EvaluationBaseline:
    try:
        return await container.evaluation_lab_service.get_baseline(suite_id, branch_id)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.get("/suites/{suite_id}/baseline-compare", response_model=EvaluationBaselineComparison)
async def compare_evaluation_run_with_baseline(
    suite_id: str,
    container: ContainerDep,
    branch_id: Annotated[str, Query(description="ID ветки")],
    run_id: Annotated[str, Query(description="ID сравниваемого запуска")],
) -> EvaluationBaselineComparison:
    try:
        return await container.evaluation_lab_service.compare_with_baseline(
            suite_id,
            branch_id,
            run_id,
        )
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.post("/suites/{suite_id}/gate-policies", response_model=EvaluationGatePolicy)
async def create_evaluation_gate_policy(
    suite_id: str,
    request: EvaluationGatePolicyCreateRequest,
    container: ContainerDep,
) -> EvaluationGatePolicy:
    try:
        return await container.evaluation_lab_service.create_gate_policy(suite_id, request)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.get("/suites/{suite_id}/gate-policies", response_model=ListResponse[EvaluationGatePolicy])
async def list_evaluation_gate_policies(
    suite_id: str,
    container: ContainerDep,
) -> ListResponse[EvaluationGatePolicy]:
    try:
        return ListResponse(items=await container.evaluation_lab_service.list_gate_policies(suite_id))
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.get("/gate-policies/{gate_policy_id}", response_model=EvaluationGatePolicy)
async def get_evaluation_gate_policy(
    gate_policy_id: str,
    container: ContainerDep,
) -> EvaluationGatePolicy:
    try:
        return await container.evaluation_lab_service.get_gate_policy(gate_policy_id)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.put("/gate-policies/{gate_policy_id}", response_model=EvaluationGatePolicy)
async def update_evaluation_gate_policy(
    gate_policy_id: str,
    request: EvaluationGatePolicyUpdateRequest,
    container: ContainerDep,
) -> EvaluationGatePolicy:
    try:
        return await container.evaluation_lab_service.update_gate_policy(gate_policy_id, request)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.post("/gate-policies/{gate_policy_id}/archive", response_model=EvaluationGatePolicy)
async def archive_evaluation_gate_policy(
    gate_policy_id: str,
    container: ContainerDep,
) -> EvaluationGatePolicy:
    try:
        return await container.evaluation_lab_service.archive_gate_policy(gate_policy_id)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.post("/gate-policies/{gate_policy_id}/run", response_model=EvaluationRunWithCases)
async def run_evaluation_gate_policy(
    gate_policy_id: str,
    request: EvaluationGatePolicyRunRequest,
    container: ContainerDep,
) -> EvaluationRunWithCases:
    try:
        created = await container.evaluation_lab_service.create_gate_policy_run(
            gate_policy_id,
            request,
        )
        if created.run.state == EvaluationRunState.QUEUED:
            await _create_run_job_and_enqueue(created.run.run_id, container)
        return await container.evaluation_lab_service.get_run(created.run.run_id)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.get("/runs/{run_id}/gate-result", response_model=EvaluationGateResult)
async def get_evaluation_gate_result(
    run_id: str,
    container: ContainerDep,
) -> EvaluationGateResult:
    try:
        return await container.evaluation_lab_service.get_gate_result(run_id)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.post("/monitors", response_model=EvaluationMonitor)
async def create_evaluation_monitor(
    request: EvaluationMonitorCreateRequest,
    container: ContainerDep,
) -> EvaluationMonitor:
    try:
        return await container.evaluation_lab_service.create_monitor(request)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.post("/monitor-cycles/run-active", response_model=EvaluationActiveMonitorCyclesResult)
async def run_active_evaluation_monitor_cycles(
    request: EvaluationActiveMonitorCyclesRequest,
    container: ContainerDep,
) -> EvaluationActiveMonitorCyclesResult:
    try:
        cycles = await container.evaluation_lab_service.run_active_monitor_cycles(
            limit_per_monitor=request.limit_per_monitor,
            enqueue_gate_runs=request.enqueue_gate_runs,
            trials=request.trials,
            max_concurrency=request.max_concurrency,
        )
        enqueued_cycles: list[EvaluationMonitorCycleResult] = []
        for cycle in cycles:
            enqueued_cycles.append(await _enqueue_run_from_cycle(cycle, container))
        return EvaluationActiveMonitorCyclesResult(cycles=enqueued_cycles)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.get("/suites/{suite_id}/monitors", response_model=ListResponse[EvaluationMonitor])
async def list_evaluation_monitors(
    suite_id: str,
    container: ContainerDep,
) -> ListResponse[EvaluationMonitor]:
    try:
        return ListResponse(items=await container.evaluation_lab_service.list_monitors(suite_id))
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.get("/monitors/{monitor_id}", response_model=EvaluationMonitor)
async def get_evaluation_monitor(
    monitor_id: str,
    container: ContainerDep,
) -> EvaluationMonitor:
    try:
        return await container.evaluation_lab_service.get_monitor(monitor_id)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.put("/monitors/{monitor_id}", response_model=EvaluationMonitor)
async def update_evaluation_monitor(
    monitor_id: str,
    request: EvaluationMonitorUpdateRequest,
    container: ContainerDep,
) -> EvaluationMonitor:
    try:
        return await container.evaluation_lab_service.update_monitor(monitor_id, request)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.post("/monitors/{monitor_id}/archive", response_model=EvaluationMonitor)
async def archive_evaluation_monitor(
    monitor_id: str,
    container: ContainerDep,
) -> EvaluationMonitor:
    try:
        return await container.evaluation_lab_service.archive_monitor(monitor_id)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.post("/monitors/{monitor_id}/sample", response_model=EvaluationMonitorSampleResult)
async def sample_evaluation_monitor(
    monitor_id: str,
    request: EvaluationMonitorSampleRequest,
    container: ContainerDep,
) -> EvaluationMonitorSampleResult:
    try:
        return await container.evaluation_lab_service.sample_monitor(monitor_id, request)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.post("/monitors/{monitor_id}/run-cycle", response_model=EvaluationMonitorCycleResult)
async def run_evaluation_monitor_cycle(
    monitor_id: str,
    request: EvaluationMonitorCycleRequest,
    container: ContainerDep,
) -> EvaluationMonitorCycleResult:
    try:
        cycle = await container.evaluation_lab_service.run_monitor_cycle(monitor_id, request)
        return await _enqueue_run_from_cycle(cycle, container)
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.post(
    "/monitors/{monitor_id}/observations/{trace_id}/case",
    response_model=EvaluationMonitorObservationCurationResult,
)
async def create_evaluation_case_from_monitor_observation(
    monitor_id: str,
    trace_id: str,
    request: EvaluationMonitorObservationCaseCreateRequest,
    container: ContainerDep,
) -> EvaluationMonitorObservationCurationResult:
    try:
        return await container.evaluation_lab_service.create_case_from_monitor_observation(
            monitor_id,
            trace_id,
            request,
        )
    except ValueError as exc:
        _raise_evaluation_error(exc)


@router.get(
    "/monitors/{monitor_id}/observations",
    response_model=ListResponse[EvaluationMonitorObservation],
)
async def list_evaluation_monitor_observations(
    monitor_id: str,
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> ListResponse[EvaluationMonitorObservation]:
    try:
        return ListResponse(
            items=await container.evaluation_lab_service.list_monitor_observations(
                monitor_id,
                limit,
            )
        )
    except ValueError as exc:
        _raise_evaluation_error(exc)
