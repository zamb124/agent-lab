/**
 * Лаборатория Evaluation — фабрики UI-домена.
 * REST: `apps/flows/src/api/v1/evaluation.py` — тот же `op_*`, что WS.
 */

import { createAsyncOp, createSlice } from '@platform/lib/events/index.js';

function requireRecord(value, label) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
        throw new Error(`${label}: object payload required`);
    }
    return value;
}

function requireStringField(payload, field, label) {
    const value = payload[field];
    if (typeof value !== 'string' || value.length === 0) {
        throw new Error(`${label}: ${field} required`);
    }
    return value;
}

function optionalStringField(payload, field, label) {
    if (!Object.prototype.hasOwnProperty.call(payload, field)) {
        return '';
    }
    const value = payload[field];
    if (value === null) {
        return '';
    }
    if (typeof value !== 'string') {
        throw new Error(`${label}: ${field} must be string or null`);
    }
    return value;
}

function optionalNumberField(payload, field, label, defaultValue) {
    if (!Object.prototype.hasOwnProperty.call(payload, field)) {
        return defaultValue;
    }
    const value = payload[field];
    if (typeof value !== 'number' || !Number.isFinite(value)) {
        throw new Error(`${label}: ${field} must be a finite number`);
    }
    return Math.trunc(value);
}

function listItems(result, label) {
    if (!result || typeof result !== 'object' || !Array.isArray(result.items)) {
        throw new Error(`${label}: backend result.items required`);
    }
    return result.items;
}

function normalizePanel(value) {
    if (value === 'case' || value === 'compare' || value === 'trace' || value === 'monitoring') {
        return value;
    }
    throw new Error(`evaluation_ui: unsupported panel "${value}"`);
}

function normalizeFullscreenPanel(value) {
    if (
        value === '' ||
        value === 'matrix' ||
        value === 'transcript' ||
        value === 'case' ||
        value === 'compare' ||
        value === 'trace' ||
        value === 'monitoring'
    ) {
        return value;
    }
    throw new Error(`evaluation_ui: unsupported fullscreenPanel "${value}"`);
}

function normalizeRunScope(value) {
    if (value === 'suite' || value === 'selected_case') {
        return value;
    }
    throw new Error(`evaluation_ui: unsupported runScope "${value}"`);
}

function normalizePositiveInt(value, label) {
    if (typeof value !== 'number' || !Number.isFinite(value)) {
        throw new Error(`${label}: finite number required`);
    }
    const out = Math.trunc(value);
    if (out < 1) {
        throw new Error(`${label}: value must be >= 1`);
    }
    return out;
}

export const evaluationUiSlice = createSlice({
    name: 'flows/evaluation_ui',
    extraInitial: {
        selectedSuiteId: '',
        selectedCaseId: '',
        selectedRunId: '',
        selectedCaseRunId: '',
        selectedCompareRunId: '',
        activePanel: 'case',
        fullscreenPanel: '',
        runScope: 'suite',
        trials: 1,
        maxConcurrency: 1,
    },
    actions: {
        selectSuite: 'suite_selected',
        selectCase: 'case_selected',
        selectRun: 'run_selected',
        selectCaseRun: 'case_run_selected',
        selectCompareRun: 'compare_run_selected',
        setPanel: 'panel_set',
        setFullscreenPanel: 'fullscreen_panel_set',
        setRunScope: 'run_scope_set',
        setRunOptions: 'run_options_set',
        resetSelection: 'selection_reset',
    },
    extraReducer: (state, event, events) => {
        switch (event.type) {
            case events.SUITE_SELECTED: {
                const payload = requireRecord(event.payload, 'evaluation_ui.suite_selected');
                const suiteId = optionalStringField(payload, 'suite_id', 'evaluation_ui.suite_selected');
                return {
                    ...state,
                    selectedSuiteId: suiteId,
                    selectedCaseId: '',
                    selectedRunId: '',
                    selectedCaseRunId: '',
                    selectedCompareRunId: '',
                    fullscreenPanel: '',
                };
            }
            case events.CASE_SELECTED: {
                const payload = requireRecord(event.payload, 'evaluation_ui.case_selected');
                return {
                    ...state,
                    selectedCaseId: optionalStringField(payload, 'case_id', 'evaluation_ui.case_selected'),
                    selectedCaseRunId: '',
                };
            }
            case events.RUN_SELECTED: {
                const payload = requireRecord(event.payload, 'evaluation_ui.run_selected');
                return {
                    ...state,
                    selectedRunId: optionalStringField(payload, 'run_id', 'evaluation_ui.run_selected'),
                    selectedCaseRunId: '',
                };
            }
            case events.CASE_RUN_SELECTED: {
                const payload = requireRecord(event.payload, 'evaluation_ui.case_run_selected');
                return {
                    ...state,
                    selectedCaseRunId: optionalStringField(payload, 'case_run_id', 'evaluation_ui.case_run_selected'),
                    activePanel: 'trace',
                    fullscreenPanel: '',
                };
            }
            case events.COMPARE_RUN_SELECTED: {
                const payload = requireRecord(event.payload, 'evaluation_ui.compare_run_selected');
                return {
                    ...state,
                    selectedCompareRunId: optionalStringField(payload, 'run_id', 'evaluation_ui.compare_run_selected'),
                    activePanel: 'compare',
                    fullscreenPanel: '',
                };
            }
            case events.PANEL_SET: {
                const payload = requireRecord(event.payload, 'evaluation_ui.panel_set');
                return {
                    ...state,
                    activePanel: normalizePanel(requireStringField(payload, 'panel', 'evaluation_ui.panel_set')),
                    fullscreenPanel: '',
                };
            }
            case events.FULLSCREEN_PANEL_SET: {
                const payload = requireRecord(event.payload, 'evaluation_ui.fullscreen_panel_set');
                return {
                    ...state,
                    fullscreenPanel: normalizeFullscreenPanel(optionalStringField(payload, 'panel', 'evaluation_ui.fullscreen_panel_set')),
                };
            }
            case events.RUN_SCOPE_SET: {
                const payload = requireRecord(event.payload, 'evaluation_ui.run_scope_set');
                return {
                    ...state,
                    runScope: normalizeRunScope(requireStringField(payload, 'scope', 'evaluation_ui.run_scope_set')),
                };
            }
            case events.RUN_OPTIONS_SET: {
                const payload = requireRecord(event.payload, 'evaluation_ui.run_options_set');
                return {
                    ...state,
                    trials: normalizePositiveInt(optionalNumberField(payload, 'trials', 'evaluation_ui.run_options_set', state.trials), 'evaluation_ui.trials'),
                    maxConcurrency: normalizePositiveInt(optionalNumberField(payload, 'max_concurrency', 'evaluation_ui.run_options_set', state.maxConcurrency), 'evaluation_ui.maxConcurrency'),
                };
            }
            case events.SELECTION_RESET:
                return {
                    selectedSuiteId: '',
                    selectedCaseId: '',
                    selectedRunId: '',
                    selectedCaseRunId: '',
                    selectedCompareRunId: '',
                    activePanel: 'case',
                    fullscreenPanel: '',
                    runScope: 'suite',
                    trials: 1,
                    maxConcurrency: 1,
                };
            default:
                return state;
        }
    },
});

export const evaluationEvaluatorCatalogOp = createAsyncOp({
    name: 'flows/evaluation_evaluator_catalog',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/evaluation/evaluator_catalog_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/evaluation/evaluator-catalog' },
});

export const evaluationSuitesListOp = createAsyncOp({
    name: 'flows/evaluation_suites_list',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/evaluation/suites_list_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/evaluation/suites' },
});

export const evaluationSuiteCreateOp = createAsyncOp({
    name: 'flows/evaluation_suite_create',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/evaluation/suite_create_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/evaluation/suites' },
});

export const evaluationSuiteUpdateOp = createAsyncOp({
    name: 'flows/evaluation_suite_update',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/evaluation/suite_update_requested',
    restMirror: { method: 'PUT', path: '/flows/api/v1/evaluation/suites/{suite_id}' },
});

export const evaluationSuiteArchiveOp = createAsyncOp({
    name: 'flows/evaluation_suite_archive',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/evaluation/suite_archive_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/evaluation/suites/{suite_id}/archive' },
});

export const evaluationCasesListOp = createAsyncOp({
    name: 'flows/evaluation_cases_list',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/evaluation/cases_list_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/evaluation/suites/{suite_id}/cases' },
});

export const evaluationCaseCreateOp = createAsyncOp({
    name: 'flows/evaluation_case_create',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/evaluation/case_create_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/evaluation/suites/{suite_id}/cases' },
});

export const evaluationCaseUpdateOp = createAsyncOp({
    name: 'flows/evaluation_case_update',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/evaluation/case_update_requested',
    restMirror: { method: 'PUT', path: '/flows/api/v1/evaluation/suites/{suite_id}/cases/{case_id}' },
});

export const evaluationCaseDeleteOp = createAsyncOp({
    name: 'flows/evaluation_case_delete',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/evaluation/case_delete_requested',
    restMirror: { method: 'DELETE', path: '/flows/api/v1/evaluation/suites/{suite_id}/cases/{case_id}' },
});

export const evaluationCaseImportOp = createAsyncOp({
    name: 'flows/evaluation_case_import',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 30_000,
    commandType: 'flows/evaluation/case_import_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/evaluation/suites/{suite_id}/cases/import' },
});

export const evaluationCaseFromDialogOp = createAsyncOp({
    name: 'flows/evaluation_case_from_dialog',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/evaluation/case_from_dialog_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/evaluation/suites/{suite_id}/cases/from-dialog' },
});

export const evaluationCaseFromTraceOp = createAsyncOp({
    name: 'flows/evaluation_case_from_trace',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/evaluation/case_from_trace_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/evaluation/suites/{suite_id}/cases/from-trace' },
});

export const evaluationRunsListOp = createAsyncOp({
    name: 'flows/evaluation_runs_list',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/evaluation/runs_list_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/evaluation/suites/{suite_id}/runs' },
    extraEffect: async (event, ctx, events) => {
        if (event.type !== 'flows/evaluation/event') {
            return false;
        }
        const payload = event.payload && typeof event.payload === 'object' ? event.payload : null;
        const runId = payload && typeof payload.run_id === 'string' ? payload.run_id : '';
        const ui = ctx.getState().flowsEvaluationUi;
        if (!ui || typeof ui !== 'object') {
            return true;
        }
        const selectedSuiteId = typeof ui.selectedSuiteId === 'string' ? ui.selectedSuiteId : '';
        const selectedRunId = typeof ui.selectedRunId === 'string' ? ui.selectedRunId : '';
        const meta = { causation_id: event.id, source: 'ws' };
        if (selectedSuiteId.length > 0) {
            ctx.dispatch(events.REQUESTED, { suite_id: selectedSuiteId, limit: 30 }, meta);
            ctx.dispatch(
                evaluationMatrixGetOp.events.REQUESTED,
                { suite_id: selectedSuiteId, branch_id: 'default', limit: 16 },
                meta,
            );
        }
        if (runId.length > 0 && runId === selectedRunId) {
            ctx.dispatch(evaluationRunGetOp.events.REQUESTED, { run_id: runId }, meta);
            ctx.dispatch(evaluationRunEventsOp.events.REQUESTED, { run_id: runId }, meta);
            ctx.dispatch(evaluationAnnotationsListOp.events.REQUESTED, { run_id: runId }, meta);
        }
        return true;
    },
});

export const evaluationRunCreateOp = createAsyncOp({
    name: 'flows/evaluation_run_create',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 30_000,
    commandType: 'flows/evaluation/run_create_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/evaluation/runs' },
});

export const evaluationRunGetOp = createAsyncOp({
    name: 'flows/evaluation_run_get',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/evaluation/run_get_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/evaluation/runs/{run_id}' },
});

export const evaluationRunCancelOp = createAsyncOp({
    name: 'flows/evaluation_run_cancel',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/evaluation/run_cancel_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/evaluation/runs/{run_id}/cancel' },
});

export const evaluationRunCasesOp = createAsyncOp({
    name: 'flows/evaluation_run_cases',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/evaluation/run_cases_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/evaluation/runs/{run_id}/cases' },
});

export const evaluationRunEventsOp = createAsyncOp({
    name: 'flows/evaluation_run_events',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/evaluation/run_events_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/evaluation/runs/{run_id}/events' },
});

export const evaluationRunEventsPageOp = createAsyncOp({
    name: 'flows/evaluation_run_events_page',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/evaluation/run_events_page_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/evaluation/runs/{run_id}/events-page' },
});

export const evaluationMatrixGetOp = createAsyncOp({
    name: 'flows/evaluation_matrix_get',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/evaluation/matrix_get_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/evaluation/suites/{suite_id}/matrix' },
});

export const evaluationCompareRunsOp = createAsyncOp({
    name: 'flows/evaluation_compare_runs',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/evaluation/compare_runs_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/evaluation/runs/compare' },
});

export const evaluationCaseRunTraceOp = createAsyncOp({
    name: 'flows/evaluation_case_run_trace',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/evaluation/case_run_trace_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/evaluation/case-runs/{case_run_id}/trace' },
});

export const evaluationAnnotationsListOp = createAsyncOp({
    name: 'flows/evaluation_annotations_list',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/evaluation/annotations_list_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/evaluation/runs/{run_id}/annotations' },
});

export const evaluationAnnotationCreateOp = createAsyncOp({
    name: 'flows/evaluation_annotation_create',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/evaluation/annotation_create_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/evaluation/runs/{run_id}/annotations' },
});

export const evaluationBaselinesListOp = createAsyncOp({
    name: 'flows/evaluation_baselines_list',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/evaluation/baselines_list_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/evaluation/suites/{suite_id}/baselines' },
});

export const evaluationBaselineSetOp = createAsyncOp({
    name: 'flows/evaluation_baseline_set',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/evaluation/baseline_set_requested',
    restMirror: { method: 'PUT', path: '/flows/api/v1/evaluation/suites/{suite_id}/baselines/{branch_id}' },
});

export const evaluationGatePoliciesListOp = createAsyncOp({
    name: 'flows/evaluation_gate_policies_list',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/evaluation/gate_policies_list_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/evaluation/suites/{suite_id}/gate-policies' },
});

export const evaluationMonitorsListOp = createAsyncOp({
    name: 'flows/evaluation_monitors_list',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/evaluation/monitors_list_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/evaluation/suites/{suite_id}/monitors' },
});

export const evaluationMonitorObservationsOp = createAsyncOp({
    name: 'flows/evaluation_monitor_observations',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/evaluation/monitor_observations_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/evaluation/monitors/{monitor_id}/observations' },
});

export const evaluationPairwiseJudgmentCreateOp = createAsyncOp({
    name: 'flows/evaluation_pairwise_judgment_create',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 30_000,
    commandType: 'flows/evaluation/pairwise_judgment_create_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/evaluation/pairwise-judgments' },
});

export const evaluationMonitorObservationCaseCreateOp = createAsyncOp({
    name: 'flows/evaluation_monitor_observation_case_create',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/evaluation/monitor_observation_case_create_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/evaluation/monitors/{monitor_id}/observations/{trace_id}/case' },
});

export const evaluationRubricsListOp = createAsyncOp({
    name: 'flows/evaluation_rubrics_list',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/evaluation/rubrics_list_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/evaluation/rubrics' },
});

export const evaluationRubricCreateOp = createAsyncOp({
    name: 'flows/evaluation_rubric_create',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/evaluation/rubric_create_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/evaluation/rubrics' },
});

export const evaluationRubricVersionsListOp = createAsyncOp({
    name: 'flows/evaluation_rubric_versions_list',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/evaluation/rubric_versions_list_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/evaluation/rubrics/{rubric_id}/versions' },
});

export const evaluationRubricVersionCreateOp = createAsyncOp({
    name: 'flows/evaluation_rubric_version_create',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/evaluation/rubric_version_create_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/evaluation/rubrics/{rubric_id}/versions' },
});

export function requireEvaluationItems(result, label) {
    return listItems(result, label);
}
