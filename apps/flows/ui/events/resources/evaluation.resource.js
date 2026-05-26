/**
 * Evaluation Lab — фабрики UI-домена.
 *
 * Компоненты Evaluation Lab не ходят в HTTP напрямую. Все CRUD/command/read
 * операции идут через эти createAsyncOp-фабрики, а выбранные сущности держатся
 * в typed slice `flows/evaluation_ui`.
 */

import { createAsyncOp, createSlice } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

const API_ROOT = '/flows/api/v1/evaluation';

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

function requireBody(payload, label) {
    const body = payload.body;
    if (!body || typeof body !== 'object' || Array.isArray(body)) {
        throw new Error(`${label}: body object required`);
    }
    return body;
}

function encoded(value) {
    return encodeURIComponent(value);
}

function buildQuery(path, entries) {
    const params = new URLSearchParams();
    for (const [key, value] of entries) {
        if (value === null || value === undefined) {
            continue;
        }
        if (typeof value === 'string') {
            if (value.length > 0) {
                params.set(key, value);
            }
            continue;
        }
        if (typeof value === 'number') {
            if (!Number.isFinite(value)) {
                throw new Error(`buildQuery: ${key} must be finite`);
            }
            params.set(key, String(Math.trunc(value)));
            continue;
        }
        if (typeof value === 'boolean') {
            params.set(key, value ? 'true' : 'false');
            continue;
        }
        throw new Error(`buildQuery: unsupported value for ${key}`);
    }
    const query = params.toString();
    return query.length > 0 ? `${path}?${query}` : path;
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
    restMirror: { method: 'GET', path: '/flows/api/v1/evaluation/evaluator-catalog' },
    request: async () => httpRequest({ method: 'GET', url: `${API_ROOT}/evaluator-catalog` }),
});

export const evaluationSuitesListOp = createAsyncOp({
    name: 'flows/evaluation_suites_list',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/evaluation/suites' },
    request: async ({ payload }) => {
        const data = requireRecord(payload, 'evaluationSuitesListOp');
        const flowId = requireStringField(data, 'flow_id', 'evaluationSuitesListOp');
        return httpRequest({
            method: 'GET',
            url: buildQuery(`${API_ROOT}/suites`, [['flow_id', flowId]]),
        });
    },
});

export const evaluationSuiteCreateOp = createAsyncOp({
    name: 'flows/evaluation_suite_create',
    silent: true,
    restMirror: { method: 'POST', path: '/flows/api/v1/evaluation/suites' },
    request: async ({ payload }) => {
        const data = requireRecord(payload, 'evaluationSuiteCreateOp');
        return httpRequest({
            method: 'POST',
            url: `${API_ROOT}/suites`,
            body: requireBody(data, 'evaluationSuiteCreateOp'),
        });
    },
});

export const evaluationSuiteUpdateOp = createAsyncOp({
    name: 'flows/evaluation_suite_update',
    silent: true,
    restMirror: { method: 'PUT', path: '/flows/api/v1/evaluation/suites/{suite_id}' },
    request: async ({ payload }) => {
        const data = requireRecord(payload, 'evaluationSuiteUpdateOp');
        const suiteId = requireStringField(data, 'suite_id', 'evaluationSuiteUpdateOp');
        return httpRequest({
            method: 'PUT',
            url: `${API_ROOT}/suites/${encoded(suiteId)}`,
            body: requireBody(data, 'evaluationSuiteUpdateOp'),
        });
    },
});

export const evaluationSuiteArchiveOp = createAsyncOp({
    name: 'flows/evaluation_suite_archive',
    silent: true,
    restMirror: { method: 'POST', path: '/flows/api/v1/evaluation/suites/{suite_id}/archive' },
    request: async ({ payload }) => {
        const data = requireRecord(payload, 'evaluationSuiteArchiveOp');
        const suiteId = requireStringField(data, 'suite_id', 'evaluationSuiteArchiveOp');
        return httpRequest({
            method: 'POST',
            url: `${API_ROOT}/suites/${encoded(suiteId)}/archive`,
            body: {},
        });
    },
});

export const evaluationCasesListOp = createAsyncOp({
    name: 'flows/evaluation_cases_list',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/evaluation/suites/{suite_id}/cases' },
    request: async ({ payload }) => {
        const data = requireRecord(payload, 'evaluationCasesListOp');
        const suiteId = requireStringField(data, 'suite_id', 'evaluationCasesListOp');
        return httpRequest({ method: 'GET', url: `${API_ROOT}/suites/${encoded(suiteId)}/cases` });
    },
});

export const evaluationCaseCreateOp = createAsyncOp({
    name: 'flows/evaluation_case_create',
    silent: true,
    restMirror: { method: 'POST', path: '/flows/api/v1/evaluation/suites/{suite_id}/cases' },
    request: async ({ payload }) => {
        const data = requireRecord(payload, 'evaluationCaseCreateOp');
        const suiteId = requireStringField(data, 'suite_id', 'evaluationCaseCreateOp');
        return httpRequest({
            method: 'POST',
            url: `${API_ROOT}/suites/${encoded(suiteId)}/cases`,
            body: requireBody(data, 'evaluationCaseCreateOp'),
        });
    },
});

export const evaluationCaseUpdateOp = createAsyncOp({
    name: 'flows/evaluation_case_update',
    silent: true,
    restMirror: { method: 'PUT', path: '/flows/api/v1/evaluation/suites/{suite_id}/cases/{case_id}' },
    request: async ({ payload }) => {
        const data = requireRecord(payload, 'evaluationCaseUpdateOp');
        const suiteId = requireStringField(data, 'suite_id', 'evaluationCaseUpdateOp');
        const caseId = requireStringField(data, 'case_id', 'evaluationCaseUpdateOp');
        return httpRequest({
            method: 'PUT',
            url: `${API_ROOT}/suites/${encoded(suiteId)}/cases/${encoded(caseId)}`,
            body: requireBody(data, 'evaluationCaseUpdateOp'),
        });
    },
});

export const evaluationCaseDeleteOp = createAsyncOp({
    name: 'flows/evaluation_case_delete',
    silent: true,
    restMirror: { method: 'DELETE', path: '/flows/api/v1/evaluation/suites/{suite_id}/cases/{case_id}' },
    request: async ({ payload }) => {
        const data = requireRecord(payload, 'evaluationCaseDeleteOp');
        const suiteId = requireStringField(data, 'suite_id', 'evaluationCaseDeleteOp');
        const caseId = requireStringField(data, 'case_id', 'evaluationCaseDeleteOp');
        return httpRequest({
            method: 'DELETE',
            url: `${API_ROOT}/suites/${encoded(suiteId)}/cases/${encoded(caseId)}`,
        });
    },
});

export const evaluationCaseImportOp = createAsyncOp({
    name: 'flows/evaluation_case_import',
    silent: true,
    restMirror: { method: 'POST', path: '/flows/api/v1/evaluation/suites/{suite_id}/cases/import' },
    request: async ({ payload }) => {
        const data = requireRecord(payload, 'evaluationCaseImportOp');
        const suiteId = requireStringField(data, 'suite_id', 'evaluationCaseImportOp');
        return httpRequest({
            method: 'POST',
            url: `${API_ROOT}/suites/${encoded(suiteId)}/cases/import`,
            body: requireBody(data, 'evaluationCaseImportOp'),
        });
    },
});

export const evaluationCaseFromDialogOp = createAsyncOp({
    name: 'flows/evaluation_case_from_dialog',
    silent: true,
    restMirror: { method: 'POST', path: '/flows/api/v1/evaluation/suites/{suite_id}/cases/from-dialog' },
    request: async ({ payload }) => {
        const data = requireRecord(payload, 'evaluationCaseFromDialogOp');
        const suiteId = requireStringField(data, 'suite_id', 'evaluationCaseFromDialogOp');
        return httpRequest({
            method: 'POST',
            url: `${API_ROOT}/suites/${encoded(suiteId)}/cases/from-dialog`,
            body: requireBody(data, 'evaluationCaseFromDialogOp'),
        });
    },
});

export const evaluationCaseFromTraceOp = createAsyncOp({
    name: 'flows/evaluation_case_from_trace',
    silent: true,
    restMirror: { method: 'POST', path: '/flows/api/v1/evaluation/suites/{suite_id}/cases/from-trace' },
    request: async ({ payload }) => {
        const data = requireRecord(payload, 'evaluationCaseFromTraceOp');
        const suiteId = requireStringField(data, 'suite_id', 'evaluationCaseFromTraceOp');
        return httpRequest({
            method: 'POST',
            url: `${API_ROOT}/suites/${encoded(suiteId)}/cases/from-trace`,
            body: requireBody(data, 'evaluationCaseFromTraceOp'),
        });
    },
});

export const evaluationRunsListOp = createAsyncOp({
    name: 'flows/evaluation_runs_list',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/evaluation/suites/{suite_id}/runs' },
    request: async ({ payload }) => {
        const data = requireRecord(payload, 'evaluationRunsListOp');
        const suiteId = requireStringField(data, 'suite_id', 'evaluationRunsListOp');
        const limit = optionalNumberField(data, 'limit', 'evaluationRunsListOp', 30);
        return httpRequest({
            method: 'GET',
            url: buildQuery(`${API_ROOT}/suites/${encoded(suiteId)}/runs`, [['limit', limit]]),
        });
    },
});

export const evaluationRunCreateOp = createAsyncOp({
    name: 'flows/evaluation_run_create',
    silent: true,
    restMirror: { method: 'POST', path: '/flows/api/v1/evaluation/runs' },
    request: async ({ payload }) => {
        const data = requireRecord(payload, 'evaluationRunCreateOp');
        return httpRequest({
            method: 'POST',
            url: `${API_ROOT}/runs`,
            body: requireBody(data, 'evaluationRunCreateOp'),
        });
    },
});

export const evaluationRunGetOp = createAsyncOp({
    name: 'flows/evaluation_run_get',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/evaluation/runs/{run_id}' },
    request: async ({ payload }) => {
        const data = requireRecord(payload, 'evaluationRunGetOp');
        const runId = requireStringField(data, 'run_id', 'evaluationRunGetOp');
        return httpRequest({ method: 'GET', url: `${API_ROOT}/runs/${encoded(runId)}` });
    },
});

export const evaluationRunCancelOp = createAsyncOp({
    name: 'flows/evaluation_run_cancel',
    silent: true,
    restMirror: { method: 'POST', path: '/flows/api/v1/evaluation/runs/{run_id}/cancel' },
    request: async ({ payload }) => {
        const data = requireRecord(payload, 'evaluationRunCancelOp');
        const runId = requireStringField(data, 'run_id', 'evaluationRunCancelOp');
        return httpRequest({ method: 'POST', url: `${API_ROOT}/runs/${encoded(runId)}/cancel`, body: {} });
    },
});

export const evaluationRunCasesOp = createAsyncOp({
    name: 'flows/evaluation_run_cases',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/evaluation/runs/{run_id}/cases' },
    request: async ({ payload }) => {
        const data = requireRecord(payload, 'evaluationRunCasesOp');
        const runId = requireStringField(data, 'run_id', 'evaluationRunCasesOp');
        return httpRequest({ method: 'GET', url: `${API_ROOT}/runs/${encoded(runId)}/cases` });
    },
});

export const evaluationRunEventsOp = createAsyncOp({
    name: 'flows/evaluation_run_events',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/evaluation/runs/{run_id}/events' },
    request: async ({ payload }) => {
        const data = requireRecord(payload, 'evaluationRunEventsOp');
        const runId = requireStringField(data, 'run_id', 'evaluationRunEventsOp');
        return httpRequest({ method: 'GET', url: `${API_ROOT}/runs/${encoded(runId)}/events` });
    },
});

export const evaluationRunEventsPageOp = createAsyncOp({
    name: 'flows/evaluation_run_events_page',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/evaluation/runs/{run_id}/events-page' },
    request: async ({ payload }) => {
        const data = requireRecord(payload, 'evaluationRunEventsPageOp');
        const runId = requireStringField(data, 'run_id', 'evaluationRunEventsPageOp');
        const afterSequence = optionalNumberField(data, 'after_sequence', 'evaluationRunEventsPageOp', 0);
        const limit = optionalNumberField(data, 'limit', 'evaluationRunEventsPageOp', 200);
        return httpRequest({
            method: 'GET',
            url: buildQuery(`${API_ROOT}/runs/${encoded(runId)}/events-page`, [
                ['after_sequence', afterSequence],
                ['limit', limit],
            ]),
        });
    },
});

export const evaluationMatrixGetOp = createAsyncOp({
    name: 'flows/evaluation_matrix_get',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/evaluation/suites/{suite_id}/matrix' },
    request: async ({ payload }) => {
        const data = requireRecord(payload, 'evaluationMatrixGetOp');
        const suiteId = requireStringField(data, 'suite_id', 'evaluationMatrixGetOp');
        const branchId = optionalStringField(data, 'branch_id', 'evaluationMatrixGetOp');
        const limit = optionalNumberField(data, 'limit', 'evaluationMatrixGetOp', 12);
        return httpRequest({
            method: 'GET',
            url: buildQuery(`${API_ROOT}/suites/${encoded(suiteId)}/matrix`, [
                ['branch_id', branchId],
                ['limit', limit],
            ]),
        });
    },
});

export const evaluationCompareRunsOp = createAsyncOp({
    name: 'flows/evaluation_compare_runs',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/evaluation/runs/compare' },
    request: async ({ payload }) => {
        const data = requireRecord(payload, 'evaluationCompareRunsOp');
        const leftRunId = requireStringField(data, 'left_run_id', 'evaluationCompareRunsOp');
        const rightRunId = requireStringField(data, 'right_run_id', 'evaluationCompareRunsOp');
        return httpRequest({
            method: 'GET',
            url: buildQuery(`${API_ROOT}/runs/compare`, [
                ['left_run_id', leftRunId],
                ['right_run_id', rightRunId],
            ]),
        });
    },
});

export const evaluationCaseRunTraceOp = createAsyncOp({
    name: 'flows/evaluation_case_run_trace',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/evaluation/case-runs/{case_run_id}/trace' },
    request: async ({ payload }) => {
        const data = requireRecord(payload, 'evaluationCaseRunTraceOp');
        const caseRunId = requireStringField(data, 'case_run_id', 'evaluationCaseRunTraceOp');
        return httpRequest({ method: 'GET', url: `${API_ROOT}/case-runs/${encoded(caseRunId)}/trace` });
    },
});

export const evaluationAnnotationsListOp = createAsyncOp({
    name: 'flows/evaluation_annotations_list',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/evaluation/runs/{run_id}/annotations' },
    request: async ({ payload }) => {
        const data = requireRecord(payload, 'evaluationAnnotationsListOp');
        const runId = requireStringField(data, 'run_id', 'evaluationAnnotationsListOp');
        return httpRequest({ method: 'GET', url: `${API_ROOT}/runs/${encoded(runId)}/annotations` });
    },
});

export const evaluationAnnotationCreateOp = createAsyncOp({
    name: 'flows/evaluation_annotation_create',
    silent: true,
    restMirror: { method: 'POST', path: '/flows/api/v1/evaluation/runs/{run_id}/annotations' },
    request: async ({ payload }) => {
        const data = requireRecord(payload, 'evaluationAnnotationCreateOp');
        const runId = requireStringField(data, 'run_id', 'evaluationAnnotationCreateOp');
        return httpRequest({
            method: 'POST',
            url: `${API_ROOT}/runs/${encoded(runId)}/annotations`,
            body: requireBody(data, 'evaluationAnnotationCreateOp'),
        });
    },
});

export const evaluationBaselinesListOp = createAsyncOp({
    name: 'flows/evaluation_baselines_list',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/evaluation/suites/{suite_id}/baselines' },
    request: async ({ payload }) => {
        const data = requireRecord(payload, 'evaluationBaselinesListOp');
        const suiteId = requireStringField(data, 'suite_id', 'evaluationBaselinesListOp');
        return httpRequest({ method: 'GET', url: `${API_ROOT}/suites/${encoded(suiteId)}/baselines` });
    },
});

export const evaluationBaselineSetOp = createAsyncOp({
    name: 'flows/evaluation_baseline_set',
    silent: true,
    restMirror: { method: 'PUT', path: '/flows/api/v1/evaluation/suites/{suite_id}/baselines/{branch_id}' },
    request: async ({ payload }) => {
        const data = requireRecord(payload, 'evaluationBaselineSetOp');
        const suiteId = requireStringField(data, 'suite_id', 'evaluationBaselineSetOp');
        const branchId = requireStringField(data, 'branch_id', 'evaluationBaselineSetOp');
        return httpRequest({
            method: 'PUT',
            url: `${API_ROOT}/suites/${encoded(suiteId)}/baselines/${encoded(branchId)}`,
            body: requireBody(data, 'evaluationBaselineSetOp'),
        });
    },
});

export const evaluationGatePoliciesListOp = createAsyncOp({
    name: 'flows/evaluation_gate_policies_list',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/evaluation/suites/{suite_id}/gate-policies' },
    request: async ({ payload }) => {
        const data = requireRecord(payload, 'evaluationGatePoliciesListOp');
        const suiteId = requireStringField(data, 'suite_id', 'evaluationGatePoliciesListOp');
        return httpRequest({ method: 'GET', url: `${API_ROOT}/suites/${encoded(suiteId)}/gate-policies` });
    },
});

export const evaluationMonitorsListOp = createAsyncOp({
    name: 'flows/evaluation_monitors_list',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/evaluation/suites/{suite_id}/monitors' },
    request: async ({ payload }) => {
        const data = requireRecord(payload, 'evaluationMonitorsListOp');
        const suiteId = requireStringField(data, 'suite_id', 'evaluationMonitorsListOp');
        return httpRequest({ method: 'GET', url: `${API_ROOT}/suites/${encoded(suiteId)}/monitors` });
    },
});

export const evaluationMonitorObservationsOp = createAsyncOp({
    name: 'flows/evaluation_monitor_observations',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/evaluation/monitors/{monitor_id}/observations' },
    request: async ({ payload }) => {
        const data = requireRecord(payload, 'evaluationMonitorObservationsOp');
        const monitorId = requireStringField(data, 'monitor_id', 'evaluationMonitorObservationsOp');
        const limit = optionalNumberField(data, 'limit', 'evaluationMonitorObservationsOp', 30);
        return httpRequest({
            method: 'GET',
            url: buildQuery(`${API_ROOT}/monitors/${encoded(monitorId)}/observations`, [['limit', limit]]),
        });
    },
});

export const evaluationPairwiseJudgmentCreateOp = createAsyncOp({
    name: 'flows/evaluation_pairwise_judgment_create',
    silent: true,
    restMirror: { method: 'POST', path: '/flows/api/v1/evaluation/pairwise-judgments' },
    request: async ({ payload }) => {
        const data = requireRecord(payload, 'evaluationPairwiseJudgmentCreateOp');
        return httpRequest({
            method: 'POST',
            url: `${API_ROOT}/pairwise-judgments`,
            body: requireBody(data, 'evaluationPairwiseJudgmentCreateOp'),
        });
    },
});

export const evaluationMonitorObservationCaseCreateOp = createAsyncOp({
    name: 'flows/evaluation_monitor_observation_case_create',
    silent: true,
    restMirror: { method: 'POST', path: '/flows/api/v1/evaluation/monitors/{monitor_id}/observations/{trace_id}/case' },
    request: async ({ payload }) => {
        const data = requireRecord(payload, 'evaluationMonitorObservationCaseCreateOp');
        const monitorId = requireStringField(data, 'monitor_id', 'evaluationMonitorObservationCaseCreateOp');
        const traceId = requireStringField(data, 'trace_id', 'evaluationMonitorObservationCaseCreateOp');
        return httpRequest({
            method: 'POST',
            url: `${API_ROOT}/monitors/${encoded(monitorId)}/observations/${encoded(traceId)}/case`,
            body: requireBody(data, 'evaluationMonitorObservationCaseCreateOp'),
        });
    },
});

export function requireEvaluationItems(result, label) {
    return listItems(result, label);
}
