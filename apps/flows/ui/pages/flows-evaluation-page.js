import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-help-hint.js';
import '../components/evaluation/flows-evaluation-suite-sidebar.js';
import '../components/evaluation/flows-evaluation-run-toolbar.js';
import '../components/evaluation/flows-evaluation-results-matrix.js';
import '../components/evaluation/flows-evaluation-transcript.js';
import '../components/evaluation/flows-evaluation-case-editor.js';
import '../components/evaluation/flows-evaluation-compare-panel.js';
import '../components/evaluation/flows-evaluation-trace-panel.js';
import { evaluationCatalogDescriptionKey, evaluationCatalogNameKey } from '../_helpers/evaluation-catalog-labels.js';

function asArray(value) {
    return Array.isArray(value) ? value : [];
}

function stringValue(record, field) {
    if (!record || typeof record !== 'object') {
        return '';
    }
    const value = record[field];
    return typeof value === 'string' ? value : '';
}

function objectValue(record, field) {
    if (!record || typeof record !== 'object') {
        return null;
    }
    const value = record[field];
    return value && typeof value === 'object' && !Array.isArray(value) ? value : null;
}

function itemsFromResult(result) {
    if (!result || typeof result !== 'object') {
        return [];
    }
    return Array.isArray(result.items) ? result.items : [];
}

function findById(items, field, id) {
    if (id.length === 0) {
        return null;
    }
    const found = asArray(items).find((item) => stringValue(item, field) === id);
    return found ? found : null;
}

function matrixCell(matrix, runId, caseId) {
    if (!matrix || typeof matrix !== 'object') {
        return null;
    }
    const found = asArray(matrix.cells).find((cell) => stringValue(cell, 'run_id') === runId && stringValue(cell, 'case_id') === caseId);
    return found ? found : null;
}

function caseIdForCaseRun(matrix, caseRunId) {
    if (!matrix || typeof matrix !== 'object') {
        return '';
    }
    const found = asArray(matrix.cells).find((cell) => stringValue(cell, 'case_run_id') === caseRunId);
    return found ? stringValue(found, 'case_id') : '';
}

function runStateIsActive(run) {
    const state = stringValue(run, 'state');
    return state === 'queued' || state === 'running';
}

function boolValue(record, field) {
    if (!record || typeof record !== 'object') {
        return false;
    }
    return record[field] === true;
}

const STATIC_CASE_TEMPLATES = Object.freeze([
    { id: 'contains_response', category: 'deterministic', icon: 'search-check', nameKey: 'contains_name', descriptionKey: 'contains_description' },
    { id: 'not_contains_response', category: 'deterministic', icon: 'shield', nameKey: 'not_contains_name', descriptionKey: 'not_contains_description' },
    { id: 'regex_response', category: 'deterministic', icon: 'code', nameKey: 'regex_name', descriptionKey: 'regex_description' },
    { id: 'length_response', category: 'deterministic', icon: 'list', nameKey: 'length_name', descriptionKey: 'length_description' },
    { id: 'state_path', category: 'deterministic', icon: 'braces', nameKey: 'state_path_name', descriptionKey: 'state_path_description' },
    { id: 'json_schema_response', category: 'deterministic', icon: 'table', nameKey: 'json_schema_name', descriptionKey: 'json_schema_description' },
    { id: 'trace_tool_called', category: 'trace', icon: 'tool', nameKey: 'trace_tool_name', descriptionKey: 'trace_tool_description' },
    { id: 'trace_node_completed', category: 'trace', icon: 'workflow', nameKey: 'trace_node_name', descriptionKey: 'trace_node_description' },
    { id: 'trace_node_failed', category: 'trace', icon: 'warning', nameKey: 'trace_node_failed_name', descriptionKey: 'trace_node_failed_description' },
    { id: 'code_python', category: 'advanced', icon: 'code', nameKey: 'code_name', descriptionKey: 'code_description' },
    { id: 'llm_judge', category: 'advanced', icon: 'sparkles', nameKey: 'llm_judge_name', descriptionKey: 'llm_judge_description' },
    { id: 'smoke_bundle', category: 'advanced', icon: 'checklist', nameKey: 'smoke_bundle_name', descriptionKey: 'smoke_bundle_description' },
    { id: 'multi_turn', category: 'advanced', icon: 'messages-square', nameKey: 'multi_turn_name', descriptionKey: 'multi_turn_description' },
]);

export class FlowsEvaluationPage extends PlatformPage {
    static properties = {
        flowId: { type: String, attribute: 'flow-id' },
        branchId: { type: String, attribute: 'branch-id' },
        _loadKey: { state: true },
        _creatingCase: { state: true },
    };

    static styles = [
        PlatformPage.styles,
        css`
            :host {
                flex: 1;
                min-width: 0;
                min-height: 0;
                height: 100%;
                display: flex;
                overflow: hidden;
                color: var(--text-primary);
                background: var(--bg-elevated);
            }

            .lab {
                flex: 1;
                min-width: 0;
                min-height: 0;
                display: flex;
                flex-direction: column;
                overflow: hidden;
            }

            .top {
                min-height: 76px;
                display: grid;
                grid-template-columns: auto minmax(0, 1fr);
                align-items: center;
                gap: var(--space-3);
                padding: 10px 18px;
                border-bottom: 1px solid color-mix(in srgb, var(--border-subtle), transparent 18%);
                background: var(--glass-solid-subtle);
                box-shadow: 0 10px 26px color-mix(in srgb, var(--shadow-color), transparent 90%);
                box-sizing: border-box;
            }

            .brand {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                min-width: 220px;
            }

            .back {
                width: 38px;
                height: 38px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-full);
                border: 1px solid var(--border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                cursor: pointer;
                transition: var(--motion-transition-interactive);
            }

            .back:hover {
                background: var(--glass-solid-strong);
                color: var(--text-primary);
            }

            .brand-mark {
                width: 38px;
                height: 38px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border-radius: 12px;
                border: 1px solid color-mix(in srgb, var(--accent), transparent 58%);
                background: var(--accent-subtle);
                color: var(--accent);
            }

            .brand-copy {
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: 2px;
            }

            .brand-title {
                font-size: var(--text-base);
                line-height: 1.1;
                font-weight: var(--font-semibold);
            }

            .brand-sub {
                max-width: 280px;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }

            .workspace {
                flex: 1;
                min-width: 0;
                min-height: 0;
                display: grid;
                grid-template-columns: auto minmax(520px, 1fr) minmax(380px, 460px);
                overflow: hidden;
            }

            .panel-frame {
                position: relative;
                min-width: 0;
                min-height: 0;
                display: flex;
            }

            .panel-content {
                flex: 1;
                min-width: 0;
                min-height: 0;
                display: flex;
            }

            .panel-content > * {
                flex: 1;
                min-width: 0;
                min-height: 0;
            }

            .panel-fullscreen-bar {
                display: flex;
                align-items: center;
                justify-content: flex-end;
                gap: var(--space-2);
            }

            .panel-frame:not(.is-fullscreen) .panel-fullscreen-bar {
                position: absolute;
                top: 8px;
                right: 8px;
                z-index: 8;
            }

            .panel-frame:not(.is-fullscreen) .panel-fullscreen-title {
                display: none;
            }

            .panel-frame.is-fullscreen {
                position: fixed;
                top: max(10px, env(safe-area-inset-top));
                right: max(10px, env(safe-area-inset-right));
                bottom: max(10px, env(safe-area-inset-bottom));
                left: max(10px, env(safe-area-inset-left));
                z-index: 90;
                display: grid;
                grid-template-rows: 42px minmax(0, 1fr);
                gap: 10px;
                padding: 10px;
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-xl);
                background: var(--bg-elevated);
                box-shadow:
                    0 26px 80px color-mix(in srgb, var(--shadow-color), transparent 54%),
                    0 0 0 999vmax color-mix(in srgb, var(--bg-primary), transparent 18%);
                box-sizing: border-box;
            }

            .panel-frame.is-fullscreen .panel-fullscreen-bar {
                min-width: 0;
                justify-content: space-between;
                padding: 0 6px 0 14px;
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-lg);
                background: var(--glass-solid-subtle);
            }

            .panel-fullscreen-title {
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                color: var(--text-secondary);
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
            }

            .panel-fullscreen-toggle {
                width: 32px;
                height: 32px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-full);
                border: 1px solid var(--border-subtle);
                background: color-mix(in srgb, var(--glass-solid-strong), transparent 10%);
                color: var(--text-secondary);
                cursor: pointer;
                transition: var(--motion-transition-interactive);
                backdrop-filter: blur(16px);
            }

            .panel-fullscreen-toggle:hover {
                color: var(--text-primary);
                border-color: color-mix(in srgb, var(--accent), transparent 50%);
                background: color-mix(in srgb, var(--accent), transparent 88%);
            }

            .main {
                min-width: 0;
                min-height: 0;
                display: grid;
                grid-template-rows: minmax(280px, 1.04fr) minmax(240px, 0.96fr);
                gap: 12px;
                padding: 12px;
                overflow: hidden;
            }

            .right {
                min-width: 0;
                min-height: 0;
                padding: 12px 12px 12px 0;
                display: flex;
                overflow: hidden;
            }

            .empty {
                flex: 1;
                min-width: 0;
                min-height: 0;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: var(--space-6);
                color: var(--text-tertiary);
                text-align: center;
                border: 1px dashed var(--border-subtle);
                border-radius: var(--radius-xl);
                background: color-mix(in srgb, var(--bg-surface), transparent 8%);
            }

            .monitoring {
                flex: 1;
                min-width: 0;
                min-height: 0;
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                padding: var(--space-4);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-xl);
                background: var(--glass-solid-subtle);
                overflow: auto;
            }

            .monitor-row {
                display: grid;
                grid-template-columns: 1fr auto;
                gap: var(--space-2);
                align-items: center;
                padding: var(--space-3);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-lg);
                background: color-mix(in srgb, var(--bg-surface), transparent 14%);
            }

            .monitor-title {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                font-weight: var(--font-medium);
            }

            .monitor-meta {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }

            .pill {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                height: 28px;
                padding: 0 var(--space-2);
                border-radius: var(--radius-full);
                border: 1px solid var(--border-subtle);
                color: var(--text-secondary);
                font-size: var(--text-xs);
                background: var(--glass-solid-subtle);
            }

            @media (max-width: 1180px) {
                .top {
                    grid-template-columns: 1fr;
                    align-items: stretch;
                }

                .workspace {
                    grid-template-columns: auto minmax(0, 1fr);
                }

                .right {
                    display: none;
                }

                .workspace[data-fullscreen="true"] .right {
                    display: flex;
                    padding: 0;
                    overflow: visible;
                }
            }

            @media (max-width: 767px) {
                .top {
                    min-height: 0;
                    padding: 10px;
                }

                .brand {
                    min-width: 0;
                }

                .workspace {
                    grid-template-columns: 1fr;
                    grid-template-rows: auto minmax(0, 1fr);
                }

                .main {
                    padding: 10px;
                    grid-template-rows: minmax(280px, 1fr) minmax(240px, 1fr);
                }

                .panel-frame.is-fullscreen {
                    top: 0;
                    right: 0;
                    bottom: 0;
                    left: 0;
                    border-radius: 0;
                }
            }
        `,
    ];

    constructor() {
        super();
        this.flowId = '';
        this.branchId = 'default';
        this._loadKey = '';
        this._creatingCase = false;
        this._handleFullscreenKeydown = (event) => {
            this._onFullscreenKeydown(event);
        };
        this._ui = this.useSlice('flows/evaluation_ui');
        this._catalog = this.useOp('flows/evaluation_evaluator_catalog');
        this._suitesList = this.useOp('flows/evaluation_suites_list');
        this._suiteCreate = this.useOp('flows/evaluation_suite_create');
        this._casesList = this.useOp('flows/evaluation_cases_list');
        this._caseCreate = this.useOp('flows/evaluation_case_create');
        this._caseUpdate = this.useOp('flows/evaluation_case_update');
        this._runsList = this.useOp('flows/evaluation_runs_list');
        this._runCreate = this.useOp('flows/evaluation_run_create');
        this._runGet = this.useOp('flows/evaluation_run_get');
        this._runCancel = this.useOp('flows/evaluation_run_cancel');
        this._runEvents = this.useOp('flows/evaluation_run_events');
        this._matrixGet = this.useOp('flows/evaluation_matrix_get');
        this._compareRuns = this.useOp('flows/evaluation_compare_runs');
        this._traceGet = this.useOp('flows/evaluation_case_run_trace');
        this._annotationsList = this.useOp('flows/evaluation_annotations_list');
        this._annotationCreate = this.useOp('flows/evaluation_annotation_create');
        this._baselineSet = this.useOp('flows/evaluation_baseline_set');
        this._baselinesList = this.useOp('flows/evaluation_baselines_list');
        this._gatePoliciesList = this.useOp('flows/evaluation_gate_policies_list');
        this._monitorsList = this.useOp('flows/evaluation_monitors_list');
        this._pairwiseCreate = this.useOp('flows/evaluation_pairwise_judgment_create');
        this.useEvent('flows/evaluation/event', (event) => {
            void this._onEvaluationEvent(event);
        });
    }

    connectedCallback() {
        super.connectedCallback();
        window.addEventListener('keydown', this._handleFullscreenKeydown);
    }

    disconnectedCallback() {
        window.removeEventListener('keydown', this._handleFullscreenKeydown);
        super.disconnectedCallback();
    }

    updated(changed) {
        super.updated(changed);
        if (changed.has('flowId') || changed.has('branchId')) {
            const key = `${this.flowId}:${this._branchId()}`;
            if (key !== this._loadKey) {
                this._loadKey = key;
                this._ui.resetSelection(null);
                void this._loadInitial();
            }
        }
    }

    _onFullscreenKeydown(event) {
        if (event.key === 'Escape' && this._ui.value.fullscreenPanel.length > 0) {
            event.preventDefault();
            this._ui.setFullscreenPanel({ panel: '' });
        }
    }

    _branchId() {
        if (typeof this.branchId !== 'string') {
            return 'default';
        }
        const value = this.branchId.trim();
        if (value.length === 0 || value === 'base') {
            return 'default';
        }
        return value;
    }

    async _loadInitial() {
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            return;
        }
        await Promise.all([
            this._catalog.run(null),
            this._suitesList.run({ flow_id: this.flowId }),
        ]);
        const suites = this._suites();
        if (suites.length > 0) {
            const firstSuiteId = stringValue(suites[0], 'suite_id');
            if (firstSuiteId.length > 0) {
                this._ui.selectSuite({ suite_id: firstSuiteId });
                await this._loadSuite(firstSuiteId);
            }
        }
    }

    async _loadSuite(suiteId) {
        if (suiteId.length === 0) {
            return;
        }
        await Promise.all([
            this._casesList.run({ suite_id: suiteId }),
            this._runsList.run({ suite_id: suiteId, limit: 30 }),
            this._matrixGet.run({ suite_id: suiteId, branch_id: this._branchId(), limit: 16 }),
            this._baselinesList.run({ suite_id: suiteId }),
            this._gatePoliciesList.run({ suite_id: suiteId }),
            this._monitorsList.run({ suite_id: suiteId }),
        ]);
    }

    async _loadRun(runId) {
        if (runId.length === 0) {
            return;
        }
        await Promise.all([
            this._runGet.run({ run_id: runId }),
            this._runEvents.run({ run_id: runId }),
            this._annotationsList.run({ run_id: runId }),
        ]);
    }

    async _onEvaluationEvent(event) {
        const payload = event && typeof event.payload === 'object' ? event.payload : null;
        const runId = stringValue(payload, 'run_id');
        const selectedRunId = this._ui.value.selectedRunId;
        const selectedSuiteId = this._ui.value.selectedSuiteId;
        if (runId.length > 0 && runId === selectedRunId) {
            await this._loadRun(runId);
        }
        if (selectedSuiteId.length > 0) {
            await Promise.all([
                this._runsList.run({ suite_id: selectedSuiteId, limit: 30 }),
                this._matrixGet.run({ suite_id: selectedSuiteId, branch_id: this._branchId(), limit: 16 }),
            ]);
        }
    }

    _suites() {
        return itemsFromResult(this._suitesList.lastResult);
    }

    _cases() {
        return itemsFromResult(this._casesList.lastResult);
    }

    _runs() {
        return itemsFromResult(this._runsList.lastResult);
    }

    _catalogItems() {
        return itemsFromResult(this._catalog.lastResult);
    }

    _caseTemplates() {
        const staticTemplates = STATIC_CASE_TEMPLATES.map((template) => ({
            id: template.id,
            category: template.category,
            icon: template.icon,
            name: this.t(`evaluation.templates.${template.nameKey}`),
            description: this.t(`evaluation.templates.${template.descriptionKey}`),
        }));
        const metricTemplates = this._catalogItems()
            .filter((item) => stringValue(item, 'check_type') === 'builtin_metric')
            .map((item) => {
                const evaluatorId = stringValue(item, 'evaluator_id');
                const catalogCategory = stringValue(item, 'category');
                let category = boolValue(item, 'requires_llm') ? 'quality' : 'deterministic';
                if (catalogCategory === 'safety') {
                    category = 'safety';
                }
                if (catalogCategory === 'trace') {
                    category = 'trace';
                }
                return {
                    id: `builtin_metric:${evaluatorId}`,
                    category,
                    icon: 'badge-check',
                    name: this.t(evaluationCatalogNameKey(evaluatorId)),
                    description: this.t(evaluationCatalogDescriptionKey(evaluatorId)),
                };
            });
        return [...staticTemplates, ...metricTemplates];
    }

    _annotations() {
        return itemsFromResult(this._annotationsList.lastResult);
    }

    _monitors() {
        return itemsFromResult(this._monitorsList.lastResult);
    }

    _gatePolicies() {
        return itemsFromResult(this._gatePoliciesList.lastResult);
    }

    _baselines() {
        return itemsFromResult(this._baselinesList.lastResult);
    }

    _runResult() {
        return this._runGet.lastResult && typeof this._runGet.lastResult === 'object' ? this._runGet.lastResult : null;
    }

    _currentRun() {
        const result = this._runResult();
        const run = objectValue(result, 'run');
        if (run && stringValue(run, 'run_id') === this._ui.value.selectedRunId) {
            return run;
        }
        return findById(this._runs(), 'run_id', this._ui.value.selectedRunId);
    }

    _caseRuns() {
        const result = this._runResult();
        if (!result || typeof result !== 'object') {
            return [];
        }
        return asArray(result.case_runs);
    }

    _events() {
        return itemsFromResult(this._runEvents.lastResult);
    }

    _matrix() {
        return this._matrixGet.lastResult && typeof this._matrixGet.lastResult === 'object' ? this._matrixGet.lastResult : null;
    }

    _trace() {
        return this._traceGet.lastResult && typeof this._traceGet.lastResult === 'object' ? this._traceGet.lastResult : null;
    }

    _selectedSuite() {
        return findById(this._suites(), 'suite_id', this._ui.value.selectedSuiteId);
    }

    _selectedCase() {
        if (this._creatingCase) {
            return null;
        }
        return findById(this._cases(), 'case_id', this._ui.value.selectedCaseId);
    }

    _selectedCaseRun() {
        return findById(this._caseRuns(), 'case_run_id', this._ui.value.selectedCaseRunId);
    }

    async _selectSuite(event) {
        const suiteId = stringValue(event.detail, 'suite_id');
        if (suiteId.length === 0) {
            return;
        }
        this._creatingCase = false;
        this._ui.selectSuite({ suite_id: suiteId });
        await this._loadSuite(suiteId);
    }

    _selectCase(event) {
        const caseId = stringValue(event.detail, 'case_id');
        this._creatingCase = false;
        this._ui.selectCase({ case_id: caseId });
    }

    async _selectRun(event) {
        const runId = stringValue(event.detail, 'run_id');
        if (runId.length === 0) {
            return;
        }
        this._ui.selectRun({ run_id: runId });
        await this._loadRun(runId);
    }

    async _selectCaseRun(event) {
        const detail = event.detail && typeof event.detail === 'object' ? event.detail : null;
        const runId = stringValue(detail, 'run_id');
        const caseRunId = stringValue(detail, 'case_run_id');
        if (runId.length > 0 && runId !== this._ui.value.selectedRunId) {
            this._ui.selectRun({ run_id: runId });
            await this._loadRun(runId);
        }
        if (caseRunId.length > 0) {
            this._ui.selectCaseRun({ case_run_id: caseRunId });
            await this._traceGet.run({ case_run_id: caseRunId });
            const caseId = caseIdForCaseRun(this._matrix(), caseRunId);
            if (caseId.length > 0) {
                this._ui.selectCase({ case_id: caseId });
            }
        }
    }

    _setPanel(event) {
        const panel = stringValue(event.detail, 'panel');
        if (panel.length > 0) {
            this._ui.setPanel({ panel });
        }
    }

    _toggleFullscreenPanel(panel, event) {
        event.stopPropagation();
        const nextPanel = this._ui.value.fullscreenPanel === panel ? '' : panel;
        this._ui.setFullscreenPanel({ panel: nextPanel });
    }

    _setRunScope(event) {
        const scope = stringValue(event.detail, 'scope');
        if (scope.length > 0) {
            this._ui.setRunScope({ scope });
        }
    }

    _setRunOptions(event) {
        const detail = event.detail && typeof event.detail === 'object' ? event.detail : {};
        this._ui.setRunOptions({
            trials: typeof detail.trials === 'number' ? detail.trials : this._ui.value.trials,
            max_concurrency: typeof detail.max_concurrency === 'number' ? detail.max_concurrency : this._ui.value.maxConcurrency,
        });
    }

    async _createSuite() {
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            return;
        }
        const result = await this._suiteCreate.run({
            body: {
                flow_id: this.flowId,
                name: this.t('evaluation.defaults.suite_name'),
                description: '',
                tags: [],
            },
        });
        await this._suitesList.run({ flow_id: this.flowId });
        const suiteId = stringValue(result, 'suite_id');
        if (suiteId.length > 0) {
            this._ui.selectSuite({ suite_id: suiteId });
            await this._loadSuite(suiteId);
        }
    }

    _startCreateCase() {
        this._creatingCase = true;
        this._ui.selectCase({ case_id: '' });
        this._ui.setPanel({ panel: 'case' });
    }

    async _createCase(event) {
        const suite = this._selectedSuite();
        const suiteId = stringValue(suite, 'suite_id');
        if (suiteId.length === 0) {
            return;
        }
        const detail = event.detail && typeof event.detail === 'object' ? event.detail : null;
        const body = objectValue(detail, 'body');
        if (!body) {
            throw new Error('FlowsEvaluationPage._createCase: body required');
        }
        const created = await this._caseCreate.run({ suite_id: suiteId, body });
        await this._loadSuite(suiteId);
        const caseId = stringValue(created, 'case_id');
        if (caseId.length > 0) {
            this._creatingCase = false;
            this._ui.selectCase({ case_id: caseId });
        }
    }

    async _createCaseFromTemplate(event) {
        const suite = this._selectedSuite();
        const suiteId = stringValue(suite, 'suite_id');
        if (suiteId.length === 0) {
            this.toast('evaluation.toast.suite_required', { type: 'error' });
            return;
        }
        const templateId = stringValue(event.detail, 'template_id');
        if (templateId.length === 0) {
            throw new Error('FlowsEvaluationPage._createCaseFromTemplate: template_id required');
        }
        const body = this._buildTemplateCaseBody(templateId);
        const created = await this._caseCreate.run({ suite_id: suiteId, body });
        await this._loadSuite(suiteId);
        const caseId = stringValue(created, 'case_id');
        if (caseId.length > 0) {
            this._creatingCase = false;
            this._ui.selectCase({ case_id: caseId });
            this._ui.setPanel({ panel: 'case' });
        }
    }

    _buildTemplateCaseBody(templateId) {
        if (templateId.startsWith('builtin_metric:')) {
            const evaluatorId = templateId.slice('builtin_metric:'.length);
            return this._builtinMetricTemplateBody(evaluatorId);
        }
        switch (templateId) {
            case 'contains_response':
                return this._caseBody(
                    this.t('evaluation.templates.contains_case_title'),
                    this.t('evaluation.templates.contains_case_description'),
                    ['deterministic', 'contains'],
                    [this._turn(this.t('evaluation.templates.sample_input'), [
                        { type: 'contains', source: 'response', values: [this.t('evaluation.templates.sample_expected_fragment')], mode: 'any', case_sensitive: false, state_path: null },
                    ])],
                );
            case 'not_contains_response':
                return this._caseBody(
                    this.t('evaluation.templates.not_contains_case_title'),
                    this.t('evaluation.templates.not_contains_case_description'),
                    ['safety', 'not_contains'],
                    [this._turn(this.t('evaluation.templates.sample_input'), [
                        { type: 'not_contains', source: 'response', values: [this.t('evaluation.templates.sample_forbidden_fragment')], case_sensitive: false, state_path: null },
                    ])],
                );
            case 'regex_response':
                return this._caseBody(
                    this.t('evaluation.templates.regex_case_title'),
                    this.t('evaluation.templates.regex_case_description'),
                    ['deterministic', 'regex'],
                    [this._turn(this.t('evaluation.templates.regex_input'), [
                        { type: 'regex', source: 'response', pattern: this.t('evaluation.templates.regex_pattern'), ignore_case: true, state_path: null },
                    ])],
                );
            case 'length_response':
                return this._caseBody(
                    this.t('evaluation.templates.length_case_title'),
                    this.t('evaluation.templates.length_case_description'),
                    ['deterministic', 'length'],
                    [this._turn(this.t('evaluation.templates.sample_input'), [
                        { type: 'length', source: 'response', min_chars: 20, max_chars: 800, state_path: null },
                    ])],
                );
            case 'state_path':
                return this._caseBody(
                    this.t('evaluation.templates.state_path_case_title'),
                    this.t('evaluation.templates.state_path_case_description'),
                    ['state', 'contract'],
                    [this._turn(this.t('evaluation.templates.sample_input'), [
                        { type: 'state_path', path: 'response', operator: 'ne', value: null },
                    ])],
                );
            case 'json_schema_response':
                return this._caseBody(
                    this.t('evaluation.templates.json_schema_case_title'),
                    this.t('evaluation.templates.json_schema_case_description'),
                    ['json_schema', 'contract'],
                    [this._turn(this.t('evaluation.templates.json_schema_input'), [
                        {
                            type: 'json_schema',
                            source: 'state',
                            state_path: 'structured_output',
                            json_schema: {
                                type: 'object',
                                properties: { answer: { type: 'string' } },
                                required: ['answer'],
                            },
                        },
                    ])],
                );
            case 'trace_tool_called':
                return this._caseBody(
                    this.t('evaluation.templates.trace_tool_case_title'),
                    this.t('evaluation.templates.trace_tool_case_description'),
                    ['trace', 'tool'],
                    [this._turn(this.t('evaluation.templates.trace_tool_input'), [
                        { type: 'trace_assertion', assertion: 'tool_called', value: 'tool_node_id_or_call_id' },
                    ])],
                );
            case 'trace_node_completed':
                return this._caseBody(
                    this.t('evaluation.templates.trace_node_case_title'),
                    this.t('evaluation.templates.trace_node_case_description'),
                    ['trace', 'node'],
                    [this._turn(this.t('evaluation.templates.trace_node_input'), [
                        { type: 'trace_assertion', assertion: 'node_completed', value: 'node_id' },
                    ])],
                );
            case 'trace_node_failed':
                return this._caseBody(
                    this.t('evaluation.templates.trace_node_failed_case_title'),
                    this.t('evaluation.templates.trace_node_failed_case_description'),
                    ['trace', 'node_failed'],
                    [this._turn(this.t('evaluation.templates.trace_node_failed_input'), [
                        { type: 'trace_assertion', assertion: 'node_failed', value: 'node_id' },
                    ])],
                );
            case 'code_python':
                return this._caseBody(
                    this.t('evaluation.templates.code_case_title'),
                    this.t('evaluation.templates.code_case_description'),
                    ['code', 'custom'],
                    [this._turn(this.t('evaluation.templates.sample_input'), [
                        {
                            type: 'code',
                            language: 'python',
                            source: 'def evaluate(state, response, dialog):\n    passed = len(response.strip()) > 0\n    return {\"result\": 10.0 if passed else 0.0, \"passed\": passed}\n',
                            entrypoint: null,
                        },
                    ])],
                );
            case 'llm_judge':
                return this._caseBody(
                    this.t('evaluation.templates.llm_judge_case_title'),
                    this.t('evaluation.templates.llm_judge_case_description'),
                    ['llm_judge', 'rubric'],
                    [this._turn(this.t('evaluation.templates.sample_input'), [
                        { type: 'llm_judge', rubric_version_id: 'rubric_version_id', judge_node_id: null, judge_node: null },
                    ])],
                );
            case 'smoke_bundle':
                return this._caseBody(
                    this.t('evaluation.templates.smoke_bundle_case_title'),
                    this.t('evaluation.templates.smoke_bundle_case_description'),
                    ['smoke', 'regression'],
                    [this._turn(this.t('evaluation.templates.sample_input'), [
                        { type: 'contains', source: 'response', values: [this.t('evaluation.templates.sample_expected_fragment')], mode: 'any', case_sensitive: false, state_path: null },
                        { type: 'not_contains', source: 'response', values: [this.t('evaluation.templates.sample_forbidden_fragment')], case_sensitive: false, state_path: null },
                        { type: 'length', source: 'response', min_chars: 20, max_chars: 800, state_path: null },
                    ])],
                );
            case 'multi_turn':
                return this._caseBody(
                    this.t('evaluation.templates.multi_turn_case_title'),
                    this.t('evaluation.templates.multi_turn_case_description'),
                    ['multi_turn', 'conversation'],
                    [
                        this._turn(this.t('evaluation.templates.multi_turn_first_input'), [
                            { type: 'contains', source: 'response', values: [this.t('evaluation.templates.multi_turn_first_expected')], mode: 'any', case_sensitive: false, state_path: null },
                        ]),
                        this._turn(this.t('evaluation.templates.multi_turn_second_input'), [
                            { type: 'contains', source: 'response', values: [this.t('evaluation.templates.multi_turn_second_expected')], mode: 'any', case_sensitive: false, state_path: null },
                        ]),
                    ],
                );
            default:
                throw new Error(`FlowsEvaluationPage: unsupported template ${templateId}`);
        }
    }

    _builtinMetricTemplateBody(evaluatorId) {
        const item = this._catalogItems().find((catalogItem) => stringValue(catalogItem, 'evaluator_id') === evaluatorId);
        if (!item || stringValue(item, 'check_type') !== 'builtin_metric') {
            throw new Error(`FlowsEvaluationPage: builtin metric template not found ${evaluatorId}`);
        }
        return this._caseBody(
            this.t('evaluation.templates.metric_case_title', { metric: this.t(evaluationCatalogNameKey(evaluatorId)) }),
            this.t(evaluationCatalogDescriptionKey(evaluatorId)),
            ['metric', evaluatorId],
            [this._turn(this.t('evaluation.templates.sample_input'), [
                {
                    type: 'builtin_metric',
                    evaluator_id: evaluatorId,
                    source: 'response',
                    state_path: null,
                    reference: boolValue(item, 'requires_reference') ? this.t('evaluation.templates.metric_reference') : null,
                    threshold: null,
                    judge_node_id: null,
                    judge_node: null,
                },
            ])],
        );
    }

    _caseBody(name, description, tags, turns) {
        return {
            name,
            description,
            branch_ids: '*',
            target: { type: 'flow' },
            initial_state: null,
            turns,
            max_turns: 10,
            timeout_seconds: 300,
            enabled: true,
            tags,
            sort_order: 0,
        };
    }

    _turn(input, checks) {
        return {
            input: { type: 'text', content: input },
            checks,
        };
    }

    async _updateCase(event) {
        const suite = this._selectedSuite();
        const suiteId = stringValue(suite, 'suite_id');
        const detail = event.detail && typeof event.detail === 'object' ? event.detail : null;
        const caseId = stringValue(detail, 'case_id');
        const body = objectValue(detail, 'body');
        if (suiteId.length === 0 || caseId.length === 0 || !body) {
            throw new Error('FlowsEvaluationPage._updateCase: suite_id, case_id and body required');
        }
        await this._caseUpdate.run({ suite_id: suiteId, case_id: caseId, body });
        await this._loadSuite(suiteId);
        this._ui.selectCase({ case_id: caseId });
    }

    async _runEvaluation() {
        const suite = this._selectedSuite();
        const suiteId = stringValue(suite, 'suite_id');
        if (suiteId.length === 0) {
            return;
        }
        const ui = this._ui.value;
        let scope = { type: 'suite' };
        if (ui.runScope === 'selected_case') {
            if (ui.selectedCaseId.length === 0) {
                this.toast('evaluation.toast.case_required', { type: 'error' });
                return;
            }
            scope = { type: 'cases', case_ids: [ui.selectedCaseId] };
        }
        const result = await this._runCreate.run({
            body: {
                suite_id: suiteId,
                branch_id: this._branchId(),
                trigger: 'manual',
                scope,
                trials: ui.trials,
                max_concurrency: ui.maxConcurrency,
                gate_policy_id: null,
                idempotency_key: null,
            },
        });
        const run = objectValue(result, 'run');
        const runId = stringValue(run, 'run_id');
        if (runId.length > 0) {
            this._ui.selectRun({ run_id: runId });
            await this._loadRun(runId);
        }
        await this._loadSuite(suiteId);
    }

    async _cancelRun(event) {
        const runId = stringValue(event.detail, 'run_id');
        const suiteId = this._ui.value.selectedSuiteId;
        if (runId.length === 0) {
            return;
        }
        await this._runCancel.run({ run_id: runId });
        await this._loadRun(runId);
        if (suiteId.length > 0) {
            await this._loadSuite(suiteId);
        }
    }

    async _reloadCurrent() {
        const suiteId = this._ui.value.selectedSuiteId;
        if (suiteId.length > 0) {
            await this._loadSuite(suiteId);
        }
        const runId = this._ui.value.selectedRunId;
        if (runId.length > 0) {
            await this._loadRun(runId);
        }
    }

    async _selectCompareRun(event) {
        const runId = stringValue(event.detail, 'run_id');
        this._ui.selectCompareRun({ run_id: runId });
    }

    async _compareRunsRequest() {
        const leftRunId = this._ui.value.selectedCompareRunId;
        const rightRunId = this._ui.value.selectedRunId;
        if (leftRunId.length === 0 || rightRunId.length === 0 || leftRunId === rightRunId) {
            this.toast('evaluation.toast.compare_required', { type: 'error' });
            return;
        }
        await this._compareRuns.run({ left_run_id: leftRunId, right_run_id: rightRunId });
    }

    async _setBaseline() {
        const suiteId = this._ui.value.selectedSuiteId;
        const runId = this._ui.value.selectedRunId;
        if (suiteId.length === 0 || runId.length === 0) {
            this.toast('evaluation.toast.run_required', { type: 'error' });
            return;
        }
        await this._baselineSet.run({
            suite_id: suiteId,
            branch_id: this._branchId(),
            body: { run_id: runId },
        });
        await this._baselinesList.run({ suite_id: suiteId });
    }

    async _createPairwiseJudgment(event) {
        const detail = event.detail && typeof event.detail === 'object' ? event.detail : null;
        const mode = stringValue(detail, 'mode');
        const preference = stringValue(detail, 'preference');
        const matrix = this._matrix();
        let caseId = this._ui.value.selectedCaseId;
        if (caseId.length === 0) {
            caseId = caseIdForCaseRun(matrix, this._ui.value.selectedCaseRunId);
        }
        const left = matrixCell(matrix, this._ui.value.selectedCompareRunId, caseId);
        const right = matrixCell(matrix, this._ui.value.selectedRunId, caseId);
        if (!left || !right || mode.length === 0) {
            this.toast('evaluation.toast.pairwise_required', { type: 'error' });
            return;
        }
        await this._pairwiseCreate.run({
            body: {
                mode,
                left_case_run_id: stringValue(left, 'case_run_id'),
                right_case_run_id: stringValue(right, 'case_run_id'),
                preferred: mode === 'human' ? preference : null,
                rubric_version_id: null,
                scores: {},
                feedback: '',
                judge_node_id: null,
                judge_node: null,
            },
        });
    }

    _backToEditor() {
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            this.navigate('list', {});
            return;
        }
        const branchId = this._branchId();
        if (branchId === 'default') {
            this.navigate('flow_editor', { flowId: this.flowId });
            return;
        }
        this.navigate('flow_editor_branch', { flowId: this.flowId, branchId });
    }

    render() {
        const ui = this._ui.value;
        const suite = this._selectedSuite();
        const testCase = this._selectedCase();
        const run = this._currentRun();
        const matrix = this._matrix();
        const caseRun = this._selectedCaseRun();
        const activePanel = ui.activePanel;
        const fullscreenActive = ui.fullscreenPanel.length > 0;
        return html`
            <div class="lab">
                <header class="top">
                    <div class="brand">
                        <button class="back" type="button" title=${this.t('evaluation.header.back')} @click=${this._backToEditor}>
                            <platform-icon name="arrow-left" size="18"></platform-icon>
                        </button>
                        <span class="brand-mark"><platform-icon name="science" size="20"></platform-icon></span>
                        <span class="brand-copy">
                            <span class="brand-title">${this.t('evaluation.header.title')}</span>
                            <span class="brand-sub">${this.flowId} · ${this._branchId()}</span>
                        </span>
                    </div>
                    <flows-evaluation-run-toolbar
                        .branchId=${this._branchId()}
                        .selectedSuite=${suite}
                        .selectedCase=${testCase}
                        .selectedRun=${run}
                        .caseTemplates=${this._caseTemplates()}
                        .runScope=${ui.runScope}
                        .trials=${ui.trials}
                        .maxConcurrency=${ui.maxConcurrency}
                        .busy=${this._runCreate.busy || this._runCancel.busy}
                        @scope-change=${this._setRunScope}
                        @options-change=${this._setRunOptions}
                        @run-request=${this._runEvaluation}
                        @cancel-request=${this._cancelRun}
                        @reload-request=${this._reloadCurrent}
                        @template-create-request=${this._createCaseFromTemplate}
                    ></flows-evaluation-run-toolbar>
                </header>

                <main class="workspace" data-fullscreen=${fullscreenActive ? 'true' : 'false'}>
                    <flows-evaluation-suite-sidebar
                        .suites=${this._suites()}
                        .cases=${this._cases()}
                        .catalog=${this._catalogItems()}
                        .selectedSuiteId=${ui.selectedSuiteId}
                        .selectedCaseId=${ui.selectedCaseId}
                        .activePanel=${ui.activePanel}
                        @suite-select=${this._selectSuite}
                        @case-select=${this._selectCase}
                        @suite-create=${this._createSuite}
                        @case-create=${this._startCreateCase}
                        @panel-select=${this._setPanel}
                    ></flows-evaluation-suite-sidebar>

                    <section class="main">
                        ${this._renderPanelFrame('matrix', this.t('evaluation.matrix.title'), html`
                            <flows-evaluation-results-matrix
                                .matrix=${matrix}
                                .selectedRunId=${ui.selectedRunId}
                                .selectedCaseRunId=${ui.selectedCaseRunId}
                                @run-select=${this._selectRun}
                                @case-run-select=${this._selectCaseRun}
                            ></flows-evaluation-results-matrix>
                        `)}
                        ${this._renderPanelFrame('transcript', this.t('evaluation.transcript.title'), html`
                            <flows-evaluation-transcript
                                .run=${run}
                                .caseRuns=${this._caseRuns()}
                                .events=${this._events()}
                                .selectedCaseRunId=${ui.selectedCaseRunId}
                            ></flows-evaluation-transcript>
                        `)}
                    </section>

                    <aside class="right">
                        ${this._renderPanelFrame(activePanel, this._rightPanelTitle(activePanel, testCase), this._renderRightPanel(activePanel, suite, testCase, run, caseRun))}
                    </aside>
                </main>
            </div>
        `;
    }

    _renderPanelFrame(panel, title, content) {
        const active = this._ui.value.fullscreenPanel === panel;
        const frameClass = active ? 'panel-frame is-fullscreen' : 'panel-frame';
        const actionTitle = active ? this.t('evaluation.fullscreen.collapse') : this.t('evaluation.fullscreen.expand');
        return html`
            <div class=${frameClass} data-panel=${panel}>
                <div class="panel-fullscreen-bar">
                    <span class="panel-fullscreen-title">${title}</span>
                    <button
                        class="panel-fullscreen-toggle"
                        type="button"
                        title=${actionTitle}
                        aria-label=${actionTitle}
                        aria-pressed=${active ? 'true' : 'false'}
                        @click=${(event) => this._toggleFullscreenPanel(panel, event)}
                    >
                        <platform-icon name=${active ? 'minimize' : 'fullscreen'} size="15"></platform-icon>
                    </button>
                </div>
                <div class="panel-content">${content}</div>
            </div>
        `;
    }

    _rightPanelTitle(activePanel, testCase) {
        if (activePanel === 'case') {
            return stringValue(testCase, 'case_id').length > 0 ? this.t('evaluation.case_editor.edit_title') : this.t('evaluation.case_editor.create_title');
        }
        if (activePanel === 'compare') {
            return this.t('evaluation.compare.title');
        }
        if (activePanel === 'trace') {
            return this.t('evaluation.trace.title');
        }
        if (activePanel === 'monitoring') {
            return this.t('evaluation.panels.monitoring');
        }
        return this.t('evaluation.panels.unknown');
    }

    _renderRightPanel(activePanel, suite, testCase, run, caseRun) {
        if (activePanel === 'case') {
            return html`
                <flows-evaluation-case-editor
                    .suite=${suite}
                    .testCase=${testCase}
                    .catalog=${this._catalogItems()}
                    .busy=${this._caseCreate.busy || this._caseUpdate.busy}
                    @case-create=${this._createCase}
                    @case-update=${this._updateCase}
                ></flows-evaluation-case-editor>
            `;
        }
        if (activePanel === 'compare') {
            return html`
                <flows-evaluation-compare-panel
                    .runs=${this._runs()}
                    .selectedRunId=${this._ui.value.selectedRunId}
                    .selectedCompareRunId=${this._ui.value.selectedCompareRunId}
                    .compareResult=${this._compareRuns.lastResult}
                    .busy=${this._compareRuns.busy || this._baselineSet.busy}
                    @compare-run-select=${this._selectCompareRun}
                    @compare-request=${this._compareRunsRequest}
                    @baseline-set-request=${this._setBaseline}
                    @pairwise-judge-request=${this._createPairwiseJudgment}
                ></flows-evaluation-compare-panel>
            `;
        }
        if (activePanel === 'trace') {
            return html`
                <flows-evaluation-trace-panel
                    .trace=${this._trace()}
                    .caseRun=${caseRun}
                    .annotations=${this._annotations()}
                    .busy=${this._traceGet.busy}
                ></flows-evaluation-trace-panel>
            `;
        }
        if (activePanel === 'monitoring') {
            return this._renderMonitoringPanel(run);
        }
        return html`<div class="empty">${this.t('evaluation.panels.unknown')}</div>`;
    }

    _renderMonitoringPanel(run) {
        const monitors = this._monitors();
        const policies = this._gatePolicies();
        const baselines = this._baselines();
        const active = runStateIsActive(run);
        return html`
            <section class="monitoring">
                <div class="monitor-row">
                    <div>
                        <div class="monitor-title">
                            ${this.t('evaluation.monitoring.gates')}
                            <platform-help-hint
                                .text=${this.t('evaluation.hints.monitoring')}
                                .label=${this.t('evaluation.hints.monitoring_label')}
                                placement="bottom"
                            ></platform-help-hint>
                        </div>
                        <div class="monitor-meta">${policies.length} ${this.t('evaluation.monitoring.policies')} · ${baselines.length} ${this.t('evaluation.monitoring.baselines')}</div>
                    </div>
                    <span class="pill"><platform-icon name="shield" size="13"></platform-icon>${active ? this.t('evaluation.monitoring.active_run') : this.t('evaluation.monitoring.ready')}</span>
                </div>
                ${monitors.length > 0 ? monitors.map((monitor) => this._renderMonitor(monitor)) : html`<div class="empty">${this.t('evaluation.monitoring.empty')}</div>`}
            </section>
        `;
    }

    _renderMonitor(monitor) {
        return html`
            <div class="monitor-row">
                <div>
                    <div class="monitor-title">${stringValue(monitor, 'name')}</div>
                    <div class="monitor-meta">${stringValue(monitor, 'state')} · ${stringValue(monitor, 'branch_id')}</div>
                </div>
                <span class="pill"><platform-icon name="activity" size="13"></platform-icon>${stringValue(monitor, 'monitor_id').slice(0, 8)}</span>
            </div>
        `;
    }
}

customElements.define('flows-evaluation-page', FlowsEvaluationPage);
