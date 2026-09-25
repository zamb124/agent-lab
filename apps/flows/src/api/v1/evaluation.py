"""REST-зеркало Evaluation Lab: path/query → тот же `op_*`, что и WS."""

from typing import Annotated

from fastapi import APIRouter, Query

from apps.flows.di import Di
from apps.flows.realtime.evaluation_operations import (
    op_flows_evaluation_annotation_create,
    op_flows_evaluation_annotation_delete,
    op_flows_evaluation_annotation_update,
    op_flows_evaluation_annotations_list,
    op_flows_evaluation_baseline_compare,
    op_flows_evaluation_baseline_item,
    op_flows_evaluation_baseline_set,
    op_flows_evaluation_baselines_list,
    op_flows_evaluation_case_create,
    op_flows_evaluation_case_delete,
    op_flows_evaluation_case_from_case_run,
    op_flows_evaluation_case_from_dialog,
    op_flows_evaluation_case_from_trace,
    op_flows_evaluation_case_import,
    op_flows_evaluation_case_item,
    op_flows_evaluation_case_run_trace,
    op_flows_evaluation_case_update,
    op_flows_evaluation_cases_list,
    op_flows_evaluation_compare_runs,
    op_flows_evaluation_evaluator_catalog,
    op_flows_evaluation_gate_policies_list,
    op_flows_evaluation_gate_policy_archive,
    op_flows_evaluation_gate_policy_create,
    op_flows_evaluation_gate_policy_item,
    op_flows_evaluation_gate_policy_run,
    op_flows_evaluation_gate_policy_update,
    op_flows_evaluation_gate_result,
    op_flows_evaluation_matrix_get,
    op_flows_evaluation_monitor_archive,
    op_flows_evaluation_monitor_create,
    op_flows_evaluation_monitor_cycles_run_active,
    op_flows_evaluation_monitor_item,
    op_flows_evaluation_monitor_observation_case_create,
    op_flows_evaluation_monitor_observations,
    op_flows_evaluation_monitor_run_cycle,
    op_flows_evaluation_monitor_sample,
    op_flows_evaluation_monitor_update,
    op_flows_evaluation_monitors_list,
    op_flows_evaluation_pairwise_judgment_create,
    op_flows_evaluation_pairwise_judgments_list,
    op_flows_evaluation_rubric_archive,
    op_flows_evaluation_rubric_create,
    op_flows_evaluation_rubric_item,
    op_flows_evaluation_rubric_update,
    op_flows_evaluation_rubric_version_create,
    op_flows_evaluation_rubric_versions_list,
    op_flows_evaluation_rubrics_list,
    op_flows_evaluation_run_cancel,
    op_flows_evaluation_run_cases,
    op_flows_evaluation_run_create,
    op_flows_evaluation_run_events,
    op_flows_evaluation_run_events_page,
    op_flows_evaluation_run_get,
    op_flows_evaluation_run_jobs_enqueue_pending,
    op_flows_evaluation_runs_list,
    op_flows_evaluation_suite_archive,
    op_flows_evaluation_suite_create,
    op_flows_evaluation_suite_item,
    op_flows_evaluation_suite_update,
    op_flows_evaluation_suites_list,
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
    EvaluationRunsListPayload,
    EvaluationRunWithCases,
    EvaluationSuite,
    EvaluationSuiteCaseIdPayload,
    EvaluationSuiteCreateRequest,
    EvaluationSuiteIdPayload,
    EvaluationSuiteUpdateRequest,
    EvaluationTraceCaseCreateRequest,
)
from core.context import require_context
from core.pagination import ListResponse
from core.websocket import EmptyPayload

router = APIRouter(tags=["evaluation"])


@router.get("/evaluator-catalog", response_model=EvaluationBuiltinEvaluatorCatalog)
async def get_evaluation_evaluator_catalog(
    di: Di,
) -> EvaluationBuiltinEvaluatorCatalog:
    return await op_flows_evaluation_evaluator_catalog(
        EmptyPayload(),
        user=require_context().user,
        di=di,
    )


@router.post("/suites", response_model=EvaluationSuite)
async def create_evaluation_suite(
    request: EvaluationSuiteCreateRequest,
    di: Di,
) -> EvaluationSuite:
    return await op_flows_evaluation_suite_create(
        request,
        user=require_context().user,
        di=di,
    )


@router.get("/suites", response_model=ListResponse[EvaluationSuite])
async def list_evaluation_suites(
    di: Di,
    flow_id: Annotated[str, Query(description="ID агента")],
) -> ListResponse[EvaluationSuite]:
    return await op_flows_evaluation_suites_list(
        EvaluationFlowIdPayload(flow_id=flow_id),
        user=require_context().user,
        di=di,
    )


@router.get("/suites/{suite_id}", response_model=EvaluationSuite)
async def get_evaluation_suite(
    suite_id: str,
    di: Di,
) -> EvaluationSuite:
    return await op_flows_evaluation_suite_item(
        EvaluationSuiteIdPayload(suite_id=suite_id),
        user=require_context().user,
        di=di,
    )


@router.put("/suites/{suite_id}", response_model=EvaluationSuite)
async def update_evaluation_suite(
    suite_id: str,
    request: EvaluationSuiteUpdateRequest,
    di: Di,
) -> EvaluationSuite:
    return await op_flows_evaluation_suite_update(
        request.model_copy(update={"suite_id": suite_id}),
        user=require_context().user,
        di=di,
    )


@router.post("/suites/{suite_id}/archive", response_model=EvaluationSuite)
async def archive_evaluation_suite(
    suite_id: str,
    di: Di,
) -> EvaluationSuite:
    return await op_flows_evaluation_suite_archive(
        EvaluationSuiteIdPayload(suite_id=suite_id),
        user=require_context().user,
        di=di,
    )


@router.post("/suites/{suite_id}/cases", response_model=EvaluationCase)
async def create_evaluation_case(
    suite_id: str,
    request: EvaluationCaseCreateRequest,
    di: Di,
) -> EvaluationCase:
    return await op_flows_evaluation_case_create(
        request.model_copy(update={"suite_id": suite_id}),
        user=require_context().user,
        di=di,
    )


@router.get("/suites/{suite_id}/cases", response_model=ListResponse[EvaluationCase])
async def list_evaluation_cases(
    suite_id: str,
    di: Di,
) -> ListResponse[EvaluationCase]:
    return await op_flows_evaluation_cases_list(
        EvaluationSuiteIdPayload(suite_id=suite_id),
        user=require_context().user,
        di=di,
    )


@router.get("/suites/{suite_id}/cases/{case_id}", response_model=EvaluationCase)
async def get_evaluation_case(
    suite_id: str,
    case_id: str,
    di: Di,
) -> EvaluationCase:
    return await op_flows_evaluation_case_item(
        EvaluationSuiteCaseIdPayload(suite_id=suite_id, case_id=case_id),
        user=require_context().user,
        di=di,
    )


@router.put("/suites/{suite_id}/cases/{case_id}", response_model=EvaluationCase)
async def update_evaluation_case(
    suite_id: str,
    case_id: str,
    request: EvaluationCaseUpdateRequest,
    di: Di,
) -> EvaluationCase:
    return await op_flows_evaluation_case_update(
        request.model_copy(update={"suite_id": suite_id, "case_id": case_id}),
        user=require_context().user,
        di=di,
    )


@router.delete("/suites/{suite_id}/cases/{case_id}", response_model=EvaluationDeletedResponse)
async def delete_evaluation_case(
    suite_id: str,
    case_id: str,
    di: Di,
) -> EvaluationDeletedResponse:
    return await op_flows_evaluation_case_delete(
        EvaluationSuiteCaseIdPayload(suite_id=suite_id, case_id=case_id),
        user=require_context().user,
        di=di,
    )


@router.post("/suites/{suite_id}/cases/import", response_model=EvaluationCaseImportResult)
async def import_evaluation_cases(
    suite_id: str,
    request: EvaluationCaseImportRequest,
    di: Di,
) -> EvaluationCaseImportResult:
    return await op_flows_evaluation_case_import(
        request.model_copy(update={"suite_id": suite_id}),
        user=require_context().user,
        di=di,
    )


@router.post("/suites/{suite_id}/cases/from-dialog", response_model=EvaluationCase)
async def create_evaluation_case_from_dialog(
    suite_id: str,
    request: EvaluationDialogCaseCreateRequest,
    di: Di,
) -> EvaluationCase:
    return await op_flows_evaluation_case_from_dialog(
        request.model_copy(update={"suite_id": suite_id}),
        user=require_context().user,
        di=di,
    )


@router.post("/suites/{suite_id}/cases/from-case-run", response_model=EvaluationCase)
async def create_evaluation_case_from_case_run(
    suite_id: str,
    request: EvaluationCaseRunCaseCreateRequest,
    di: Di,
) -> EvaluationCase:
    return await op_flows_evaluation_case_from_case_run(
        request.model_copy(update={"suite_id": suite_id}),
        user=require_context().user,
        di=di,
    )


@router.post("/suites/{suite_id}/cases/from-trace", response_model=EvaluationCase)
async def create_evaluation_case_from_trace(
    suite_id: str,
    request: EvaluationTraceCaseCreateRequest,
    di: Di,
) -> EvaluationCase:
    return await op_flows_evaluation_case_from_trace(
        request.model_copy(update={"suite_id": suite_id}),
        user=require_context().user,
        di=di,
    )


@router.post("/rubrics", response_model=EvaluationRubricWithVersion)
async def create_evaluation_rubric(
    request: EvaluationRubricCreateRequest,
    di: Di,
) -> EvaluationRubricWithVersion:
    return await op_flows_evaluation_rubric_create(
        request,
        user=require_context().user,
        di=di,
    )


@router.get("/rubrics", response_model=ListResponse[EvaluationRubric])
async def list_evaluation_rubrics(
    di: Di,
    flow_id: Annotated[str, Query(description="ID агента")],
) -> ListResponse[EvaluationRubric]:
    return await op_flows_evaluation_rubrics_list(
        EvaluationFlowIdPayload(flow_id=flow_id),
        user=require_context().user,
        di=di,
    )


@router.get("/rubrics/{rubric_id}", response_model=EvaluationRubric)
async def get_evaluation_rubric(
    rubric_id: str,
    di: Di,
) -> EvaluationRubric:
    return await op_flows_evaluation_rubric_item(
        EvaluationRubricIdPayload(rubric_id=rubric_id),
        user=require_context().user,
        di=di,
    )


@router.put("/rubrics/{rubric_id}", response_model=EvaluationRubric)
async def update_evaluation_rubric(
    rubric_id: str,
    request: EvaluationRubricUpdateRequest,
    di: Di,
) -> EvaluationRubric:
    return await op_flows_evaluation_rubric_update(
        request.model_copy(update={"rubric_id": rubric_id}),
        user=require_context().user,
        di=di,
    )


@router.post("/rubrics/{rubric_id}/archive", response_model=EvaluationRubric)
async def archive_evaluation_rubric(
    rubric_id: str,
    di: Di,
) -> EvaluationRubric:
    return await op_flows_evaluation_rubric_archive(
        EvaluationRubricIdPayload(rubric_id=rubric_id),
        user=require_context().user,
        di=di,
    )


@router.post("/rubrics/{rubric_id}/versions", response_model=EvaluationRubricVersion)
async def create_evaluation_rubric_version(
    rubric_id: str,
    request: EvaluationRubricVersionCreateRequest,
    di: Di,
) -> EvaluationRubricVersion:
    return await op_flows_evaluation_rubric_version_create(
        request.model_copy(update={"rubric_id": rubric_id}),
        user=require_context().user,
        di=di,
    )


@router.get("/rubrics/{rubric_id}/versions", response_model=ListResponse[EvaluationRubricVersion])
async def list_evaluation_rubric_versions(
    rubric_id: str,
    di: Di,
) -> ListResponse[EvaluationRubricVersion]:
    return await op_flows_evaluation_rubric_versions_list(
        EvaluationRubricIdPayload(rubric_id=rubric_id),
        user=require_context().user,
        di=di,
    )


@router.post("/runs", response_model=EvaluationRunWithCases)
async def create_evaluation_run(
    request: EvaluationRunCreateRequest,
    di: Di,
) -> EvaluationRunWithCases:
    return await op_flows_evaluation_run_create(
        request,
        user=require_context().user,
        di=di,
    )


@router.get("/runs/compare", response_model=EvaluationRunComparison)
async def compare_evaluation_runs(
    di: Di,
    left_run_id: Annotated[str, Query(description="ID базового запуска")],
    right_run_id: Annotated[str, Query(description="ID сравниваемого запуска")],
) -> EvaluationRunComparison:
    return await op_flows_evaluation_compare_runs(
        EvaluationCompareRunsPayload(left_run_id=left_run_id, right_run_id=right_run_id),
        user=require_context().user,
        di=di,
    )


@router.post("/run-jobs/enqueue-pending", response_model=EvaluationPendingRunJobsEnqueueResult)
async def enqueue_pending_evaluation_run_jobs(
    di: Di,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> EvaluationPendingRunJobsEnqueueResult:
    return await op_flows_evaluation_run_jobs_enqueue_pending(
        EvaluationPendingJobsPayload(limit=limit),
        user=require_context().user,
        di=di,
    )


@router.get("/runs/{run_id}", response_model=EvaluationRunWithCases)
async def get_evaluation_run(
    run_id: str,
    di: Di,
) -> EvaluationRunWithCases:
    return await op_flows_evaluation_run_get(
        EvaluationRunIdPayload(run_id=run_id),
        user=require_context().user,
        di=di,
    )


@router.post("/runs/{run_id}/cancel", response_model=EvaluationRunWithCases)
async def cancel_evaluation_run(
    run_id: str,
    di: Di,
) -> EvaluationRunWithCases:
    return await op_flows_evaluation_run_cancel(
        EvaluationRunIdPayload(run_id=run_id),
        user=require_context().user,
        di=di,
    )


@router.get("/runs/{run_id}/cases", response_model=ListResponse[EvaluationCaseRun])
async def list_evaluation_case_runs(
    run_id: str,
    di: Di,
) -> ListResponse[EvaluationCaseRun]:
    return await op_flows_evaluation_run_cases(
        EvaluationRunIdPayload(run_id=run_id),
        user=require_context().user,
        di=di,
    )


@router.get("/runs/{run_id}/events", response_model=ListResponse[EvaluationRunEvent])
async def list_evaluation_run_events(
    run_id: str,
    di: Di,
) -> ListResponse[EvaluationRunEvent]:
    return await op_flows_evaluation_run_events(
        EvaluationRunIdPayload(run_id=run_id),
        user=require_context().user,
        di=di,
    )


@router.get("/runs/{run_id}/events-page", response_model=EvaluationRunEventsPage)
async def list_evaluation_run_events_page(
    run_id: str,
    di: Di,
    after_sequence: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> EvaluationRunEventsPage:
    return await op_flows_evaluation_run_events_page(
        EvaluationEventsPagePayload(
            run_id=run_id,
            after_sequence=after_sequence,
            limit=limit,
        ),
        user=require_context().user,
        di=di,
    )


@router.get("/case-runs/{case_run_id}/trace", response_model=EvaluationCaseRunTrace)
async def get_evaluation_case_run_trace(
    case_run_id: str,
    di: Di,
) -> EvaluationCaseRunTrace:
    return await op_flows_evaluation_case_run_trace(
        EvaluationCaseRunIdPayload(case_run_id=case_run_id),
        user=require_context().user,
        di=di,
    )


@router.post("/pairwise-judgments", response_model=EvaluationPairwiseJudgment)
async def create_evaluation_pairwise_judgment(
    request: EvaluationPairwiseJudgeRequest,
    di: Di,
) -> EvaluationPairwiseJudgment:
    return await op_flows_evaluation_pairwise_judgment_create(
        request,
        user=require_context().user,
        di=di,
    )


@router.get(
    "/case-runs/{case_run_id}/pairwise-judgments",
    response_model=ListResponse[EvaluationPairwiseJudgment],
)
async def list_evaluation_pairwise_judgments_for_case_run(
    case_run_id: str,
    di: Di,
) -> ListResponse[EvaluationPairwiseJudgment]:
    return await op_flows_evaluation_pairwise_judgments_list(
        EvaluationCaseRunIdPayload(case_run_id=case_run_id),
        user=require_context().user,
        di=di,
    )


@router.post("/runs/{run_id}/annotations", response_model=EvaluationAnnotation)
async def create_evaluation_annotation(
    run_id: str,
    request: EvaluationAnnotationCreateRequest,
    di: Di,
) -> EvaluationAnnotation:
    return await op_flows_evaluation_annotation_create(
        request.model_copy(update={"run_id": run_id}),
        user=require_context().user,
        di=di,
    )


@router.get("/runs/{run_id}/annotations", response_model=ListResponse[EvaluationAnnotation])
async def list_evaluation_annotations(
    run_id: str,
    di: Di,
) -> ListResponse[EvaluationAnnotation]:
    return await op_flows_evaluation_annotations_list(
        EvaluationRunIdPayload(run_id=run_id),
        user=require_context().user,
        di=di,
    )


@router.put("/annotations/{annotation_id}", response_model=EvaluationAnnotation)
async def update_evaluation_annotation(
    annotation_id: str,
    request: EvaluationAnnotationUpdateRequest,
    di: Di,
) -> EvaluationAnnotation:
    return await op_flows_evaluation_annotation_update(
        request.model_copy(update={"annotation_id": annotation_id}),
        user=require_context().user,
        di=di,
    )


@router.delete("/annotations/{annotation_id}", response_model=EvaluationDeletedResponse)
async def delete_evaluation_annotation(
    annotation_id: str,
    di: Di,
) -> EvaluationDeletedResponse:
    return await op_flows_evaluation_annotation_delete(
        EvaluationAnnotationIdPayload(annotation_id=annotation_id),
        user=require_context().user,
        di=di,
    )


@router.get("/suites/{suite_id}/runs", response_model=ListResponse[EvaluationRun])
async def list_evaluation_runs(
    suite_id: str,
    di: Di,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ListResponse[EvaluationRun]:
    return await op_flows_evaluation_runs_list(
        EvaluationRunsListPayload(suite_id=suite_id, limit=limit),
        user=require_context().user,
        di=di,
    )


@router.get("/suites/{suite_id}/matrix", response_model=EvaluationResultsMatrix)
async def get_evaluation_results_matrix(
    suite_id: str,
    di: Di,
    branch_id: Annotated[str, Query(description="ID ветки")],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> EvaluationResultsMatrix:
    return await op_flows_evaluation_matrix_get(
        EvaluationMatrixPayload(suite_id=suite_id, branch_id=branch_id, limit=limit),
        user=require_context().user,
        di=di,
    )


@router.put("/suites/{suite_id}/baselines/{branch_id}", response_model=EvaluationBaseline)
async def set_evaluation_baseline(
    suite_id: str,
    branch_id: str,
    request: EvaluationBaselineSetRequest,
    di: Di,
) -> EvaluationBaseline:
    return await op_flows_evaluation_baseline_set(
        request.model_copy(update={"suite_id": suite_id, "branch_id": branch_id}),
        user=require_context().user,
        di=di,
    )


@router.get("/suites/{suite_id}/baselines", response_model=ListResponse[EvaluationBaseline])
async def list_evaluation_baselines(
    suite_id: str,
    di: Di,
) -> ListResponse[EvaluationBaseline]:
    return await op_flows_evaluation_baselines_list(
        EvaluationSuiteIdPayload(suite_id=suite_id),
        user=require_context().user,
        di=di,
    )


@router.get("/suites/{suite_id}/baselines/{branch_id}", response_model=EvaluationBaseline)
async def get_evaluation_baseline(
    suite_id: str,
    branch_id: str,
    di: Di,
) -> EvaluationBaseline:
    return await op_flows_evaluation_baseline_item(
        EvaluationBaselineItemPayload(suite_id=suite_id, branch_id=branch_id),
        user=require_context().user,
        di=di,
    )


@router.get("/suites/{suite_id}/baseline-compare", response_model=EvaluationBaselineComparison)
async def compare_evaluation_run_with_baseline(
    suite_id: str,
    di: Di,
    branch_id: Annotated[str, Query(description="ID ветки")],
    run_id: Annotated[str, Query(description="ID сравниваемого запуска")],
) -> EvaluationBaselineComparison:
    return await op_flows_evaluation_baseline_compare(
        EvaluationBaselineComparePayload(
            suite_id=suite_id,
            branch_id=branch_id,
            run_id=run_id,
        ),
        user=require_context().user,
        di=di,
    )


@router.post("/suites/{suite_id}/gate-policies", response_model=EvaluationGatePolicy)
async def create_evaluation_gate_policy(
    suite_id: str,
    request: EvaluationGatePolicyCreateRequest,
    di: Di,
) -> EvaluationGatePolicy:
    return await op_flows_evaluation_gate_policy_create(
        request.model_copy(update={"suite_id": suite_id}),
        user=require_context().user,
        di=di,
    )


@router.get("/suites/{suite_id}/gate-policies", response_model=ListResponse[EvaluationGatePolicy])
async def list_evaluation_gate_policies(
    suite_id: str,
    di: Di,
) -> ListResponse[EvaluationGatePolicy]:
    return await op_flows_evaluation_gate_policies_list(
        EvaluationSuiteIdPayload(suite_id=suite_id),
        user=require_context().user,
        di=di,
    )


@router.get("/gate-policies/{gate_policy_id}", response_model=EvaluationGatePolicy)
async def get_evaluation_gate_policy(
    gate_policy_id: str,
    di: Di,
) -> EvaluationGatePolicy:
    return await op_flows_evaluation_gate_policy_item(
        EvaluationGatePolicyIdPayload(gate_policy_id=gate_policy_id),
        user=require_context().user,
        di=di,
    )


@router.put("/gate-policies/{gate_policy_id}", response_model=EvaluationGatePolicy)
async def update_evaluation_gate_policy(
    gate_policy_id: str,
    request: EvaluationGatePolicyUpdateRequest,
    di: Di,
) -> EvaluationGatePolicy:
    return await op_flows_evaluation_gate_policy_update(
        request.model_copy(update={"gate_policy_id": gate_policy_id}),
        user=require_context().user,
        di=di,
    )


@router.post("/gate-policies/{gate_policy_id}/archive", response_model=EvaluationGatePolicy)
async def archive_evaluation_gate_policy(
    gate_policy_id: str,
    di: Di,
) -> EvaluationGatePolicy:
    return await op_flows_evaluation_gate_policy_archive(
        EvaluationGatePolicyIdPayload(gate_policy_id=gate_policy_id),
        user=require_context().user,
        di=di,
    )


@router.post("/gate-policies/{gate_policy_id}/run", response_model=EvaluationRunWithCases)
async def run_evaluation_gate_policy(
    gate_policy_id: str,
    request: EvaluationGatePolicyRunRequest,
    di: Di,
) -> EvaluationRunWithCases:
    return await op_flows_evaluation_gate_policy_run(
        request.model_copy(update={"gate_policy_id": gate_policy_id}),
        user=require_context().user,
        di=di,
    )


@router.get("/runs/{run_id}/gate-result", response_model=EvaluationGateResult)
async def get_evaluation_gate_result(
    run_id: str,
    di: Di,
) -> EvaluationGateResult:
    return await op_flows_evaluation_gate_result(
        EvaluationRunIdPayload(run_id=run_id),
        user=require_context().user,
        di=di,
    )


@router.post("/monitors", response_model=EvaluationMonitor)
async def create_evaluation_monitor(
    request: EvaluationMonitorCreateRequest,
    di: Di,
) -> EvaluationMonitor:
    return await op_flows_evaluation_monitor_create(
        request,
        user=require_context().user,
        di=di,
    )


@router.post("/monitor-cycles/run-active", response_model=EvaluationActiveMonitorCyclesResult)
async def run_active_evaluation_monitor_cycles(
    request: EvaluationActiveMonitorCyclesRequest,
    di: Di,
) -> EvaluationActiveMonitorCyclesResult:
    return await op_flows_evaluation_monitor_cycles_run_active(
        request,
        user=require_context().user,
        di=di,
    )


@router.get("/suites/{suite_id}/monitors", response_model=ListResponse[EvaluationMonitor])
async def list_evaluation_monitors(
    suite_id: str,
    di: Di,
) -> ListResponse[EvaluationMonitor]:
    return await op_flows_evaluation_monitors_list(
        EvaluationSuiteIdPayload(suite_id=suite_id),
        user=require_context().user,
        di=di,
    )


@router.get("/monitors/{monitor_id}", response_model=EvaluationMonitor)
async def get_evaluation_monitor(
    monitor_id: str,
    di: Di,
) -> EvaluationMonitor:
    return await op_flows_evaluation_monitor_item(
        EvaluationMonitorIdPayload(monitor_id=monitor_id),
        user=require_context().user,
        di=di,
    )


@router.put("/monitors/{monitor_id}", response_model=EvaluationMonitor)
async def update_evaluation_monitor(
    monitor_id: str,
    request: EvaluationMonitorUpdateRequest,
    di: Di,
) -> EvaluationMonitor:
    return await op_flows_evaluation_monitor_update(
        request.model_copy(update={"monitor_id": monitor_id}),
        user=require_context().user,
        di=di,
    )


@router.post("/monitors/{monitor_id}/archive", response_model=EvaluationMonitor)
async def archive_evaluation_monitor(
    monitor_id: str,
    di: Di,
) -> EvaluationMonitor:
    return await op_flows_evaluation_monitor_archive(
        EvaluationMonitorIdPayload(monitor_id=monitor_id),
        user=require_context().user,
        di=di,
    )


@router.post("/monitors/{monitor_id}/sample", response_model=EvaluationMonitorSampleResult)
async def sample_evaluation_monitor(
    monitor_id: str,
    request: EvaluationMonitorSampleRequest,
    di: Di,
) -> EvaluationMonitorSampleResult:
    return await op_flows_evaluation_monitor_sample(
        request.model_copy(update={"monitor_id": monitor_id}),
        user=require_context().user,
        di=di,
    )


@router.post("/monitors/{monitor_id}/run-cycle", response_model=EvaluationMonitorCycleResult)
async def run_evaluation_monitor_cycle(
    monitor_id: str,
    request: EvaluationMonitorCycleRequest,
    di: Di,
) -> EvaluationMonitorCycleResult:
    return await op_flows_evaluation_monitor_run_cycle(
        request.model_copy(update={"monitor_id": monitor_id}),
        user=require_context().user,
        di=di,
    )


@router.post(
    "/monitors/{monitor_id}/observations/{trace_id}/case",
    response_model=EvaluationMonitorObservationCurationResult,
)
async def create_evaluation_case_from_monitor_observation(
    monitor_id: str,
    trace_id: str,
    request: EvaluationMonitorObservationCaseCreateRequest,
    di: Di,
) -> EvaluationMonitorObservationCurationResult:
    return await op_flows_evaluation_monitor_observation_case_create(
        request.model_copy(update={"monitor_id": monitor_id, "trace_id": trace_id}),
        user=require_context().user,
        di=di,
    )


@router.get(
    "/monitors/{monitor_id}/observations",
    response_model=ListResponse[EvaluationMonitorObservation],
)
async def list_evaluation_monitor_observations(
    monitor_id: str,
    di: Di,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> ListResponse[EvaluationMonitorObservation]:
    return await op_flows_evaluation_monitor_observations(
        EvaluationMonitorObservationsPayload(monitor_id=monitor_id, limit=limit),
        user=require_context().user,
        di=di,
    )
